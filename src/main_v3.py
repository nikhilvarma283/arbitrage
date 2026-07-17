"""
Arbitrage Bot v3.0 - Option A (CHANGE ORDER 001 implementation)

Integrates:
- Phase 3: Event-Driven Pool Watcher
- Phase 4: Cycle Detection (direct + triangular)
- Phase 5: Simulator + Staleness Tracking
- Query API for real-time monitoring
- Gate 0 funnel reporting

Runs in shadow mode by default (no capital at risk).
"""

import logging
import sys
import time
import json
from datetime import datetime, date
from typing import Dict, List, Optional
import yaml
from pathlib import Path
from flask import Flask, jsonify
import threading
import requests

from algosdk.v2client.algod import AlgodClient

# Import new components
from src.pool_watcher_v2 import PoolWatcherV2
from src.cycle_detector import CycleDetector
from src.simulator import CycleSimulator, StalenessAnalyzer
from src.ledger import Ledger
from src.pool_discovery import PoolDiscovery
from collections import namedtuple

CycleRecord = namedtuple('CycleRecord', [
    'ts_utc', 'block_round', 'route_id', 'cycle_path', 'hops',
    'raw_spread_log', 'fee_stack_log', 'net_profit_est_usd',
    'optimal_size_usdc', 'cleared_gate', 'simulate_pass',
    'staleness_ms', 'would_execute', 'notes'
])

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/data/logs/bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class ArbitrageBotV3:
    """
    Multi-DEX Atomic Arbitrage Bot (CHANGE ORDER 001).

    Gate 0: Shadow mode (detection-only, no capital at risk)
    Measures: staleness decay → win-rate forecast → Phase 1 decision
    """

    def __init__(self, config_path: str):
        """Initialize bot with configuration."""
        self.config_path = config_path
        self.config = self._load_config()
        self.mode = self.config.get("app", {}).get("mode", "shadow")
        self.running = False

        logger.info(f"Initializing ArbitrageBotV3 in {self.mode} mode")

        # Initialize components
        self.algod_client = self._create_algod_client()
        self.pools_config = self._load_pools_config()

        # Pool auto-discovery enabled - discovers dynamic pools (Pact, Humble Swap, etc.)
        logger.info("Pool discovery: discovering dynamic pools on startup...")
        try:
            discovery = PoolDiscovery(self.algod_client)
            # Discover pools for all asset pairs (ALGO/USDC, ALGO/USDT, USDC/USDT)
            pairs = [(0, 31566704), (0, 793589522), (31566704, 793589522)]
            discovery.discover_all(pairs)
            self.pools_config = self._load_pools_config()  # Reload with discovered pools
            logger.info("✓ Pool discovery completed, config updated")
        except Exception as e:
            logger.warning(f"Pool discovery failed, using confirmed pools only: {e}")

        confirmed_count = sum(
            1 for dex_pools in self.pools_config.get("dexes", {}).values()
            for pool in dex_pools.values()
            if isinstance(pool, dict) and pool.get("app_id")
        )
        logger.info(f"✓ Loaded {confirmed_count} pools with app_ids")

        self.watcher = PoolWatcherV2(self.algod_client, self.pools_config, self.config.get("blockchain", {}))
        self.detector = CycleDetector(
            self.pools_config,
            self.config.get("gates", {})
        )
        self.simulator = CycleSimulator(
            self.algod_client,
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HVY",  # Placeholder address
            self.config.get("gates", {})
        )
        self.ledger = Ledger(
            self.config.get("ledger", {}).get("database_path", "/data/ledger.db")
        )

        # Statistics
        self.stats = {
            "start_time": datetime.now(),
            "blocks_processed": 0,
            "pools_updated": 0,
            "cycles_detected": 0,
            "cycles_simulated": 0,
            "would_execute_count": 0,
            "avg_staleness_ms": 0,
        }

        # Wire callbacks
        self.watcher.set_callback(self._on_pools_updated)

        # Flask app for queries
        self.app = Flask(__name__)
        self._setup_query_endpoints()

        logger.info("ArbitrageBotV3 initialized successfully")

    def _load_config(self) -> Dict:
        """Load bot configuration."""
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def _load_pools_config(self) -> Dict:
        """Load pools.lock.json."""
        try:
            pools_path = Path(self.config_path).parent / "pools.lock.json"
            with open(pools_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load pools config: {e}")
            raise

    def _create_algod_client(self) -> AlgodClient:
        """Create Algorand client with retry logic."""
        bc_config = self.config.get("blockchain", {})
        host = bc_config.get("algod_host", "localhost")
        port = bc_config.get("algod_port", 4001)
        token = bc_config.get("algod_token", "") or "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        use_https = bc_config.get("use_https", False)

        protocol = "https" if use_https else "http"
        client = AlgodClient(token, f"{protocol}://{host}:{port}")

        # Verify connection with timeout
        max_retries = 20
        retry_delay = 2
        url = f"http://{host}:{port}/health"

        for attempt in range(max_retries):
            try:
                # Try SDK first
                try:
                    status = client.status()
                    logger.info(f"✓ Connected to Algorand (block {status['last-round']})")
                    return client
                except Exception:
                    pass

                # Fallback: Quick health check via HTTP
                # Try /v2/status first (AlgoNode), then /status (standard)
                for endpoint_path in ["/v2/status", "/status"]:
                    try:
                        endpoint_url = f"{protocol}://{host}:{port}{endpoint_path}"
                        resp = requests.get(endpoint_url, timeout=2, verify=False)
                        if resp.status_code == 200:
                            data = resp.json()
                            block = data.get("last-round", 0)
                            logger.info(f"✓ Algorand node responding (block {block})")
                            return client
                    except Exception:
                        continue
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: {e}")
                    time.sleep(retry_delay)
                else:
                    logger.warning(f"Timeout waiting for node, proceeding anyway")
                    return client  # Return anyway - watcher will retry

    def _on_pools_updated(self, pool_states: List) -> None:
        """Callback when pools update (event-driven)."""
        try:
            # Detect cycles from current pool states
            cycles = self.detector.detect_cycles(pool_states)

            if not cycles:
                return

            logger.info(f"Detected {len(cycles)} cycles")

            # Simulate each cycle and record
            detection_time_ns = time.time_ns()

            for cycle in cycles:
                self.stats["cycles_detected"] += 1

                # Simulate
                result = self.simulator.simulate_cycle(
                    cycle,
                    {ps.pool_id: ps for ps in pool_states},
                    detection_time_ns,
                )

                self.stats["cycles_simulated"] += 1

                if result.would_execute:
                    self.stats["would_execute_count"] += 1
                    logger.info(
                        f"✓ Would execute: {result.route_id} "
                        f"profit=${result.net_profit_est_usd:.2f} "
                        f"staleness={result.staleness_ms}ms"
                    )

                # Log to ledger (CHANGE 3: log ALL cycles, not just winners)
                record = CycleRecord(
                    ts_utc=datetime.now(),
                    block_round=0,  # Would get from block
                    route_id=result.route_id,
                    cycle_path=result.cycle_path,
                    hops=result.hops,
                    raw_spread_log=result.raw_spread_log,
                    fee_stack_log=result.fee_stack_log,
                    net_profit_est_usd=result.net_profit_est_usd,
                    optimal_size_usdc=result.optimal_size_usdc,
                    cleared_gate=result.cleared_gate,
                    simulate_pass=result.simulate_pass,
                    staleness_ms=result.staleness_ms,
                    would_execute=result.would_execute,
                    notes=result.notes,
                )

                self.ledger.log_cycle(record)

        except Exception as e:
            logger.error(f"Error in pool update callback: {e}")

    def _setup_query_endpoints(self) -> None:
        """Setup Flask query API endpoints."""

        @self.app.route("/status", methods=["GET"])
        def status():
            """Get bot status."""
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()

            return jsonify({
                "mode": self.mode,
                "uptime_seconds": uptime,
                "status": "running" if self.running else "stopped",
                "blocks_processed": self.stats["blocks_processed"],
                "pools_updated": self.stats["pools_updated"],
                "cycles_detected": self.stats["cycles_detected"],
                "cycles_simulated": self.stats["cycles_simulated"],
                "would_execute_count": self.stats["would_execute_count"],
                "avg_staleness_ms": int(self.stats.get("avg_staleness_ms", 0)),
            })

        @self.app.route("/opportunities", methods=["GET"])
        def opportunities():
            """Get recent opportunities."""
            limit = 10
            # Would query ledger for recent cycles
            return jsonify({
                "total_detected": self.stats["cycles_detected"],
                "would_execute": self.stats["would_execute_count"],
                "recent": [],  # Would populate from ledger
            })

        @self.app.route("/pools", methods=["GET"])
        def pools():
            """Get current pool states."""
            states = self.watcher.get_all_pool_states()
            return jsonify({
                "total_pools": len(states),
                "pools": [
                    {
                        "app_id": s.pool_id,
                        "dex": s.dex,
                        "pair": f"{s.asset_a}/{s.asset_b}",
                        "reserve_a": float(s.reserve_a),
                        "reserve_b": float(s.reserve_b),
                        "log_rate": s.log_rate,
                    }
                    for s in states
                ],
            })

        @self.app.route("/funnel", methods=["GET"])
        def funnel():
            """Get Gate 0 funnel report."""
            # Would generate from ledger query
            return jsonify({
                "message": "Gate 0 funnel report (14-30 days)",
                "pass_criteria": {
                    "would_execute_per_day": ">=10",
                    "median_profit_usd": ">=0.75",
                    "staleness_win_rate": ">=40%",
                }
            })

        @self.app.route("/staleness", methods=["GET"])
        def staleness():
            """Get staleness distribution (win-rate forecast)."""
            # Would analyze from simulation results
            return jsonify({
                "message": "Staleness decay curve analysis",
                "estimated_win_rate": "calculating...",
            })

    def run(self) -> None:
        """Start bot and query API."""
        self.running = True

        logger.info("Starting bot main loop...")

        # Start query API in background thread
        api_thread = threading.Thread(
            target=lambda: self.app.run(host="0.0.0.0", port=8000, debug=False),
            daemon=True,
        )
        api_thread.start()
        logger.info("Query API started on port 8000")

        try:
            # Start event-driven pool watcher (blocking)
            self.watcher.start()

        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
            self.shutdown()
        except Exception as e:
            logger.critical(f"Bot crashed: {e}")
            self.shutdown()
            raise

    def shutdown(self) -> None:
        """Shutdown bot gracefully."""
        logger.info("Shutting down bot...")
        self.running = False

        # Generate final Gate 0 report if running in shadow mode
        if self.mode == "shadow":
            try:
                report = self.ledger.get_funnel_report(
                    date.today(),
                    date.today()
                )
                logger.info(f"Gate 0 Report: {report}")
            except Exception as e:
                logger.error(f"Failed to generate report: {e}")

        self.ledger.close()
        logger.info("Bot shutdown complete")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Arbitrage Bot v3.0")
    parser.add_argument(
        "--config",
        default="config/bot.multi-dex.yaml",
        help="Path to config file",
    )

    args = parser.parse_args()

    bot = ArbitrageBotV3(args.config)

    try:
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
