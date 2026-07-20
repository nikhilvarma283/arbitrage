"""Pure profit math for comparing a Coinbase price against a DEX pool.

Separated from src/main_v3.py so the actual cost/slippage accounting can
be unit-tested without spinning up the whole bot (algod client, ledger,
Flask app, etc.).
"""

from dataclasses import dataclass
from typing import Optional

from src.amm_math import swap_exact_in


@dataclass
class CexDexComparison:
    direction: str  # "buy_cex_sell_dex" or "buy_dex_sell_cex"
    dex_mid_price: float
    algo_amount: float
    net_profit_usd: float
    total_fee_frac: float
    total_fee_cost_usd: float
    cleared_gate: bool


def compute_cex_dex_profit(
    cex_bid: float,
    cex_ask: float,
    reserve_algo: float,
    reserve_stable: float,
    dex_fee_bps: float,
    trade_size_usd: float,
    coinbase_fee_bps: float,
    algorand_network_fee_usd: float,
    breakeven_margin: float,
) -> Optional[CexDexComparison]:
    """
    Real execution-price comparison: prices the DEX leg with constant-
    product slippage via swap_exact_in against the pool's actual current
    reserves, not its marginal spot price (reserve_stable/reserve_algo),
    which only holds for an infinitesimally small trade and understates
    cost for anything real. Also includes the (small but real) Algorand
    network fee, missing from the original version of this comparison.

    Returns None if there's no edge worth evaluating (DEX price sits
    inside Coinbase's own bid/ask spread).
    """
    dex_mid_price = reserve_stable / reserve_algo
    coinbase_fee_frac = coinbase_fee_bps / 10000

    if dex_mid_price > cex_ask:
        # Buy ALGO on Coinbase at ask, sell it into the DEX pool.
        direction = "buy_cex_sell_dex"
        algo_amount = trade_size_usd / cex_ask
        coinbase_cost_usd = trade_size_usd + trade_size_usd * coinbase_fee_frac
        dex_proceeds_usd = swap_exact_in(
            reserve_algo, reserve_stable, algo_amount, dex_fee_bps
        )
        net_profit_usd = dex_proceeds_usd - coinbase_cost_usd - algorand_network_fee_usd
    elif dex_mid_price < cex_bid:
        # Buy ALGO on the DEX, sell it on Coinbase at bid.
        direction = "buy_dex_sell_cex"
        algo_amount = swap_exact_in(
            reserve_stable, reserve_algo, trade_size_usd, dex_fee_bps
        )
        cex_gross_proceeds_usd = algo_amount * cex_bid
        cex_net_proceeds_usd = cex_gross_proceeds_usd * (1 - coinbase_fee_frac)
        net_profit_usd = (
            cex_net_proceeds_usd - trade_size_usd - algorand_network_fee_usd
        )
    else:
        return None

    if net_profit_usd <= 0:
        return None

    dex_fee_frac = dex_fee_bps / 10000
    total_fee_frac = dex_fee_frac + coinbase_fee_frac
    total_fee_cost_usd = trade_size_usd * total_fee_frac + algorand_network_fee_usd
    cleared_gate = net_profit_usd >= total_fee_cost_usd * breakeven_margin

    return CexDexComparison(
        direction=direction,
        dex_mid_price=dex_mid_price,
        algo_amount=algo_amount,
        net_profit_usd=net_profit_usd,
        total_fee_frac=total_fee_frac,
        total_fee_cost_usd=total_fee_cost_usd,
        cleared_gate=cleared_gate,
    )
