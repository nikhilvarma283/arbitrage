"""Real constant-product (x*y=k) AMM swap math, shared by anything that
needs an actual execution price rather than a pool's marginal spot price
(reserve_b/reserve_a) -- the spot price understates cost for any real
trade size, since it ignores slippage entirely.
"""


def swap_exact_in(
    reserve_in: float, reserve_out: float, amount_in: float, fee_bps: float
) -> float:
    """Given amount_in, what's received."""
    amount_in_after_fee = amount_in * (1 - fee_bps / 10000)
    k = reserve_in * reserve_out
    new_reserve_in = reserve_in + amount_in_after_fee
    new_reserve_out = k / new_reserve_in
    return reserve_out - new_reserve_out


def swap_exact_out(
    reserve_in: float, reserve_out: float, amount_out: float, fee_bps: float
) -> float:
    """Input required for a fixed amount_out."""
    if amount_out >= reserve_out:
        raise ValueError("Cannot swap out more than the pool's available reserve")
    k = reserve_in * reserve_out
    new_reserve_out = reserve_out - amount_out
    new_reserve_in = k / new_reserve_out
    amount_in_after_fee = new_reserve_in - reserve_in
    return amount_in_after_fee / (1 - fee_bps / 10000)
