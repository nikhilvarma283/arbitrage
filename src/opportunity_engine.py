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

        Algorithm:
        1. For each configured pool pair (pool_a, pool_b):
           a. Compute spread: (price_b - price_a) / price_a
           b. Apply Gate 1: spread ≥ spread_gate_bps?
           c. Size trade using constant-product formula
           d. Apply Gate 2: expected_profit ≥ min_profit_usd?
           e. Apply Gate 3: size within [min_size, max_size]?
           f. Create Opportunity object
        2. Rank by expected_profit (descending)
        3. Return sorted list

        TODO:
        - Iterate through pool_pairs
        - Compute spread for each pair
        - Apply all gates
        - Size trades
        - Rank and return
        """
        # TODO: Implement
        raise NotImplementedError("detect_opportunities() must be implemented in Sprint 2.2")

    def compute_spread(self, pool_a: PoolState, pool_b: PoolState) -> float:
        """
        Compute spread between two pools in basis points.

        Spread = (price_rich - price_cheap) / price_cheap * 10000

        Args:
            pool_a: First pool
            pool_b: Second pool

        Returns:
            Spread in basis points (e.g., 55.0 = 0.55%)

        Formula:
        - price_a = reserve_b_a / reserve_a_a (asset_b per asset_a)
        - price_b = reserve_b_b / reserve_a_b
        - If price_a < price_b: spread = (price_b - price_a) / price_a
        - Else: spread = (price_a - price_b) / price_b

        TODO:
        - Extract prices from both pools
        - Compute spread
        - Return in basis points
        """
        # TODO: Implement
        raise NotImplementedError("compute_spread() must be implemented")

    def size_trade(
        self, pool_a: PoolState, pool_b: PoolState, spread_bps: float
    ) -> Tuple[Decimal, Decimal]:
        """
        Size an optimal trade using constant-product formula.

        Given a spread between two pools, compute the optimal amount to trade
        to maximize profit, subject to constraints.

        Constant Product Formula (pool A → pool B → profit):
        y = (reserve_b_A * X * (1 - fee_a)) / (reserve_a_A + X * (1 - fee_a))
        output = (reserve_a_B * y * (1 - fee_b)) / (reserve_b_B + y * (1 - fee_b))
        profit = X - output

        Where:
        - X = amount of asset_a to sell on pool A
        - y = amount of asset_b received from pool A
        - output = amount of asset_a received from pool B
        - profit = net profit in asset_a

        Optimal X: Use golden-section search or closed-form solution

        Args:
            pool_a: Cheaper pool (buy from here)
            pool_b: Richer pool (sell to here)
            spread_bps: Spread in basis points (for validation)

        Returns:
            (size_tokens, expected_profit_tokens)

        TODO:
        - Implement constant-product formula
        - Find optimal size using golden-section or closed-form
        - Apply safety margin (1.5%)
        - Return (size, profit)
        """
        # TODO: Implement
        raise NotImplementedError("size_trade() must be implemented")

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

        TODO:
        - Check spread gate
        - Check profit gate
        - Check size gates
        - Return result
        - Log discard reason if failed
        """
        # TODO: Implement
        raise NotImplementedError("_apply_gates() must be implemented")

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
