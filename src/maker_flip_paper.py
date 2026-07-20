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
- Requotes every tick (matching the poll cadence, currently ~10s) rather
  than continuously -- a real market maker would want much faster requote
  cycles, especially since DEX prices can move between polls.

Hedge latency / adverse selection: the hedge leg is priced using DEX
reserves observed `hedge_delay_seconds` after the CEX fill is detected,
not the same-instant reserves used to compute the quote. This matters a
lot -- a real CEX fill happens because the market just moved, and the
DEX price is likely moving with it, so the hedge you can actually place
a few seconds later (real submit + confirm time) is priced worse than
what was true at quote time. Pricing the hedge off the same snapshot
used for the quote (the original version of this code did) makes every
simulated fill deterministically profitable, which live trading will
not be.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.amm_math import swap_exact_in as _swap_exact_in
from src.amm_math import swap_exact_out as _swap_exact_out
from src.coinbase_feed import Trade

logger = logging.getLogger(__name__)


@dataclass
class PendingFill:
    """A simulated CEX fill awaiting its delayed DEX hedge."""

    ts_utc: datetime
    cex_side: str  # "buy_algo" or "sell_algo" (what we did on Coinbase)
    cex_price: float
    algo_amount: float
    cex_notional_usd: float
    maker_fee_usd: float
    trade_id: int


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
        hedge_delay_seconds: float = 5.0,
    ):
        # Needs to comfortably exceed dex_fee_bps (live, ~30-36bps for our
        # pools) plus maker_fee_bps for a filled round-trip to be
        # profitable at all -- see net_pnl_usd calculation below.
        self.quote_half_spread_bps = quote_half_spread_bps
        self.maker_fee_bps = maker_fee_bps
        self.quote_size_usd = quote_size_usd
        # Approximates real submit + on-chain confirmation time for the
        # hedge transaction (Algorand block time is ~2.8-3.4s; this adds
        # margin for detecting the fill and building/signing the swap).
        self.hedge_delay_seconds = hedge_delay_seconds

        self.last_seen_trade_id: Optional[int] = None
        self.pending_fills: List[PendingFill] = []
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
        Two jobs per call, in order:

        1. Settle any pending fills whose hedge_delay_seconds has elapsed,
           pricing the hedge against the CURRENT (later) reserves passed in
           here -- these reflect however much the DEX price has genuinely
           moved since the fill was detected.
        2. Detect any new fills from trades since the last tick, against
           quotes computed fresh from fair_value. New fills are queued as
           pending, NOT hedged immediately.

        Returns any fills newly settled in this call.
        """
        now = datetime.now(timezone.utc)
        new_fills = []

        still_pending = []
        for pending in self.pending_fills:
            elapsed = (now - pending.ts_utc).total_seconds()
            if elapsed >= self.hedge_delay_seconds:
                fill = self._settle_fill(
                    pending, dex_reserve_algo, dex_reserve_usd, dex_fee_bps
                )
                new_fills.append(fill)
                self.fills.append(fill)
                self.realized_pnl_usd += fill.net_pnl_usd
                logger.info(
                    f"Paper fill settled: {fill.cex_side} {fill.algo_amount:.2f} "
                    f"ALGO @{fill.cex_price:.6f} on Coinbase, hedged "
                    f"{elapsed:.1f}s later on DEX, net_pnl=${fill.net_pnl_usd:.4f}"
                )
            else:
                still_pending.append(pending)
        self.pending_fills = still_pending

        bid, ask = self.current_quotes(fair_value)
        for t in trades:
            if (
                self.last_seen_trade_id is not None
                and t.trade_id <= self.last_seen_trade_id
            ):
                continue

            pending_fill = None
            if t.side == "SELL" and t.price <= bid:
                # A real seller hit bids at/below ours -> our bid fills:
                # we buy ALGO at `bid`, and must hedge by selling it on the DEX.
                pending_fill = self._detect_fill(
                    cex_side="buy_algo", cex_price=bid, trade_id=t.trade_id
                )
            elif t.side == "BUY" and t.price >= ask:
                # A real buyer lifted asks at/above ours -> our ask fills:
                # we sell ALGO at `ask`, and must hedge by buying it on the DEX.
                pending_fill = self._detect_fill(
                    cex_side="sell_algo", cex_price=ask, trade_id=t.trade_id
                )

            if pending_fill:
                self.pending_fills.append(pending_fill)

            self.last_seen_trade_id = t.trade_id

        return new_fills

    def _detect_fill(
        self, cex_side: str, cex_price: float, trade_id: int
    ) -> PendingFill:
        """The CEX leg happens live (a real trade crossed our quote), so
        it's priced immediately. Only the DEX hedge leg is delayed."""
        algo_amount = self.quote_size_usd / cex_price
        cex_notional_usd = algo_amount * cex_price
        maker_fee_usd = cex_notional_usd * (self.maker_fee_bps / 10000)
        return PendingFill(
            ts_utc=datetime.now(timezone.utc),
            cex_side=cex_side,
            cex_price=cex_price,
            algo_amount=algo_amount,
            cex_notional_usd=cex_notional_usd,
            maker_fee_usd=maker_fee_usd,
            trade_id=trade_id,
        )

    def _settle_fill(
        self,
        pending: PendingFill,
        dex_reserve_algo: float,
        dex_reserve_usd: float,
        dex_fee_bps: float,
    ) -> PaperFill:
        if pending.cex_side == "buy_algo":
            # Now hold algo_amount ALGO from the CEX fill; hedge by selling
            # it into the DEX pool.
            dex_hedge_notional_usd = _swap_exact_in(
                dex_reserve_algo, dex_reserve_usd, pending.algo_amount, dex_fee_bps
            )
            net_pnl_usd = (
                dex_hedge_notional_usd
                - pending.cex_notional_usd
                - pending.maker_fee_usd
            )
        else:
            # Now owe algo_amount ALGO from the CEX fill (sold it); hedge
            # by buying exactly that amount from the DEX pool.
            dex_hedge_notional_usd = _swap_exact_out(
                dex_reserve_usd, dex_reserve_algo, pending.algo_amount, dex_fee_bps
            )
            net_pnl_usd = (
                pending.cex_notional_usd
                - dex_hedge_notional_usd
                - pending.maker_fee_usd
            )

        return PaperFill(
            ts_utc=pending.ts_utc,
            cex_side=pending.cex_side,
            cex_price=pending.cex_price,
            algo_amount=pending.algo_amount,
            cex_notional_usd=pending.cex_notional_usd,
            dex_hedge_notional_usd=dex_hedge_notional_usd,
            maker_fee_usd=pending.maker_fee_usd,
            dex_fee_bps=dex_fee_bps,
            net_pnl_usd=net_pnl_usd,
            trade_id=pending.trade_id,
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
