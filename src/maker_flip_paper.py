"""
Maker-flip paper trading simulation (strategy validation, zero capital)

Simulates the "maker flip" strategy end-to-end using only real, live data:
- Fair value = DEX-implied mid price, from a real, deep on-chain pool
- Hypothetical resting quotes = fair value +/- half_spread_bps
- Fill detection = did a REAL Coinbase trade actually print through our
  quote? (a taker SELL at/below our bid means our bid would have filled;
  a taker BUY at/above our ask means our ask would have filled)
- On a simulated fill, the hedge leg is priced using real constant-product
  AMM math against the pool's actual current reserves -- not the linear
  approximation used elsewhere in this bot for quick cycle profit
  estimates, since realistic hedge cost is the entire point here.

This places no real orders, signs nothing, and touches no real funds. It
is a backtest-style paper trader driven entirely by real market data, to
answer "would this strategy actually have made money" before ever
risking anything.

Known simplifying assumptions (deliberate, for this first pass):
- Assumes our quote fills completely once price crosses it, regardless
  of the crossing trade's own size or our position in the order book
  queue (a real resting order could be partially filled, or sit behind
  other orders at the same price and not fill at all).
- Assumes the hedge executes instantly and completely at the simulated
  AMM price the moment a fill is detected -- no hedge latency, no
  slippage from other traders acting on the pool in between.
- Requotes every tick (matching the poll cadence, currently ~10s) rather
  than continuously -- a real market maker would want much faster requote
  cycles, especially since DEX prices can move between polls.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.coinbase_feed import Trade

logger = logging.getLogger(__name__)


def _swap_exact_in(
    reserve_in: float, reserve_out: float, amount_in: float, fee_bps: float
) -> float:
    """Real constant-product (x*y=k) swap: given amount_in, what's received."""
    amount_in_after_fee = amount_in * (1 - fee_bps / 10000)
    k = reserve_in * reserve_out
    new_reserve_in = reserve_in + amount_in_after_fee
    new_reserve_out = k / new_reserve_in
    return reserve_out - new_reserve_out


def _swap_exact_out(
    reserve_in: float, reserve_out: float, amount_out: float, fee_bps: float
) -> float:
    """Real constant-product (x*y=k) swap: input required for a fixed amount_out."""
    if amount_out >= reserve_out:
        raise ValueError("Cannot swap out more than the pool's available reserve")
    k = reserve_in * reserve_out
    new_reserve_out = reserve_out - amount_out
    new_reserve_in = k / new_reserve_out
    amount_in_after_fee = new_reserve_in - reserve_in
    return amount_in_after_fee / (1 - fee_bps / 10000)


@dataclass
class PaperFill:
    """One simulated maker-flip round trip: a CEX fill plus its DEX hedge."""

    ts_utc: datetime
    cex_side: str  # "buy_algo" or "sell_algo" (what we did on Coinbase)
    cex_price: float
    algo_amount: float
    cex_notional_usd: float
    dex_hedge_notional_usd: float
    maker_fee_usd: float
    dex_fee_bps: float
    net_pnl_usd: float
    trade_id: int


class MakerFlipPaperTrader:
    """
    Paper-trades the maker-flip strategy: hypothetically quote on Coinbase
    around DEX-implied fair value, and on a simulated fill, hedge against
    real, live DEX reserves using proper AMM math.
    """

    def __init__(
        self,
        quote_half_spread_bps: float = 80.0,
        maker_fee_bps: float = 0.0,
        quote_size_usd: float = 500.0,
    ):
        # Needs to comfortably exceed dex_fee_bps (live, ~30-36bps for our
        # pools) plus maker_fee_bps for a filled round-trip to be
        # profitable at all -- see net_pnl_usd calculation below.
        self.quote_half_spread_bps = quote_half_spread_bps
        self.maker_fee_bps = maker_fee_bps
        self.quote_size_usd = quote_size_usd

        self.last_seen_trade_id: Optional[int] = None
        self.fills: List[PaperFill] = []
        self.realized_pnl_usd: float = 0.0

    def current_quotes(self, fair_value: float) -> Tuple[float, float]:
        """Hypothetical (bid, ask) around the given DEX-implied fair value."""
        half = self.quote_half_spread_bps / 10000
        return fair_value * (1 - half), fair_value * (1 + half)

    def tick(
        self,
        fair_value: float,
        trades: List[Trade],
        dex_reserve_algo: float,
        dex_reserve_usd: float,
        dex_fee_bps: float,
    ) -> List[PaperFill]:
        """
        Process every real trade since the last tick against our current
        hypothetical quotes (computed fresh each tick from fair_value).
        Returns any newly simulated fills from this call.
        """
        bid, ask = self.current_quotes(fair_value)
        new_fills = []

        for t in trades:
            if (
                self.last_seen_trade_id is not None
                and t.trade_id <= self.last_seen_trade_id
            ):
                continue

            fill = None
            if t.side == "SELL" and t.price <= bid:
                # A real seller hit bids at/below ours -> our bid fills:
                # we buy ALGO at `bid`, and must hedge by selling it on the DEX.
                fill = self._simulate_fill(
                    cex_side="buy_algo",
                    cex_price=bid,
                    dex_reserve_algo=dex_reserve_algo,
                    dex_reserve_usd=dex_reserve_usd,
                    dex_fee_bps=dex_fee_bps,
                    trade_id=t.trade_id,
                )
            elif t.side == "BUY" and t.price >= ask:
                # A real buyer lifted asks at/above ours -> our ask fills:
                # we sell ALGO at `ask`, and must hedge by buying it on the DEX.
                fill = self._simulate_fill(
                    cex_side="sell_algo",
                    cex_price=ask,
                    dex_reserve_algo=dex_reserve_algo,
                    dex_reserve_usd=dex_reserve_usd,
                    dex_fee_bps=dex_fee_bps,
                    trade_id=t.trade_id,
                )

            if fill:
                new_fills.append(fill)
                self.fills.append(fill)
                self.realized_pnl_usd += fill.net_pnl_usd
                logger.info(
                    f"Paper fill: {fill.cex_side} {fill.algo_amount:.2f} ALGO "
                    f"@{fill.cex_price:.6f} on Coinbase, hedged on DEX, "
                    f"net_pnl=${fill.net_pnl_usd:.4f}"
                )

            self.last_seen_trade_id = t.trade_id

        return new_fills

    def _simulate_fill(
        self,
        cex_side: str,
        cex_price: float,
        dex_reserve_algo: float,
        dex_reserve_usd: float,
        dex_fee_bps: float,
        trade_id: int,
    ) -> PaperFill:
        algo_amount = self.quote_size_usd / cex_price
        cex_notional_usd = algo_amount * cex_price
        maker_fee_usd = cex_notional_usd * (self.maker_fee_bps / 10000)

        if cex_side == "buy_algo":
            # Now hold algo_amount ALGO from the CEX fill; hedge by selling
            # it into the DEX pool.
            dex_hedge_notional_usd = _swap_exact_in(
                dex_reserve_algo, dex_reserve_usd, algo_amount, dex_fee_bps
            )
            net_pnl_usd = dex_hedge_notional_usd - cex_notional_usd - maker_fee_usd
        else:
            # Now owe algo_amount ALGO from the CEX fill (sold it); hedge
            # by buying exactly that amount from the DEX pool.
            dex_hedge_notional_usd = _swap_exact_out(
                dex_reserve_usd, dex_reserve_algo, algo_amount, dex_fee_bps
            )
            net_pnl_usd = cex_notional_usd - dex_hedge_notional_usd - maker_fee_usd

        return PaperFill(
            ts_utc=datetime.now(timezone.utc),
            cex_side=cex_side,
            cex_price=cex_price,
            algo_amount=algo_amount,
            cex_notional_usd=cex_notional_usd,
            dex_hedge_notional_usd=dex_hedge_notional_usd,
            maker_fee_usd=maker_fee_usd,
            dex_fee_bps=dex_fee_bps,
            net_pnl_usd=net_pnl_usd,
            trade_id=trade_id,
        )

    def get_summary(self) -> dict:
        return {
            "fill_count": len(self.fills),
            "realized_pnl_usd": round(self.realized_pnl_usd, 4),
            "quote_half_spread_bps": self.quote_half_spread_bps,
            "quote_size_usd": self.quote_size_usd,
            "last_fill": (
                {
                    "ts_utc": self.fills[-1].ts_utc.isoformat(),
                    "cex_side": self.fills[-1].cex_side,
                    "net_pnl_usd": round(self.fills[-1].net_pnl_usd, 4),
                }
                if self.fills
                else None
            ),
        }
