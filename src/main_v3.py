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
from typing import Any, Dict, List, Optional
import yaml
from pathlib import Path
from flask import Flask, jsonify
import threading
import requests

from algosdk.v2client.algod import AlgodClient

# Import new components
from src.pool_watcher_v2 import PoolWatcherV2
from src.cycle_detector import CycleDetector
from src.simulator import CycleSimulator
from src.ledger import Ledger, CycleRecord
from src.coinbase_feed import fetch_coinbase_price, fetch_recent_trades
from src.maker_flip_paper import MakerFlipPaperTrader

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

        # Pool auto-discovery disabled - using hardcoded confirmed pool IDs from config
        # TODO: Re-enable when algod_client initialization is fixed to pass valid client
        logger.info(
            "Pool discovery: using confirmed pool IDs from config (dynamic discovery disabled)"
        )

        confirmed_count = sum(
            1
            for dex_pools in self.pools_config.get("dexes", {}).values()
            for pool in dex_pools.values()
            if isinstance(pool, dict) and pool.get("app_id")
        )
        logger.info(f"✓ Loaded {confirmed_count} pools with app_ids")

        self.watcher = PoolWatcherV2(
            self.algod_client, self.pools_config, self.config.get("blockchain", {})
        )
        self.detector = CycleDetector(self.pools_config, self.config.get("gates", {}))
        self.simulator = CycleSimulator(
            self.algod_client,
            # Zero-key address (encoding.encode_address(bytes(32))) -- shadow
            # mode only ever builds unsigned txns for algod simulate() with
            # allow_empty_signatures=True, never signs or broadcasts, so this
            # just needs to be a syntactically valid 58-char address. The
            # previous placeholder here was 57 characters (invalid).
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ",
            self.config.get("gates", {}),
        )
        self.ledger = Ledger(
            self.config.get("ledger", {}).get("database_path", "/data/ledger.db")
        )

        # Statistics
        # blocks_processed/pools_updated live on the watcher itself (it's the
        # thing actually processing blocks); read via self.watcher.get_stats()
        # rather than duplicating counters here that would need to be kept in
        # sync. staleness_total_ms/staleness_count back a running average of
        # simulate_cycle()'s staleness_ms across every cycle simulated this run.
        self.stats: Dict[str, Any] = {
            "start_time": datetime.now(),
            "cycles_detected": 0,
            "cycles_simulated": 0,
            "would_execute_count": 0,
            "staleness_total_ms": 0,
            "staleness_count": 0,
            "cex_checks": 0,
            "cex_opportunities_detected": 0,
        }
        self.last_cex_price: Optional[Any] = None  # for /health's staleness check

        # CEX-DEX comparison config (see _check_cex_dex_opportunities).
        # Detection only -- there is no Coinbase account, no API key, and no
        # order-placement capability anywhere in this bot.
        gates_cfg = self.config.get("gates", {})
        self.coinbase_products = gates_cfg.get(
            "coinbase_products",
            # (Coinbase product id, matching Algorand stablecoin asset id it's compared against)
            [("ALGO-USD", 31566704), ("ALGO-USD", 312769)],
        )
        self.coinbase_taker_fee_bps = gates_cfg.get("coinbase_taker_fee_bps", 60)
        self.coinbase_poll_seconds = gates_cfg.get("coinbase_poll_seconds", 10)

        # CycleDetector's min_pool_reserve_raw (100 tokens/side) is a flat
        # floor tuned to exclude outright-dead pools, not one scaled to this
        # bot's $500 assumed trade size -- confirmed live: Tinyman's real
        # ALGO/USDT pool (~$2,940 total reserves) clears that floor easily
        # but is still far too thin for a $500 trade against it to be valid
        # under the linear-slippage model, and was persistently reporting a
        # ~7.6% "opportunity" against Coinbase on nearly every poll. CEX-DEX
        # comparison uses its own, stricter floor for this reason.
        self.cex_min_pool_reserve_raw = gates_cfg.get(
            "cex_min_pool_reserve_raw", 5_000_000_000
        )

        # Maker-flip paper trading (src/maker_flip_paper.py): simulates
        # quoting on Coinbase around DEX-implied fair value and hedging on
        # a simulated fill, using only real market data. Places no real
        # orders, signs nothing, touches no real funds -- purely a
        # backtest-style validation of whether the strategy would have
        # made money. Reference pool defaults to Tinyman ALGO/USDC (the
        # deepest pool we track) for fair value + hedge pricing.
        self.maker_flip_trader = MakerFlipPaperTrader(
            quote_half_spread_bps=gates_cfg.get("maker_flip_half_spread_bps", 80.0),
            maker_fee_bps=gates_cfg.get("maker_flip_maker_fee_bps", 0.0),
            quote_size_usd=gates_cfg.get("maker_flip_quote_size_usd", 500.0),
            hedge_delay_seconds=gates_cfg.get("maker_flip_hedge_delay_seconds", 5.0),
        )
        self.maker_flip_reference_pool_id = gates_cfg.get(
            "maker_flip_reference_pool_id", 1002590888  # Tinyman ALGO/USDC
        )

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
        token = (
            bc_config.get("algod_token", "")
            or "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        use_https = bc_config.get("use_https", False)

        protocol = "https" if use_https else "http"
        client = AlgodClient(token, f"{protocol}://{host}:{port}")

        # Verify connection with timeout
        max_retries = 20
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # Try SDK first
                try:
                    status = client.status()
                    assert isinstance(status, dict)  # algod default response format
                    logger.info(
                        f"✓ Connected to Algorand (block {status['last-round']})"
                    )
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

                # Neither the SDK call nor either HTTP fallback endpoint
                # succeeded this attempt, but none of them raised either --
                # retry rather than silently falling through with no client.
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries}: node not responding yet"
                    )
                    time.sleep(retry_delay)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: {e}")
                    time.sleep(retry_delay)
                else:
                    logger.warning("Timeout waiting for node, proceeding anyway")
                    return client  # Return anyway - watcher will retry

        raise RuntimeError(
            f"Could not connect to Algorand node at {protocol}://{host}:{port} "
            f"after {max_retries} attempts"
        )

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
                self.stats["staleness_total_ms"] += result.staleness_ms
                self.stats["staleness_count"] += 1

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

    def _check_cex_dex_opportunities(self) -> None:
        """
        Compare Coinbase's public ALGO-USD price against our Algorand DEX
        pools for the same nominal pair (ALGO/USDC, ALGO/USDT -- treating
        USDC/USDT as ~$1, which is the standard stablecoin-peg assumption;
        an actual USDC/USDT depeg would introduce error here).

        Detection only, same as everything else in this bot: this can log
        a divergence, but it can never be executed by this code. A real
        CEX-DEX trade needs two separate, non-atomic legs (an authenticated
        Coinbase order, and a signed Algorand transaction), with real
        execution risk between them that an atomic on-chain swap doesn't
        have. simulate_pass and would_execute are hardcoded False here for
        that reason -- there is no simulate() equivalent for a CEX leg, and
        no order-placement capability exists in this bot at all.
        """
        try:
            # Stricter than CycleDetector's on-chain floor (see
            # cex_min_pool_reserve_raw above) -- this is deliberately its
            # own, separate check so tightening it can't change which pools
            # are eligible for on-chain triangular/direct-pair detection.
            pool_states = [
                ps
                for ps in self.watcher.get_all_pool_states()
                if ps.reserve_a >= self.cex_min_pool_reserve_raw
                and ps.reserve_b >= self.cex_min_pool_reserve_raw
            ]

            # Fetch each unique Coinbase product once per poll, then compare
            # it against every configured stablecoin pairing for that
            # product (e.g. ALGO-USD is compared against both ALGO/USDC and
            # ALGO/USDT DEX pools).
            stables_by_product: Dict[str, List[int]] = {}
            for product_id, stable_asset_id in self.coinbase_products:
                stables_by_product.setdefault(product_id, []).append(stable_asset_id)

            for product_id, stable_asset_ids in stables_by_product.items():
                cex_price = fetch_coinbase_price(product_id)
                self.stats["cex_checks"] += 1
                if cex_price is None:
                    continue
                self.last_cex_price = cex_price  # for /health's staleness check

                for stable_asset_id in stable_asset_ids:
                    for ps in pool_states:
                        self._compare_cex_dex_pair(
                            product_id, stable_asset_id, cex_price, ps
                        )

        except Exception as e:
            logger.error(f"Error checking CEX-DEX opportunities: {e}")

    def _compare_cex_dex_pair(
        self, product_id: str, stable_asset_id: int, cex_price, ps
    ) -> None:
        """Compare one Coinbase price against one DEX pool state and log the result."""
        # Only ALGO/<stablecoin> pools are comparable to an ALGO-USD CEX
        # price; identify ALGO regardless of which side of the pool it's on.
        if ps.asset_a == 0 and ps.asset_b == stable_asset_id:
            dex_price = float(ps.reserve_b) / float(ps.reserve_a)
        elif ps.asset_b == 0 and ps.asset_a == stable_asset_id:
            dex_price = float(ps.reserve_a) / float(ps.reserve_b)
        else:
            return

        if dex_price > cex_price.ask:
            # Buy ALGO on Coinbase at ask, sell on the DEX.
            gross_gain_frac = (dex_price - cex_price.ask) / cex_price.ask
        elif dex_price < cex_price.bid:
            # Buy ALGO on the DEX, sell on Coinbase at bid.
            gross_gain_frac = (cex_price.bid - dex_price) / dex_price
        else:
            # dex_price sits inside Coinbase's own bid/ask spread -- no edge.
            gross_gain_frac = 0.0

        if gross_gain_frac <= 0:
            return

        # Simple additive fee approximation (one DEX swap + one CEX taker
        # fill, not a multi-hop log-compounded route like the on-chain-only
        # cycles use).
        dex_fee_frac = ps.fee_bps / 10000
        coinbase_fee_frac = self.coinbase_taker_fee_bps / 10000
        total_fee_frac = dex_fee_frac + coinbase_fee_frac

        net_gain_frac = gross_gain_frac - total_fee_frac
        cleared_gate = net_gain_frac >= total_fee_frac * self.detector.breakeven_margin

        base_size_usd = 500
        net_profit_usd = base_size_usd * net_gain_frac if cleared_gate else 0

        if cleared_gate and net_profit_usd >= self.detector.min_profit_usd:
            self.stats["cex_opportunities_detected"] += 1
            logger.info(
                f"CEX-DEX divergence: {product_id} vs {ps.dex} pool {ps.pool_id} "
                f"gross={gross_gain_frac*10000:.1f}bps net=${net_profit_usd:.2f} "
                f"(detection only, not executable)"
            )

        record = CycleRecord(
            ts_utc=datetime.now(),
            block_round=0,
            route_id=f"CEX_{product_id}_{ps.pool_id}",
            cycle_path=f"{product_id}@coinbase <-> pool {ps.pool_id}@{ps.dex}",
            hops=2,
            raw_spread_log=gross_gain_frac,
            fee_stack_log=total_fee_frac,
            net_profit_est_usd=net_profit_usd,
            optimal_size_usdc=base_size_usd,
            cleared_gate=cleared_gate,
            simulate_pass=False,  # no simulate() equivalent for a CEX leg
            staleness_ms=0,
            would_execute=False,  # no order-placement capability exists
            notes="cex_dex_detection_only: two non-atomic legs, not executable by this bot",
        )
        self.ledger.log_cycle(record)

    def _tick_maker_flip_paper_trader(self) -> None:
        """
        Paper-trade the maker-flip strategy for one poll cycle: fetch real
        recent Coinbase trades, check them against our current hypothetical
        quotes (recomputed fresh from the reference pool's live DEX price),
        and simulate any fills against real DEX reserves. Places no real
        orders, signs nothing -- see src/maker_flip_paper.py.
        """
        try:
            pool_states = self.watcher.get_all_pool_states()
            ref_pool = next(
                (
                    ps
                    for ps in pool_states
                    if ps.pool_id == self.maker_flip_reference_pool_id
                ),
                None,
            )
            if ref_pool is None:
                return

            fair_value = float(ref_pool.reserve_b) / float(ref_pool.reserve_a)
            trades = fetch_recent_trades("ALGO-USD", limit=25)
            if not trades:
                return

            fills = self.maker_flip_trader.tick(
                fair_value=fair_value,
                trades=trades,
                dex_reserve_algo=float(ref_pool.reserve_a) / 1_000_000,
                dex_reserve_usd=float(ref_pool.reserve_b) / 1_000_000,
                dex_fee_bps=ref_pool.fee_bps,
            )
            for fill in fills:
                self.ledger.log_paper_fill(fill)

        except Exception as e:
            logger.error(f"Error ticking maker-flip paper trader: {e}")

    def _run_cex_dex_poll_loop(self) -> None:
        """Background thread: periodically compare Coinbase vs DEX prices
        and paper-trade the maker-flip strategy."""
        while self.running:
            self._check_cex_dex_opportunities()
            self._tick_maker_flip_paper_trader()
            time.sleep(self.coinbase_poll_seconds)

    def _setup_query_endpoints(self) -> None:
        """Setup Flask query API endpoints."""

        @self.app.route("/status", methods=["GET"])
        def status():
            """Get bot status."""
            uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
            watcher_stats = self.watcher.get_stats()

            staleness_count = self.stats.get("staleness_count", 0)
            avg_staleness_ms = (
                self.stats.get("staleness_total_ms", 0) / staleness_count
                if staleness_count
                else 0
            )

            # All-time (across restarts -- the ledger persists on disk)
            # total of every on-chain and CEX-DEX opportunity that actually
            # cleared the fee/spread gates, i.e. genuine arbitrage the bot
            # identified. This is broader than would_execute_count, which
            # additionally requires simulate_pass -- something CEX-DEX
            # comparisons can never have (see _check_cex_dex_opportunities).
            cleared_summary = self.ledger.get_cleared_summary()

            # All-time paper-traded maker-flip summary -- simulated fills
            # only (real market data, no real orders, no real funds). See
            # src/maker_flip_paper.py.
            paper_summary = self.ledger.get_paper_trading_summary()

            return jsonify(
                {
                    "mode": self.mode,
                    "uptime_seconds": uptime,
                    "status": "running" if self.running else "stopped",
                    "blocks_processed": watcher_stats.get("blocks_processed", 0),
                    "pools_updated": watcher_stats.get("pools_updated", 0),
                    "missed_blocks": watcher_stats.get("missed_blocks", 0),
                    "cycles_detected": self.stats["cycles_detected"],
                    "cycles_simulated": self.stats["cycles_simulated"],
                    "would_execute_count": self.stats["would_execute_count"],
                    "avg_staleness_ms": int(avg_staleness_ms),
                    "cex_checks": self.stats["cex_checks"],
                    "cex_opportunities_detected": self.stats[
                        "cex_opportunities_detected"
                    ],
                    "cleared_opportunities_count": cleared_summary[
                        "cleared_opportunities_count"
                    ],
                    "total_cleared_profit_usd": round(
                        cleared_summary["total_cleared_profit_usd"], 2
                    ),
                    "paper_fill_count": paper_summary["paper_fill_count"],
                    "paper_total_pnl_usd": round(
                        paper_summary["paper_total_pnl_usd"], 4
                    ),
                    "paper_avg_pnl_per_fill_usd": round(
                        paper_summary["paper_avg_pnl_per_fill_usd"], 4
                    ),
                }
            )

        @self.app.route("/health", methods=["GET"])
        def health():
            """
            Is this actually working right now, not just "is the process
            alive" -- codifies every failure mode actually hit so far:
            the chain tip silently falling behind real-time (frozen
            parsing, rate-limit-induced stalls), errors starting to happen
            frequently (e.g. a 403 rate-limit burst), and the Coinbase feed
            going stale (confirmed once already this session to fail
            silently if untracked). Returns HTTP 503 (not 200) when
            unhealthy, so both `curl -f` and Docker's own HEALTHCHECK can
            react to it without parsing JSON.
            """
            watcher_health = self.watcher.get_health()
            reasons = []

            chain_lag = watcher_health.get("chain_lag_blocks")
            if watcher_health.get("error"):
                reasons.append(f"cannot reach algod: {watcher_health['error']}")
            elif chain_lag is not None and chain_lag > 20:
                reasons.append(
                    f"chain lag is {chain_lag} blocks (expected near 0 with "
                    f"the long-poll watcher)"
                )

            error_count = watcher_health.get("recent_error_count", 0)
            if error_count > 5:
                reasons.append(
                    f"{error_count} watcher errors in the last 5 minutes "
                    f"(possible rate-limiting or RPC issue)"
                )

            cex_staleness = None
            if self.last_cex_price is not None:
                cex_staleness = self.last_cex_price.staleness_seconds
                if cex_staleness is not None and cex_staleness > 300:
                    reasons.append(
                        f"Coinbase feed is {cex_staleness:.0f}s stale "
                        f"(> 300s -- confirmed once before to silently "
                        f"serve frozen data)"
                    )

            healthy = len(reasons) == 0
            return (
                jsonify(
                    {
                        "healthy": healthy,
                        "reasons": reasons,
                        "chain_lag_blocks": chain_lag,
                        "seconds_since_last_block": watcher_health.get(
                            "seconds_since_last_block"
                        ),
                        "recent_watcher_error_count": error_count,
                        "coinbase_staleness_seconds": cex_staleness,
                    }
                ),
                200 if healthy else 503,
            )

        @self.app.route("/opportunities", methods=["GET"])
        def opportunities():
            """Get recent opportunities."""
            # TODO: query ledger for recent cycles (limit=10)
            return jsonify(
                {
                    "total_detected": self.stats["cycles_detected"],
                    "would_execute": self.stats["would_execute_count"],
                    "recent": [],  # Would populate from ledger
                }
            )

        @self.app.route("/pools", methods=["GET"])
        def pools():
            """Get current pool states."""
            states = self.watcher.get_all_pool_states()
            return jsonify(
                {
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
                }
            )

        @self.app.route("/funnel", methods=["GET"])
        def funnel():
            """Get Gate 0 funnel report."""
            # Would generate from ledger query
            return jsonify(
                {
                    "message": "Gate 0 funnel report (14-30 days)",
                    "pass_criteria": {
                        "would_execute_per_day": ">=10",
                        "median_profit_usd": ">=0.75",
                        "staleness_win_rate": ">=40%",
                    },
                }
            )

        @self.app.route("/staleness", methods=["GET"])
        def staleness():
            """Get staleness distribution (win-rate forecast)."""
            # Would analyze from simulation results
            return jsonify(
                {
                    "message": "Staleness decay curve analysis",
                    "estimated_win_rate": "calculating...",
                }
            )

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

        # Start CEX-DEX comparison poll in background thread. Coinbase
        # prices update on their own clock, not per-Algorand-block, so this
        # runs on a simple timer rather than the event-driven watcher path.
        cex_thread = threading.Thread(target=self._run_cex_dex_poll_loop, daemon=True)
        cex_thread.start()
        logger.info(
            f"CEX-DEX comparison started (polling every {self.coinbase_poll_seconds}s, detection only)"
        )

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
                report = self.ledger.get_funnel_report(date.today(), date.today())
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
