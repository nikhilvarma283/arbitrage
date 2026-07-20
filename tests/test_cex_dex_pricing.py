from src.amm_math import swap_exact_in
from src.cex_dex_pricing import compute_cex_dex_profit


def test_no_edge_when_dex_price_inside_cex_spread():
    # reserve_stable/reserve_algo = 0.10, squarely between bid/ask.
    result = compute_cex_dex_profit(
        cex_bid=0.099,
        cex_ask=0.101,
        reserve_algo=10_000_000,
        reserve_stable=1_000_000,
        dex_fee_bps=36,
        trade_size_usd=500,
        coinbase_fee_bps=60,
        algorand_network_fee_usd=0.003,
        breakeven_margin=0.05,
    )
    assert result is None


def test_dex_execution_price_includes_slippage_not_just_marginal_price():
    """The whole point of this fix: profit must come from the pool's real
    constant-product execution price, not its marginal spot price -- a
    thin pool should show materially worse profit than the naive
    spot-price-ratio calculation would report."""
    # Thin-ish pool: a $500 trade is a meaningful fraction of depth, so
    # slippage should be noticeable but shouldn't wipe out the edge.
    reserve_algo = 50_000  # implies spot price 0.10
    reserve_stable = 5_000

    result = compute_cex_dex_profit(
        cex_bid=0.085,
        cex_ask=0.086,  # DEX spot price (0.10) is well above cex_ask
        reserve_algo=reserve_algo,
        reserve_stable=reserve_stable,
        dex_fee_bps=36,
        trade_size_usd=500,
        coinbase_fee_bps=60,
        algorand_network_fee_usd=0.003,
        breakeven_margin=0.05,
    )
    assert result is not None
    assert result.direction == "buy_cex_sell_dex"

    # Naive (buggy) calculation: linear fee subtraction off the marginal
    # spot price, ignoring slippage entirely.
    dex_spot_price = reserve_stable / reserve_algo
    algo_amount = 500 / 0.086
    naive_gross = (dex_spot_price - 0.086) / 0.086
    naive_net = 500 * naive_gross - 500 * 0.006 - 500 * 0.0036

    # Real result must be materially worse than the naive one, because
    # selling algo_amount ALGO into a pool this thin moves the price.
    assert result.net_profit_usd < naive_net

    # And it must match swap_exact_in exactly (real execution accounting).
    expected_dex_proceeds = swap_exact_in(reserve_algo, reserve_stable, algo_amount, 36)
    expected_coinbase_cost = 500 + 500 * 0.006
    expected_net = expected_dex_proceeds - expected_coinbase_cost - 0.003
    assert abs(result.net_profit_usd - expected_net) < 1e-9


def test_deep_pool_thin_edge_gets_wiped_out_by_costs():
    """A tiny apparent edge against a deep pool should be eaten alive by
    Coinbase's 60bps taker fee plus the DEX fee -- this is exactly the
    kind of case the old linear model could get wrong in the other
    direction (reporting a "profit" too small to have survived real
    costs)."""
    result = compute_cex_dex_profit(
        cex_bid=0.0829,
        cex_ask=0.0830,
        reserve_algo=11_000_000,
        reserve_stable=915_000,  # spot price ~0.08318, barely above ask
        dex_fee_bps=36,
        trade_size_usd=500,
        coinbase_fee_bps=60,
        algorand_network_fee_usd=0.003,
        breakeven_margin=0.05,
    )
    # 60bps (coinbase) + 36bps (dex) = 96bps of cost against a spread
    # this small -- should not clear either the profit or the gate.
    assert result is None or not result.cleared_gate


def test_buy_dex_sell_cex_direction_uses_exact_in_on_stable_side():
    reserve_algo = 10_000_000
    reserve_stable = 800_000  # spot price 0.08, below cex_bid

    result = compute_cex_dex_profit(
        cex_bid=0.085,
        cex_ask=0.086,
        reserve_algo=reserve_algo,
        reserve_stable=reserve_stable,
        dex_fee_bps=36,
        trade_size_usd=500,
        coinbase_fee_bps=60,
        algorand_network_fee_usd=0.003,
        breakeven_margin=0.05,
    )
    assert result is not None
    assert result.direction == "buy_dex_sell_cex"

    expected_algo_amount = swap_exact_in(reserve_stable, reserve_algo, 500, 36)
    assert abs(result.algo_amount - expected_algo_amount) < 1e-9
