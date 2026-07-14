"""
Ledger Module - SQLite persistence for opportunities and trades.

Logs all detected opportunities (shadow mode) and executed trades (phase 1 live)
to SQLite database for auditing, analytics, and KPI calculation.

Sprint 2.3: Ledger Implementation
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import logging

from src.opportunity_engine import Opportunity

logger = logging.getLogger(__name__)


class Ledger:
    """
    SQLite-based ledger for arbitrage bot.

    Schema:
    - opportunities: all detected opportunities (shadow mode)
    - trades: all submitted trades (phase 1 live)
    - daily_summary: computed KPIs per day

    Responsibilities:
    - Create and maintain SQLite schema
    - Log opportunities (shadow mode)
    - Log trades and results (phase 1 live)
    - Compute daily KPIs
    - Export data for dashboard
    - Validate data integrity

    Usage:
        ledger = Ledger("ledger.db")
        ledger.log_opportunity(opportunity)
        daily_kpi = ledger.get_daily_summary(datetime.now().date())
        ledger.export_for_dashboard("2026-07-01", "2026-07-13")
    """

    def __init__(self, db_path: str):
        """
        Initialize ledger with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database and create schema if needed."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_schema()
            logger.info(f"Ledger initialized: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize ledger: {e}")
            raise

    def _create_schema(self) -> None:
        """
        Create database schema (idempotent).

        Tables:
        - opportunities: All detected arbitrage opportunities
        - trades: All submitted trade attempts
        - daily_summary: Aggregated KPIs per day
        """
        cursor = self.conn.cursor()

        # Opportunities table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                block_number INTEGER NOT NULL,
                pool_a_id INTEGER NOT NULL,
                pool_b_id INTEGER NOT NULL,
                pool_a_name TEXT,
                pool_b_name TEXT,
                spread_bps REAL NOT NULL,
                size_tokens REAL NOT NULL,
                size_usd REAL NOT NULL,
                expected_profit_tokens REAL NOT NULL,
                expected_profit_usd REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Trades table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_group_id TEXT UNIQUE NOT NULL,
                timestamp DATETIME NOT NULL,
                pool_a_id INTEGER NOT NULL,
                pool_b_id INTEGER NOT NULL,
                spread_bps REAL NOT NULL,
                size_tokens REAL NOT NULL,
                size_usd REAL NOT NULL,
                expected_profit_usd REAL NOT NULL,
                actual_profit_usd REAL,
                gas_spent_usd REAL,
                status TEXT NOT NULL,
                reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                settled_at DATETIME
            )
            """
        )

        # Daily summary table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_summary (
                date DATE PRIMARY KEY,
                opportunities_detected INTEGER DEFAULT 0,
                avg_spread_bps REAL DEFAULT 0,
                trades_submitted INTEGER DEFAULT 0,
                trades_won INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                total_profit_usd REAL DEFAULT 0,
                total_gas_usd REAL DEFAULT 0,
                net_profit_usd REAL DEFAULT 0,
                decay_ratio REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_opp_timestamp ON opportunities(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_status ON trades(status)")

        self.conn.commit()
        logger.info("Database schema created/verified")

    def log_opportunity(self, opp: Opportunity) -> int:
        """
        Log an opportunity detection to database.

        Args:
            opp: Opportunity object

        Returns:
            Row ID of inserted opportunity
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO opportunities
                (timestamp, block_number, pool_a_id, pool_b_id, pool_a_name, pool_b_name,
                 spread_bps, size_tokens, size_usd, expected_profit_tokens, expected_profit_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(),
                    opp.pool_a.updated_at,
                    opp.pool_a.pool_id,
                    opp.pool_b.pool_id,
                    opp.pool_a.pool_name,
                    opp.pool_b.pool_name,
                    opp.spread_bps,
                    float(opp.size_tokens),
                    float(opp.size_tokens),  # Simplified: 1 token = $1
                    float(opp.expected_profit_tokens),
                    float(opp.expected_profit_usd),
                ),
            )
            self.conn.commit()
            row_id = cursor.lastrowid
            logger.debug(f"Logged opportunity: {opp} (row {row_id})")
            return row_id
        except Exception as e:
            logger.error(f"Failed to log opportunity: {e}")
            raise

    def log_trade(
        self,
        tx_group_id: str,
        opp: Opportunity,
        timestamp: datetime,
    ) -> int:
        """
        Log a trade submission.

        Args:
            tx_group_id: Unique transaction group ID
            opp: Opportunity object
            timestamp: When trade was submitted

        Returns:
            Row ID of inserted trade
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades
                (tx_group_id, timestamp, pool_a_id, pool_b_id, spread_bps,
                 size_tokens, size_usd, expected_profit_usd, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_group_id,
                    timestamp,
                    opp.pool_a.pool_id,
                    opp.pool_b.pool_id,
                    opp.spread_bps,
                    float(opp.size_tokens),
                    float(opp.size_tokens),
                    float(opp.expected_profit_usd),
                    "submitted",
                ),
            )
            self.conn.commit()
            row_id = cursor.lastrowid
            logger.debug(f"Logged trade: {tx_group_id} (row {row_id})")
            return row_id
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")
            raise

    def update_trade_result(
        self,
        tx_group_id: str,
        status: str,  # "won", "lost", "failed"
        actual_profit_usd: Optional[float] = None,
        gas_spent_usd: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Update trade with settlement result.

        Args:
            tx_group_id: Transaction group ID to update
            status: Result status ("won", "lost", "failed")
            actual_profit_usd: Actual profit realized (if won)
            gas_spent_usd: Gas/fee costs
            reason: Reason for failure (if applicable)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE trades
                SET status = ?, actual_profit_usd = ?, gas_spent_usd = ?, reason = ?, settled_at = ?
                WHERE tx_group_id = ?
                """,
                (
                    status,
                    actual_profit_usd,
                    gas_spent_usd,
                    reason,
                    datetime.now(),
                    tx_group_id,
                ),
            )
            self.conn.commit()

            # Alert if negative profit (should never happen with Layer 0 on-chain assertion)
            if actual_profit_usd is not None and actual_profit_usd < 0:
                logger.critical(f"NEGATIVE PROFIT DETECTED: {tx_group_id} = ${actual_profit_usd:.2f}")

            logger.debug(f"Updated trade: {tx_group_id} -> {status}")
        except Exception as e:
            logger.error(f"Failed to update trade result: {e}")
            raise

    def get_daily_summary(self, date) -> Dict:
        """
        Compute daily KPIs for a given date.

        Args:
            date: Date to summarize (datetime.date)

        Returns:
            Dict with KPIs
        """
        try:
            cursor = self.conn.cursor()

            # Query opportunities for the day
            cursor.execute(
                """
                SELECT COUNT(*), AVG(spread_bps) FROM opportunities
                WHERE DATE(timestamp) = ?
                """,
                (date,),
            )
            opp_count, avg_spread = cursor.fetchone()
            opp_count = opp_count or 0
            avg_spread = avg_spread or 0

            # Query trades for the day
            cursor.execute(
                """
                SELECT COUNT(*), SUM(actual_profit_usd), SUM(gas_spent_usd),
                       COUNT(CASE WHEN status = 'won' THEN 1 END)
                FROM trades
                WHERE DATE(timestamp) = ?
                """,
                (date,),
            )
            trades_count, total_profit, total_gas, trades_won = cursor.fetchone()
            trades_count = trades_count or 0
            total_profit = total_profit or 0
            total_gas = total_gas or 0
            trades_won = trades_won or 0

            win_rate = (trades_won / trades_count * 100) if trades_count > 0 else 0
            net_profit = total_profit - total_gas

            # Calculate decay_ratio (7 days ago vs today)
            decay_ratio = 1.0
            cursor.execute(
                """
                SELECT SUM(actual_profit_usd) FROM trades
                WHERE DATE(timestamp) = DATE(?, '-7 days')
                """,
                (date,),
            )
            past_profit = cursor.fetchone()[0] or 1
            if past_profit > 0:
                decay_ratio = net_profit / past_profit

            summary = {
                "date": str(date),
                "opportunities_detected": opp_count,
                "avg_spread_bps": float(avg_spread),
                "trades_submitted": trades_count,
                "trades_won": trades_won,
                "win_rate": win_rate,
                "total_profit_usd": float(total_profit),
                "total_gas_usd": float(total_gas),
                "net_profit_usd": float(net_profit),
                "decay_ratio": float(decay_ratio),
            }

            logger.info(f"Daily summary {date}: {summary['net_profit_usd']:.2f} net")
            return summary
        except Exception as e:
            logger.error(f"Failed to compute daily summary: {e}")
            raise

    def get_weekly_summary(self, date) -> Dict:
        """Get weekly KPIs (last 7 days from date)."""
        # TODO: Implement
        raise NotImplementedError("get_weekly_summary() must be implemented")

    def export_for_dashboard(self, start_date, end_date, limit: int = 10000) -> List[Dict]:
        """
        Export opportunities for public dashboard.

        Args:
            start_date: Start date (datetime.date)
            end_date: End date (datetime.date)
            limit: Max rows to return

        Returns:
            List of opportunity dicts for API

        TODO:
        - Query opportunities in date range
        - Convert to API-friendly format
        - Limit results
        - Return
        """
        # TODO: Implement
        raise NotImplementedError("export_for_dashboard() must be implemented")

    def validate(self) -> bool:
        """
        Validate database integrity.

        Runs PRAGMA integrity_check and detects corruption.

        Returns:
            True if valid, False if corrupted
        """
        try:
            cursor = self.conn.cursor()

            # Check integrity
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            if result != "ok":
                logger.error(f"Database integrity check failed: {result}")
                return False

            # Check for impossible values
            cursor.execute("SELECT COUNT(*) FROM trades WHERE actual_profit_usd < 0")
            if cursor.fetchone()[0] > 0:
                logger.error("Found negative profits in trades (impossible)")
                return False

            logger.info("Database validation passed")
            return True
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Ledger closed")

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()


class LedgerConfig:
    """Configuration for ledger."""

    def __init__(
        self,
        database_path: str = "/data/ledger.db",
        backup_dir: str = "/data/backups",
        retention_days: int = 30,
    ):
        """Initialize ledger config."""
        self.database_path = database_path
        self.backup_dir = backup_dir
        self.retention_days = retention_days

    @staticmethod
    def from_yaml(config_dict: Dict) -> "LedgerConfig":
        """Load from YAML dict."""
        # TODO: Parse from config/bot.yaml
        raise NotImplementedError()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage (after implementation)
    # ledger = Ledger("ledger.db")
    # ledger.log_opportunity(opportunity)
    # summary = ledger.get_daily_summary(datetime.now().date())
    # print(f"Today: {summary}")
    # ledger.close()
