"""
Cycle Detection Engine - Direct & Triangular Arbitrage

Detects arbitrage opportunities:
1. Direct pairs: same asset pair on different DEXes
2. Triangular: 3-hop cycles (max 3 hops per CHANGE 5)

Filters by:
- Spread gate (55bps default)
- Fee breakeven: computed dynamically per-cycle from the real, live fee_bps
  of whichever pools are actually involved, plus a required margin beyond
  breakeven (breakeven_margin, default 5% of the real fee cost) -- not a
  static two_hop/three_hop bps assumption
- Min profit ($0.75 per CHANGE 7)
"""

import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from itertools import combinations, permutations

logger = logging.getLogger(__name__)


@dataclass
class Cycle:
    """Arbitrage cycle (direct or triangular)."""
    hops: int  # 2 or 3
    pools: List[int]  # List of pool app_ids
    path: List[Tuple[int, int]]  # List of (asset_a, asset_b) pairs
    dexes: List[str]  # DEX names for each hop
    raw_spread_log: float  # Pre-fee log gain
    fee_stack_log: float  # Sum of hop fees as log
    net_profit_log: float  # raw_spread - fee_stack
    optimal_size_usdc: float  # Golden section optimized size
    net_profit_usd: float  # Estimated profit at optimal size
    route_id: str  # Unique identifier


class CycleDetector:
    """Detects direct and triangular arbitrage cycles."""

    def __init__(self, pools_config: Dict, gates: Dict):
        """
        Initialize cycle detector.

        Args:
            pools_config: pools.lock.json loaded config
            gates: Gate thresholds (spread_gate_bps, breakeven_margin, min_profit_usd)
        """
        self.pools_config = pools_config
        self.gates = gates

        # Extract gate parameters
        self.spread_gate_bps = gates.get("spread_gate_bps", 55)

        # Breakeven is computed dynamically per-cycle from the real, live
        # fee_bps of whichever specific pools are involved (Tinyman pools
        # currently charge 36bps, not the 30bps a route might assume; a
        # 3-hop route mixing DEXes has a different total cost than an
        # all-Tinyman one) rather than a static two_hop/three_hop bps
        # constant. breakeven_margin is the required cushion *beyond*
        # breakeven, as a fraction of the real fee cost -- e.g. 0.05 means
        # net gain must be at least 5% of what was actually paid in fees,
        # equivalently gross gain must be at least 1.05x the fee cost.
        self.breakeven_margin = gates.get("breakeven_margin", 0.05)
        self.min_profit_usd = gates.get("min_profit_usd", 0.75)

        # Pools with thin reserves (an abandoned pool, or one that just
        # never attracted liquidity) produce implied prices that are
        # meaningless at the $500 notional size this bot assumes, and get
        # wildly amplified by the simplified linear-slippage profit model
        # below. Confirmed live: a Pact USDC/USDT pool with genuine but tiny
        # on-chain reserves (~36 USDC / ~333 USDT, a few hundred dollars
        # total) produced a "raw" spread vs Tinyman's much deeper USDC/USDT
        # pool that the linear model turned into a $3,700+ "profit" estimate
        # on a $500 trade -- not a bug in the math, just real data from an
        # illiquid pool being fed into a model that assumes real depth.
        # Require both sides of a pool to hold at least this many raw base
        # units (default 100,000,000 -- i.e. 100.0 tokens for any 6-decimal
        # asset) before it's eligible for cycle detection at all.
        self.min_pool_reserve_raw = gates.get("min_pool_reserve_raw", 100_000_000)

        # Build pool lookup
        self.pools_by_id = {}  # app_id -> pool_info
        self.pools_by_assets = {}  # (asset_a, asset_b) -> [pool_info, ...]
        self._build_pool_indices()

        logger.info(f"CycleDetector initialized with {len(self.pools_by_id)} pools")

    def _build_pool_indices(self) -> None:
        """Build lookup indices for pools."""
        for dex, dex_pools in self.pools_config.get("dexes", {}).items():
            for pair_key, pool_info in dex_pools.items():
                if not isinstance(pool_info, dict) or not pool_info.get("app_id"):
                    continue

                app_id = pool_info["app_id"]
                asset_a = pool_info.get("asset_a")
                asset_b = pool_info.get("asset_b")

                # Add to pool lookup
                self.pools_by_id[app_id] = pool_info

                # Add to asset lookup (both directions)
                key_ab = (asset_a, asset_b)
                key_ba = (asset_b, asset_a)

                if key_ab not in self.pools_by_assets:
                    self.pools_by_assets[key_ab] = []
                self.pools_by_assets[key_ab].append((app_id, dex, False))  # False = not reversed

                if key_ba not in self.pools_by_assets:
                    self.pools_by_assets[key_ba] = []
                self.pools_by_assets[key_ba].append((app_id, dex, True))  # True = reversed

    def detect_cycles(self, pool_states: List) -> List[Cycle]:
        """
        Detect all arbitrage cycles from current pool states.

        Args:
            pool_states: List of PoolState objects

        Returns:
            List of profitable Cycle objects
        """
        cycles = []

        liquid_states = [
            ps for ps in pool_states
            if ps.reserve_a >= self.min_pool_reserve_raw and ps.reserve_b >= self.min_pool_reserve_raw
        ]
        dust_excluded = len(pool_states) - len(liquid_states)
        if dust_excluded:
            logger.info(f"Excluded {dust_excluded} dust pool(s) below min_pool_reserve_raw={self.min_pool_reserve_raw}")

        # Detect direct pairs (2-hop)
        direct_cycles = self._detect_direct_pairs(liquid_states)
        cycles.extend(direct_cycles)

        # Detect triangular cycles (3-hop)
        triangular_cycles = self._detect_triangular(liquid_states)
        cycles.extend(triangular_cycles)

        logger.info(f"Detected {len(cycles)} cycles (direct: {len(direct_cycles)}, triangular: {len(triangular_cycles)})")

        return cycles

    def _detect_direct_pairs(self, pool_states: List) -> List[Cycle]:
        """Detect same-pair cycles across different DEXes (2-hop)."""
        cycles = []

        # Group pools by asset pair
        pairs_dict = {}
        for pool_state in pool_states:
            key = (pool_state.asset_a, pool_state.asset_b)
            if key not in pairs_dict:
                pairs_dict[key] = []
            pairs_dict[key].append(pool_state)

        # Find pairs with >1 pool (different DEXes)
        for pair, pools in pairs_dict.items():
            if len(pools) < 2:
                continue

            # Compare each pair of pools
            for i in range(len(pools)):
                for j in range(i + 1, len(pools)):
                    pool_a = pools[i]
                    pool_b = pools[j]

                    # Calculate spread. Signed spread_log tells us which
                    # direction is profitable; the achievable gross gain
                    # from trading in that direction is its magnitude.
                    spread_log = pool_a.log_rate - pool_b.log_rate
                    gross_gain_log = abs(spread_log)
                    spread_bps = gross_gain_log * 10000  # Convert to basis points

                    # Check gates
                    if spread_bps < self.spread_gate_bps:
                        continue

                    # Real, per-pool fee cost for this specific route (not a
                    # static assumption) -- both fee_a_log/fee_b_log are
                    # negative (ln of something < 1).
                    fee_a_log = math.log(1 - pool_a.fee_bps / 10000)
                    fee_b_log = math.log(1 - pool_b.fee_bps / 10000)
                    total_fee_log = fee_a_log + fee_b_log  # Pay fee on both swaps
                    fee_cost_log = -total_fee_log  # positive magnitude of real cost

                    # Fees reduce net gain -> add the (negative) fee log.
                    net_spread_log = gross_gain_log + total_fee_log

                    # Dynamic breakeven: net gain must clear the real fee
                    # cost by at least breakeven_margin (e.g. 5% of cost).
                    if net_spread_log < fee_cost_log * self.breakeven_margin:
                        continue

                    # Estimate profit (simplified - would use golden section in real code)
                    net_profit_usd = self._estimate_profit_usd(net_spread_log, 500)  # Base size 500 USDC

                    if net_profit_usd < self.min_profit_usd:
                        continue

                    # Create cycle
                    cycle = Cycle(
                        hops=2,
                        pools=[pool_a.pool_id, pool_b.pool_id],
                        path=[(pair[0], pair[1]), (pair[1], pair[0])],
                        dexes=[pool_a.dex, pool_b.dex],
                        raw_spread_log=gross_gain_log,
                        fee_stack_log=total_fee_log,
                        net_profit_log=net_spread_log,
                        optimal_size_usdc=500,  # Would calculate with golden section
                        net_profit_usd=net_profit_usd,
                        route_id=f"D2_{pool_a.pool_id}_{pool_b.pool_id}",
                    )

                    cycles.append(cycle)

        return cycles

    def _detect_triangular(self, pool_states: List) -> List[Cycle]:
        """Detect 3-hop triangular cycles (max 3 hops per CHANGE 5)."""
        cycles = []

        # Get unique assets in pools
        assets = set()
        for pool_state in pool_states:
            assets.add(pool_state.asset_a)
            assets.add(pool_state.asset_b)

        # Try all 3-asset combinations
        for triplet in combinations(assets, 3):
            # Try all permutations (different cycle directions)
            for path in permutations(triplet):
                # Path is (A, B, C) - cycle is A->B->C->A
                a, b, c = path

                # Find pools for each hop
                hop1_pools = self.pools_by_assets.get((a, b), [])
                hop2_pools = self.pools_by_assets.get((b, c), [])
                hop3_pools = self.pools_by_assets.get((c, a), [])

                if not (hop1_pools and hop2_pools and hop3_pools):
                    continue

                # Try combinations of pools from different DEXes
                for pool1_info in hop1_pools:
                    for pool2_info in hop2_pools:
                        for pool3_info in hop3_pools:
                            pool1_id, dex1, rev1 = pool1_info
                            pool2_id, dex2, rev2 = pool2_info
                            pool3_id, dex3, rev3 = pool3_info

                            # Find actual pool states
                            ps1 = next((p for p in pool_states if p.pool_id == pool1_id), None)
                            ps2 = next((p for p in pool_states if p.pool_id == pool2_id), None)
                            ps3 = next((p for p in pool_states if p.pool_id == pool3_id), None)

                            if not (ps1 and ps2 and ps3):
                                continue

                            # log_rate = ln(reserve_a/reserve_b) is only the
                            # log-gain for traversing a pool in its own
                            # asset_a -> asset_b direction when reversed is
                            # True (i.e. this hop's (from,to) matched the
                            # pool's (asset_b, asset_a), meaning we're
                            # actually going asset_b -> asset_a = the pool's
                            # native a/b order). When reversed is False, this
                            # hop travels asset_a -> asset_b in the pool's
                            # own terms, which is the *inverse* rate, so the
                            # log-gain is -log_rate. Without this correction
                            # roughly half of all traversals get the wrong
                            # sign, which silently produced wildly incorrect
                            # "profit" estimates (thousands of dollars on a
                            # $500 notional) for triangular cycles.
                            hop1_log = ps1.log_rate if rev1 else -ps1.log_rate
                            hop2_log = ps2.log_rate if rev2 else -ps2.log_rate
                            hop3_log = ps3.log_rate if rev3 else -ps3.log_rate

                            # Calculate cycle gain
                            cycle_log = hop1_log + hop2_log + hop3_log

                            # Fee stack: real, per-pool fee cost for this
                            # specific route (Tinyman-heavy routes cost more
                            # than a route touching Pact's lower-fee pool).
                            fee_log = (
                                math.log(1 - ps1.fee_bps / 10000) +
                                math.log(1 - ps2.fee_bps / 10000) +
                                math.log(1 - ps3.fee_bps / 10000)
                            )
                            fee_cost_log = -fee_log  # positive magnitude of real cost

                            net_log = cycle_log + fee_log  # Log domain: multiply is add

                            # Check gates
                            if abs(cycle_log) < math.log(1 + self.spread_gate_bps / 10000):
                                continue

                            # Dynamic breakeven: net gain must clear the real
                            # fee cost by at least breakeven_margin (e.g. 5%
                            # of cost), rather than a static three_hop bps
                            # assumption that doesn't reflect this route's
                            # actual pools (e.g. an all-Tinyman loop costs
                            # ~108bps at today's live fees, not the 90bps a
                            # static config value might assume).
                            if net_log < fee_cost_log * self.breakeven_margin:
                                continue

                            net_profit_usd = self._estimate_profit_usd(net_log, 500)

                            if net_profit_usd < self.min_profit_usd:
                                continue

                            # Create cycle
                            cycle = Cycle(
                                hops=3,
                                pools=[pool1_id, pool2_id, pool3_id],
                                path=[(a, b), (b, c), (c, a)],
                                dexes=[dex1, dex2, dex3],
                                raw_spread_log=cycle_log,
                                fee_stack_log=fee_log,
                                net_profit_log=net_log,
                                optimal_size_usdc=500,
                                net_profit_usd=net_profit_usd,
                                route_id=f"T3_{pool1_id}_{pool2_id}_{pool3_id}",
                            )

                            cycles.append(cycle)

        return cycles

    def _estimate_profit_usd(self, net_gain_log: float, base_size_usdc: float) -> float:
        """
        Estimate profit in USD from log gain.

        Simplified: assumes linear slippage (actual would use constant product curve).
        """
        if net_gain_log <= 0:
            return 0

        gain_pct = (math.exp(net_gain_log) - 1) * 100  # Convert to percentage

        return base_size_usdc * gain_pct / 100
