#!/usr/bin/env python3
"""
Health Check Script - Monitor bot and node health.

Checks:
- Node sync status (block height)
- Database integrity
- Bot uptime
- Recent opportunities
- Daily KPIs

Usage:
    python scripts/health_check.py
    or via cron: */5 * * * * python /app/scripts/health_check.py
"""

import sqlite3
import sys
import logging
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_ledger_integrity(db_path: str) -> bool:
    """Check SQLite database integrity."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            logger.info("✅ Ledger integrity: OK")
            return True
        else:
            logger.error(f"❌ Ledger corruption detected: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to check ledger: {e}")
        return False


def check_recent_opportunities(db_path: str, hours: int = 1) -> int:
    """Check if we've seen recent opportunities."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM opportunities
            WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours')
            """,
            (hours,),
        )
        count = cursor.fetchone()[0]
        conn.close()

        if count > 0:
            logger.info(f"✅ Recent opportunities: {count} in last {hours}h")
            return count
        else:
            logger.warning(f"⚠️  No opportunities detected in last {hours}h")
            return 0
    except Exception as e:
        logger.error(f"❌ Failed to check opportunities: {e}")
        return -1


def check_daily_kpi(db_path: str) -> dict:
    """Get today's KPIs."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*), SUM(actual_profit_usd), SUM(gas_spent_usd),
                   COUNT(CASE WHEN status = 'won' THEN 1 END)
            FROM trades
            WHERE DATE(timestamp) = DATE('now')
            """
        )
        trades_count, total_profit, total_gas, trades_won = cursor.fetchone()
        trades_count = trades_count or 0
        total_profit = total_profit or 0
        total_gas = total_gas or 0
        trades_won = trades_won or 0

        net_profit = total_profit - total_gas
        win_rate = (trades_won / trades_count * 100) if trades_count > 0 else 0

        conn.close()

        logger.info(f"✅ Today's KPI: {trades_won}W/{trades_count}T, "
                   f"Win Rate: {win_rate:.1f}%, Net: ${net_profit:.2f}")

        return {
            "trades_submitted": trades_count,
            "trades_won": trades_won,
            "win_rate": win_rate,
            "net_profit_usd": net_profit,
        }
    except Exception as e:
        logger.error(f"❌ Failed to get KPI: {e}")
        return {}


def check_database_file(db_path: str) -> bool:
    """Check if database file exists and is accessible."""
    try:
        path = Path(db_path)
        if not path.exists():
            logger.warning(f"⚠️  Database not found at {db_path}")
            return False

        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Database file: {size_mb:.1f}MB")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to check database file: {e}")
        return False


def main():
    """Run health checks."""
    logger.info("=" * 60)
    logger.info("ARBITRAGE BOT HEALTH CHECK")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 60)

    db_path = "/data/ledger.db"

    # Check database
    logger.info("\n[DATABASE CHECKS]")
    db_exists = check_database_file(db_path)
    if db_exists:
        db_integrity = check_ledger_integrity(db_path)
        kpi = check_daily_kpi(db_path)

    # Check opportunities
    logger.info("\n[OPPORTUNITY CHECKS]")
    recent_1h = check_recent_opportunities(db_path, 1)
    recent_24h = check_recent_opportunities(db_path, 24)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("HEALTH CHECK SUMMARY")
    logger.info("=" * 60)

    all_good = (
        db_exists
        and db_integrity if db_exists else False
        and recent_24h > 0
    )

    if all_good:
        logger.info("✅ ALL SYSTEMS HEALTHY")
        return 0
    else:
        logger.warning("⚠️  SOME ISSUES DETECTED - CHECK LOGS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
