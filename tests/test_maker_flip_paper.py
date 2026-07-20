from datetime import datetime, timedelta, timezone

from src.coinbase_feed import Trade
from src.maker_flip_paper import MakerFlipPaperTrader, _swap_exact_in


def _trade(trade_id, price, side, seconds_ago=0):
    return Trade(
        trade_id=trade_id,
        price=price,
        size=1000,
        side=side,
        time=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    )


def test_fill_is_not_settled_in_the_same_tick():
    trader = MakerFlipPaperTrader(hedge_delay_seconds=5.0)

    # fair_value=0.10 -> bid=0.0992, ask=0.1008 (80bps half-spread).
    # A SELL at 0.09 crosses our bid -> should be detected, not settled yet.
    fills = trader.tick(
        fair_value=0.10,
        trades=[_trade(1, 0.09, "SELL")],
        dex_reserve_algo=10_000_000,
        dex_reserve_usd=1_000_000,
        dex_fee_bps=36,
    )

    assert fills == []
    assert len(trader.pending_fills) == 1
    assert trader.realized_pnl_usd == 0.0


def test_fill_settles_only_after_hedge_delay_elapses():
    trader = MakerFlipPaperTrader(hedge_delay_seconds=5.0)
    trader.tick(
        fair_value=0.10,
        trades=[_trade(1, 0.09, "SELL")],
        dex_reserve_algo=10_000_000,
        dex_reserve_usd=1_000_000,
        dex_fee_bps=36,
    )

    # Force the pending fill to look older than hedge_delay_seconds.
    trader.pending_fills[0].ts_utc = datetime.now(timezone.utc) - timedelta(seconds=6)

    fills = trader.tick(
        fair_value=0.10,
        trades=[],
        dex_reserve_algo=10_000_000,
        dex_reserve_usd=1_000_000,
        dex_fee_bps=36,
    )

    assert len(fills) == 1
    assert trader.pending_fills == []
    assert trader.realized_pnl_usd == fills[0].net_pnl_usd


def test_hedge_uses_reserves_at_settlement_not_detection():
    """The whole point of the fix: if the DEX price moves between fill
    detection and settlement, the hedge must reflect the LATER reserves,
    not the snapshot used to compute the original quote."""
    trader = MakerFlipPaperTrader(hedge_delay_seconds=5.0)

    detection_reserve_algo = 10_000_000
    detection_reserve_usd = 1_000_000  # implies DEX price 0.10

    trader.tick(
        fair_value=0.10,
        trades=[_trade(1, 0.09, "SELL")],  # crosses bid -> buy_algo pending
        dex_reserve_algo=detection_reserve_algo,
        dex_reserve_usd=detection_reserve_usd,
        dex_fee_bps=36,
    )
    pending = trader.pending_fills[0]
    pending.ts_utc = datetime.now(timezone.utc) - timedelta(seconds=6)

    # DEX price has since dropped (more ALGO reserve, less USD reserve) --
    # a worse price for a hedge that sells ALGO into the pool.
    later_reserve_algo = 10_100_000
    later_reserve_usd = 990_000

    fills = trader.tick(
        fair_value=0.098,
        trades=[],
        dex_reserve_algo=later_reserve_algo,
        dex_reserve_usd=later_reserve_usd,
        dex_fee_bps=36,
    )

    assert len(fills) == 1
    fill = fills[0]

    expected_hedge_notional = _swap_exact_in(
        later_reserve_algo, later_reserve_usd, fill.algo_amount, 36
    )
    assert fill.dex_hedge_notional_usd == expected_hedge_notional

    # Sanity: hedging at the detection-time reserves would have given a
    # different (better, since price hadn't dropped yet) result.
    stale_hedge_notional = _swap_exact_in(
        detection_reserve_algo, detection_reserve_usd, fill.algo_amount, 36
    )
    assert stale_hedge_notional != expected_hedge_notional


def test_quote_computation_unaffected_by_hedge_delay():
    trader = MakerFlipPaperTrader(quote_half_spread_bps=80.0)
    bid, ask = trader.current_quotes(0.10)
    assert round(bid, 6) == 0.0992
    assert round(ask, 6) == 0.1008
