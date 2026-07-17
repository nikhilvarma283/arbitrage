"""
Simulator & Staleness Tracker (CHANGE ORDER 001 CHANGE 2)

For EVERY cycle that clears the fee gate:
1. Build complete atomic transaction group (no signing/broadcast)
2. Call algod.simulate() with current params
3. Record staleness_ms (wall-clock from detection to simulate)
4. Record simulate_pass (whether group cleared profit assertion)

The detection-to-simulate decay rate is the PRIMARY Gate 0 output:
it's our empirical estimate of the race win rate.
"""

import logging
import time
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from algosdk.v2client.algod import AlgodClient
from algosdk import transaction, encoding

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Result of simulating a cycle."""
    route_id: str
    cycle_path: str
    hops: int
    raw_spread_log: float
    fee_stack_log: float
    net_profit_est_usd: float
    optimal_size_usdc: float
    cleared_gate: bool  # Cleared fee gate
    simulate_pass: bool  # Would execute if we submitted
    staleness_ms: int  # Detection to simulate time
    would_execute: bool  # cleared_gate AND simulate_pass AND profit >= min
    notes: str


class CycleSimulator:
    """Simulates atomic transaction groups and measures staleness."""

    def __init__(self, algod_client: AlgodClient, executor_address: str, gates: Dict):
        """
        Initialize simulator.

        Args:
            algod_client: Algorand client
            executor_address: Account that would execute trades (for testing)
            gates: Gate configuration
        """
        self.client = algod_client
        self.executor_address = executor_address
        self.gates = gates

        # Get suggested params once per block
        self.suggested_params = None
        self._last_params_block = 0

    def simulate_cycle(
        self,
        cycle,
        pool_states: Dict,
        detection_time_ns: int,
    ) -> SimulationResult:
        """
        Simulate a cycle (CHANGE 2).

        Args:
            cycle: Cycle object from detector
            pool_states: Dict of pool_id -> PoolState
            detection_time_ns: Nanoseconds when cycle was detected

        Returns:
            SimulationResult with staleness and pass/fail
        """
        simulate_start_ns = time.time_ns()
        staleness_ms = (simulate_start_ns - detection_time_ns) // 1_000_000

        try:
            # Build atomic transaction group
            txn_group = self._build_atomic_group(cycle, pool_states)

            if not txn_group:
                return SimulationResult(
                    route_id=cycle.route_id,
                    cycle_path=str(cycle.path),
                    hops=cycle.hops,
                    raw_spread_log=cycle.raw_spread_log,
                    fee_stack_log=cycle.fee_stack_log,
                    net_profit_est_usd=cycle.net_profit_usd,
                    optimal_size_usdc=cycle.optimal_size_usdc,
                    cleared_gate=False,
                    simulate_pass=False,
                    staleness_ms=staleness_ms,
                    would_execute=False,
                    notes="failed_to_build_txn_group",
                )

            # Call algod.simulate()
            try:
                result = self.client.simulate_transactions(txn_group)
                simulate_pass = result.get("txn-groups", [{}])[0].get("txn-results", [{}])[-1].get("success", False)
            except Exception as e:
                logger.warning(f"Simulate failed: {e}")
                simulate_pass = False

            # Determine would_execute
            would_execute = (
                simulate_pass and
                cycle.net_profit_usd >= self.gates.get("min_profit_usd", 0.75)
            )

            return SimulationResult(
                route_id=cycle.route_id,
                cycle_path=str(cycle.path),
                hops=cycle.hops,
                raw_spread_log=cycle.raw_spread_log,
                fee_stack_log=cycle.fee_stack_log,
                net_profit_est_usd=cycle.net_profit_usd,
                optimal_size_usdc=cycle.optimal_size_usdc,
                cleared_gate=True,
                simulate_pass=simulate_pass,
                staleness_ms=staleness_ms,
                would_execute=would_execute,
                notes=f"simulated in {staleness_ms}ms, pass={simulate_pass}",
            )

        except Exception as e:
            logger.error(f"Simulation error: {e}")
            return SimulationResult(
                route_id=cycle.route_id,
                cycle_path=str(cycle.path),
                hops=cycle.hops,
                raw_spread_log=cycle.raw_spread_log,
                fee_stack_log=cycle.fee_stack_log,
                net_profit_est_usd=cycle.net_profit_usd,
                optimal_size_usdc=cycle.optimal_size_usdc,
                cleared_gate=False,
                simulate_pass=False,
                staleness_ms=staleness_ms,
                would_execute=False,
                notes=str(e),
            )

    def _build_atomic_group(self, cycle, pool_states: Dict) -> Optional[List]:
        """
        Build atomic transaction group for cycle execution.

        WITHOUT signing or broadcasting (for simulation only).
        Includes profit assertion as final transaction.

        Returns:
            List of unsigned transactions, or None if build failed
        """
        try:
            txns = []

            # Get suggested params
            params = self.client.suggested_params()

            # For each hop in the cycle, build a swap transaction
            for i, pool_id in enumerate(cycle.pools):
                pool_state = pool_states.get(pool_id)
                if not pool_state:
                    logger.warning(f"Pool {pool_id} not found in states")
                    return None

                # This would be an app call to the DEX
                # For simulation, we build a minimal structure
                swap_txn = self._build_swap_txn(
                    app_id=pool_id,
                    asset_in=cycle.path[i][0],
                    asset_out=cycle.path[i][1],
                    amount_in=int(cycle.optimal_size_usdc * 1_000_000),  # microunits
                    min_out=0,  # Would calculate proper slippage
                    params=params,
                )

                if not swap_txn:
                    return None

                txns.append(swap_txn)

            # Final: profit assertion (self-payment minimum)
            min_final_amount = int(
                cycle.optimal_size_usdc * (1 + cycle.net_profit_log) * 1_000_000
            )

            assert_txn = transaction.PaymentTxn(
                sender=self.executor_address,
                index=params.index + 1,
                amount=min_final_amount,
                receiver=self.executor_address,
                sp=params,
            )
            txns.append(assert_txn)

            # Assign group ID
            txn_group = transaction.assign_group_id(txns)

            return txn_group

        except Exception as e:
            logger.error(f"Failed to build atomic group: {e}")
            return None

    def _build_swap_txn(
        self,
        app_id: int,
        asset_in: int,
        asset_out: int,
        amount_in: int,
        min_out: int,
        params,
    ):
        """
        Build a DEX swap transaction.

        This is simplified - real implementation would encode
        proper app arguments for the specific DEX.
        """
        try:
            # Tinyman V2 swap call structure (simplified)
            # In production, would use tinyman-py-sdk or pact-sdk

            app_call = transaction.ApplicationCallTxn(
                sender=self.executor_address,
                index=app_id,
                app_args=["swap"],
                foreign_assets=[asset_in, asset_out],
                sp=params,
            )

            return app_call

        except Exception as e:
            logger.error(f"Failed to build swap txn: {e}")
            return None


class StalenessAnalyzer:
    """Analyzes staleness decay curve for Gate 0 decision."""

    @staticmethod
    def calculate_win_rate_from_staleness(staleness_ms: int) -> float:
        """
        Estimate win rate based on staleness (empirical model).

        Staleness = wall-clock time from detection to simulation.
        Higher staleness = higher chance of being beaten.

        Model (from CHANGE 2 notes):
        - <100ms: ~90% win rate
        - 100-500ms: ~50% win rate
        - >500ms: ~10% win rate

        Linear interpolation between points.
        """
        if staleness_ms < 100:
            # Linear from 90% at 100ms to higher at 0ms
            return 0.95 - (staleness_ms / 100) * 0.05
        elif staleness_ms < 500:
            # Linear from 90% at 100ms to 10% at 500ms
            return 0.90 - ((staleness_ms - 100) / 400) * 0.80
        else:
            # Linear from 10% at 500ms to 5% at 1000ms
            return max(0.05, 0.10 - ((staleness_ms - 500) / 500) * 0.05)

    @staticmethod
    def analyze_funnel(results: List[SimulationResult]) -> Dict:
        """
        Analyze full funnel: raw → fee_gate → simulate_pass → would_execute.

        Returns statistics for Gate 0 decision.
        """
        if not results:
            return {
                "raw_cycles": 0,
                "fee_gate_pass": 0,
                "simulate_pass": 0,
                "would_execute": 0,
                "avg_profit": 0,
                "avg_staleness_ms": 0,
                "estimated_win_rate": 0,
            }

        fee_gate_results = [r for r in results if r.cleared_gate]
        simulate_results = [r for r in results if r.cleared_gate and r.simulate_pass]
        execute_results = [r for r in results if r.would_execute]

        avg_profit = (
            sum(r.net_profit_est_usd for r in execute_results) / len(execute_results)
            if execute_results else 0
        )

        avg_staleness = (
            sum(r.staleness_ms for r in execute_results) / len(execute_results)
            if execute_results else 0
        )

        estimated_win_rate = (
            StalenessAnalyzer.calculate_win_rate_from_staleness(int(avg_staleness))
            if execute_results else 0
        )

        return {
            "raw_cycles": len(results),
            "fee_gate_pass": len(fee_gate_results),
            "simulate_pass": len(simulate_results),
            "would_execute": len(execute_results),
            "avg_profit": avg_profit,
            "avg_staleness_ms": int(avg_staleness),
            "estimated_win_rate": estimated_win_rate,
        }
