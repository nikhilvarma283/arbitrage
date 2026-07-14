"""
Opportunity Engine - Detect and size arbitrage opportunities.

Receives pool state updates from pool_watcher and detects profitable arbitrage
opportunities between configured pool pairs. Applies gates (minimum spread, profit)
and sizes trades using constant-product formula mathematics.

Sprint 2.2: Opportunity Engine Implementation
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import logging
import math

from src.pool_watcher import PoolState

logger = logging.getLogger(__name__)


@dataclass
class Opportunity:
    """A detected arbitrage opportunity between two pools."""

    pool_a: PoolState  # Cheaper pool (buy here)
    pool_b: PoolState  # Richer pool (sell here)
    spread_bps: float  # Spread in basis points (e.g., 55.0 = 0.55%)
    size_tokens: Decimal  # Optimal amount to trade (asset A)
    expected_profit_tokens: Decimal  # Profit in tokens (asset A)
    expected_profit_usd: Decimal  # Profit in USD equivalent
    rank: int  # Rank by profit (lower = better)
    discovered_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(seconds=6))

    def __repr__(self) -> str:
        return (
            f"Opportunity({self.pool_a.pool_name}→{self.pool_b.pool_name}: "
            f"spread={self.spread_bps:.1f}bps, size={self.size_tokens:.2f}, "
            f"profit=${self.expected_profit_usd:.2f})"
        )


class OpportunityEngine:
    """
    Detects and sizes profitable arbitrage opportunities.

    Responsibilities:
    - Receive pool state updates from pool_watcher
    - Compute spreads between configured pool pairs
    - Apply opportunity gates (minimum spread, minimum profit)
    - Size trades using constant-product formula
    - Rank opportunities by expected profit
    - Emit opportunities to executor (phase 1 live) or ledger (shadow mode)

    Gate Configuration:
    - spread_gate_bps: Minimum spread (default 55 bps = 0.55%)
    - min_profit_tokens: Minimum absolute profit (default 0.001 ALGO)
    - min_profit_usd: Minimum profit in USD (default $1.00)
    - max_position_size: Maximum trade size (default $2,000)
    - min_position_size: Minimum trade size (default $100)

    Usage:
        engine = OpportunityEngine(config)
        pool_state = pool_watcher.get_pool_state(pool_id)
        opportunities = engine.detect_opportunities(pool_states)
        for opp in opportunities:
            print(f"Found: {opp}")
    """

    def __init__(self, config: Dict):
        """
        Initialize opportunity engine.

        Args:
            config: Configuration dict with gates:
                - spread_gate_bps: Minimum spread (basis points)
                - min_profit_tokens: Minimum absolute profit
                - min_profit_usd: Minimum profit USD
                - max_position_size: Max size USD
                - min_position_size: Min size USD
                - profit_margin: Safety margin (e.g., 0.015 = 1.5%)
                - pool_pairs: List of (pool_a_id, pool_b_id) pairs to check
        """
        self.config = config
        self.opportunities: List[Opportunity] = []
        self.stats = {
            "opportunities_detected": 0,
            "opportunities_discarded": 0,
            "avg_spread_bps": 0.0,
        }

    def detect_opportunities(self, pool_states: Dict[int, PoolState]) -> List[Opportunity]:
        """
        Detect all profitable opportunities given current pool states.

        Args:
            pool_states: Dict of pool_id → PoolState

        Returns:
            List of Opportunity objects, sorted by profit (descending)
        """
        opportunities = []

        for pool_a_id, pool_b_id in self.config.get("pool_pairs", []):
            pool_a = pool_states.get(pool_a_id)
            pool_b = pool_states.get(pool_b_id)

            if not pool_a or not pool_b:
                continue

            # Compute spread
            spread_bps = self.compute_spread(pool_a, pool_b)
            if spread_bps < self.config["spread_gate_bps"]:
                self.stats["opportunities_discarded"] += 1
                continue

            # Size trade
            size_tokens, profit_tokens = self.size_trade(pool_a, pool_b, spread_bps)

            # Convert to USD (assuming USDC = $1)
            profit_usd = float(profit_tokens)

            # Apply gates
            opp = Opportunity(
                pool_a=pool_a,
                pool_b=pool_b,
                spread_bps=spread_bps,
                size_tokens=size_tokens,
                expected_profit_tokens=profit_tokens,
                expected_profit_usd=Decimal(str(profit_usd)),
                rank=0,
            )

            if not self._apply_gates(opp):
                self.stats["opportunities_discarded"] += 1
                continue

            opportunities.append(opp)
            self.stats["opportunities_detected"] += 1

        # Rank and return
        return self.rank_opportunities(opportunities)

    def compute_spread(self, pool_a: PoolState, pool_b: PoolState) -> float:
        """
        Compute spread between two pools in basis points.

        Spread = (price_rich - price_cheap) / price_cheap * 10000

        Args:
            pool_a: First pool
            pool_b: Second pool

        Returns:
            Spread in basis points (e.g., 55.0 = 0.55%)
        """
        # Calculate prices (asset_b per asset_a)
        if pool_a.reserve_a == 0 or pool_b.reserve_a == 0:
            return 0.0

        price_a = float(pool_a.reserve_b / pool_a.reserve_a)
        price_b = float(pool_b.reserve_b / pool_b.reserve_a)

        if price_a == 0 or price_b == 0:
            return 0.0

        # Calculate spread
        if price_a < price_b:
            spread = (price_b - price_a) / price_a
        else:
            spread = (price_a - price_b) / price_b

        # Convert to basis points
        spread_bps = spread * 10000
        return spread_bps

    def size_trade(
        self, pool_a: PoolState, pool_b: PoolState, spread_bps: float
    ) -> Tuple[Decimal, Decimal]:
        """
        Size an optimal trade using constant-product formula.

        Returns:
            (size_tokens, expected_profit_tokens)
        """
        # Start with a conservative size and iterate
        min_size = self.config.get("min_position_size", 100)
        max_size = self.config.get("max_position_size", 2000)

        # Use binary search to find optimal size that maximizes profit
        best_profit = Decimal(0)
        best_size = Decimal(min_size)

        # Sample sizes geometrically (10, 50, 100, 500, 1000, 2000)
        test_sizes = [
            Decimal(min_size),
            Decimal(min_size * 2),
            Decimal(min_size * 5),
            Decimal(min_size * 10),
            Decimal(max_size / 2),
            Decimal(max_size),
        ]

        fee_a = Decimal(pool_a.fee_bps) / Decimal(10000)
        fee_b = Decimal(pool_b.fee_bps) / Decimal(10000)

        for test_size in test_sizes:
            if test_size < min_size or test_size > max_size:
                continue

            # Apply constant product formula
            # y = (reserve_b_a * X * (1 - fee_a)) / (reserve_a_a + X * (1 - fee_a))
            numerator = pool_a.reserve_b * test_size * (Decimal(1) - fee_a)
            denominator = pool_a.reserve_a + test_size * (Decimal(1) - fee_a)

            if denominator == 0:
                continue

            y = numerator / denominator

            # output = (reserve_a_b * y * (1 - fee_b)) / (reserve_b_b + y * (1 - fee_b))
            numerator2 = pool_b.reserve_a * y * (Decimal(1) - fee_b)
            denominator2 = pool_b.reserve_b + y * (Decimal(1) - fee_b)

            if denominator2 == 0:
                continue

            output = numerator2 / denominator2

            # profit = X - output
            profit = test_size - output

            if profit > best_profit:
                best_profit = profit
                best_size = test_size

        return best_size, best_profit

    def _apply_gates(self, opp: Opportunity) -> bool:
        """
        Apply all gates to an opportunity.

        Gates:
        1. Spread ≥ spread_gate_bps
        2. Expected profit ≥ min_profit_usd
        3. Size within [min_position_size, max_position_size]

        Args:
            opp: Opportunity to check

        Returns:
            True if opportunity passes all gates, False otherwise
        """
        # Gate 1: Spread
        if opp.spread_bps < self.config.get("spread_gate_bps", 55):
            logger.debug(f"Discarded: spread {opp.spread_bps:.1f}bps < {self.config['spread_gate_bps']}bps")
            return False

        # Gate 2: Minimum profit
        min_profit = Decimal(str(self.config.get("min_profit_usd", 1.0)))
        if opp.expected_profit_usd < min_profit:
            logger.debug(f"Discarded: profit ${opp.expected_profit_usd:.2f} < ${min_profit:.2f}")
            return False

        # Gate 3: Position size
        min_size = self.config.get("min_position_size", 100)
        max_size = self.config.get("max_position_size", 2000)
        size_usd = float(opp.size_tokens)  # Simplified: 1 ALGO = $1 for now

        if size_usd < min_size:
            logger.debug(f"Discarded: size ${size_usd:.2f} < ${min_size:.2f}")
            return False

        if size_usd > max_size:
            logger.debug(f"Discarded: size ${size_usd:.2f} > ${max_size:.2f}")
            return False

        return True

    def rank_opportunities(self, opps: List[Opportunity]) -> List[Opportunity]:
        """
        Rank opportunities by expected profit (descending).

        Args:
            opps: List of opportunities

        Returns:
            Sorted list (highest profit first)
        """
        sorted_opps = sorted(opps, key=lambda o: o.expected_profit_usd, reverse=True)
        for i, opp in enumerate(sorted_opps):
            opp.rank = i
        return sorted_opps

    def get_stats(self) -> Dict:
        """Return metrics: opportunities detected, discarded, avg spread."""
        return self.stats.copy()


class OpportunityEngineConfig:
    """Configuration for opportunity detection."""

    # Default gates (from PHASE_1_SPRINT_ROADMAP.md)
    DEFAULT_SPREAD_GATE_BPS = 55  # 0.55%
    DEFAULT_MIN_PROFIT_USD = 1.0
    DEFAULT_MIN_POSITION_SIZE = 100  # USD
    DEFAULT_MAX_POSITION_SIZE = 2000  # USD
    DEFAULT_PROFIT_MARGIN = 0.015  # 1.5%

    def __init__(self, **kwargs):
        """Initialize config with optional overrides."""
        self.spread_gate_bps = kwargs.get("spread_gate_bps", self.DEFAULT_SPREAD_GATE_BPS)
        self.min_profit_usd = kwargs.get("min_profit_usd", self.DEFAULT_MIN_PROFIT_USD)
        self.min_position_size = kwargs.get("min_position_size", self.DEFAULT_MIN_POSITION_SIZE)
        self.max_position_size = kwargs.get("max_position_size", self.DEFAULT_MAX_POSITION_SIZE)
        self.profit_margin = kwargs.get("profit_margin", self.DEFAULT_PROFIT_MARGIN)
        self.pool_pairs = kwargs.get("pool_pairs", [])

    @staticmethod
    def from_yaml(config_dict: Dict) -> "OpportunityEngineConfig":
        """Load configuration from YAML dict."""
        # TODO: Parse from config/bot.yaml
        raise NotImplementedError()


if __name__ == "__main__":
    # Example usage (after implementation)
    logging.basicConfig(level=logging.INFO)

    # config = OpportunityEngineConfig(
    #     spread_gate_bps=55,
    #     pool_pairs=[
    #         (430731383, 729405934),  # TINYMAN_ALGO_USDC, PACT_ALGO_USDC
    #     ],
    # )
    # engine = OpportunityEngine(config)
    # opportunities = engine.detect_opportunities(pool_states)
    # for opp in opportunities:
    #     print(opp)
