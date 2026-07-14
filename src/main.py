"""
Main Bot Orchestration - Ties all modules together.

Orchestrates pool_watcher, opportunity_engine, ledger, and alerts
into a unified shadow harness or live trading bot.

Sprint 2.5: Integration & Deployment
"""

import logging
import sys
import time
from datetime import datetime, date
from typing import Dict, List, Optional
import yaml
from algosdk.v2client.algod import AlgodClient

from src.pool_watcher import PoolWatcher, PoolWatcherConfig, PoolState
from src.opportunity_engine import OpportunityEngine, OpportunityEngineConfig
from src.ledger import Ledger, LedgerConfig
from src.alerts import AlertManager, AlertConfig

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


class ArbitrageBot:
    """
    Main arbitrage bot orchestration.

    Coordinates pool_watcher, opportunity_engine, ledger, and alerts
    into a unified shadow harness (detection-only) or live bot.

    Usage:
        bot = ArbitrageBot("config/bot.yaml")
        bot.run()  # Main event loop
    """

    def __init__(self, config_path: str):
        """
        Initialize bot with configuration.

        Args:
            config_path: Path to bot.yaml configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.mode = self.config.get("app", {}).get("mode", "shadow")
        self.running = False

        logger.info(f"Initializing ArbitrageBot in {self.mode} mode")

        # Initialize components
        self.algod_client = self._create_algod_client()
        self.pool_watcher = self._create_pool_watcher()
        self.opportunity_engine = self._create_opportunity_engine()
        self.ledger = self._create_ledger()
        self.alerts = self._create_alerts()

        # Statistics
        self.stats = {
            "start_time": datetime.now(),
            "opportunities_detected": 0,
            "trades_submitted": 0,
            "trades_won": 0,
            "last_opportunity": None,
            "uptime_seconds": 0,
        }

        # Connect pool_watcher to opportunity_engine
        self.pool_watcher.set_callback(self._on_pool_updated)

        logger.info("ArbitrageBot initialized successfully")

    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def _create_algod_client(self) -> AlgodClient:
        """Create Algorand client from config."""
        blockchain_config = self.config.get("blockchain", {})
        host = blockchain_config.get("algod_host", "localhost")
        port = blockchain_config.get("algod_port", 4001)
        token = blockchain_config.get("algod_token", "")

        client = AlgodClient(token, f"http://{host}:{port}")

        # Verify connection
        try:
            status = client.status()
            logger.info(f"Connected to Algorand node (block {status['last-round']})")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Algorand node: {e}")
            raise

    def _create_pool_watcher(self) -> PoolWatcher:
        """Create pool watcher from config."""
        pool_configs = self.config.get("pools", [])
        watcher = PoolWatcher(self.algod_client, pool_configs)
        logger.info(f"Created PoolWatcher for {len(pool_configs)} pools")
        return watcher

    def _create_opportunity_engine(self) -> OpportunityEngine:
        """Create opportunity engine from config."""
        engine_config = self.config.get("opportunity_engine", {})
        engine = OpportunityEngine(engine_config)
        logger.info(f"Created OpportunityEngine (gate: {engine_config.get('spread_gate_bps', 55)}bps)")
        return engine

    def _create_ledger(self) -> Ledger:
        """Create ledger from config."""
        ledger_config = self.config.get("ledger", {})
        db_path = ledger_config.get("database_path", "/data/ledger.db")
        ledger = Ledger(db_path)
        logger.info(f"Created Ledger at {db_path}")
        return ledger

    def _create_alerts(self) -> AlertManager:
        """Create alerts from config."""
        alerts_config = self.config.get("alerts", {})
        if alerts_config.get("telegram_enabled"):
            bot_token = alerts_config.get("telegram_bot_token", "")
            chat_id = alerts_config.get("telegram_chat_id", "")
            alerts = AlertManager(bot_token, chat_id)
            logger.info("Created AlertManager (Telegram enabled)")
            return alerts
        else:
            alerts = AlertManager("", "")
            logger.info("Created AlertManager (Telegram disabled)")
            return alerts

    def _on_pool_updated(self, pool_state: PoolState) -> None:
        """
        Callback when pool state updates.

        Triggers opportunity detection.

        Args:
            pool_state: Updated pool state
        """
        # Get all pool states
        all_pools = self.pool_watcher.get_all_pool_states()

        # Detect opportunities
        opportunities = self.opportunity_engine.detect_opportunities(all_pools)

        if opportunities:
            logger.info(f"Detected {len(opportunities)} opportunities")

            for opp in opportunities:
                # Log to ledger
                self.ledger.log_opportunity(opp)

                # Update stats
                self.stats["opportunities_detected"] += 1
                self.stats["last_opportunity"] = datetime.now()

                logger.debug(f"Opportunity: {opp}")

    def run(self) -> None:
        """
        Main bot event loop.

        Starts block subscription and runs indefinitely.
        """
        self.running = True
        logger.info("Starting main bot loop...")

        try:
            # Start pool watcher (blocking call)
            self.pool_watcher.start()
        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
            self.shutdown()
        except Exception as e:
            logger.critical(f"Bot crashed: {e}")
            self.alerts.send_error(f"Bot crashed: {e}", "critical")
            self.shutdown()
            raise

    def shutdown(self) -> None:
        """Shutdown bot gracefully."""
        logger.info("Shutting down bot...")
        self.running = False

        # Send final summary
        try:
            today_summary = self.ledger.get_daily_summary(date.today())
            self.alerts.send_daily_summary(today_summary)
        except Exception as e:
            logger.error(f"Failed to send final summary: {e}")

        # Close connections
        self.ledger.close()

        # Log final stats
        uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        logger.info(
            f"Bot shutdown. Uptime: {uptime:.0f}s, "
            f"Opportunities: {self.stats['opportunities_detected']}, "
            f"Trades: {self.stats['trades_submitted']}"
        )

    def get_status(self) -> Dict:
        """Get bot status for monitoring."""
        watcher_stats = self.pool_watcher.get_stats()
        engine_stats = self.opportunity_engine.get_stats()

        uptime = (datetime.now() - self.stats["start_time"]).total_seconds()

        return {
            "mode": self.mode,
            "running": self.running,
            "uptime_seconds": uptime,
            "blocks_processed": watcher_stats.get("blocks_processed", 0),
            "pools_updated": watcher_stats.get("pools_updated", 0),
            "missed_blocks": watcher_stats.get("missed_blocks", 0),
            "opportunities_detected": engine_stats.get("opportunities_detected", 0),
            "opportunities_discarded": engine_stats.get("opportunities_discarded", 0),
            "last_opportunity": str(self.stats["last_opportunity"]),
        }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Arbitrage Bot")
    parser.add_argument(
        "--config",
        default="config/bot.yaml",
        help="Path to config file (default: config/bot.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["shadow", "live"],
        help="Override bot mode (shadow or live)",
    )

    args = parser.parse_args()

    # Initialize and run bot
    bot = ArbitrageBot(args.config)

    if args.mode:
        bot.mode = args.mode
        logger.info(f"Overriding mode to {args.mode}")

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot interrupted")
        bot.shutdown()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        bot.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
