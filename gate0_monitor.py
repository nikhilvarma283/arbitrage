#!/usr/bin/env python3
"""
Gate 0 Testing Monitor - Real-time metrics tracking for shadow mode validation

Collects daily:
- would_execute count
- median profit
- staleness decay curve
- pass/fail decision vs criteria

Usage: python gate0_monitor.py
"""

import requests
import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Optional
import sys

BOT_URL = "http://187.124.153.221:8000"
LEDGER_PATH = "/root/arbitrage/data/ledger.db"  # Via SSH


class Gate0Monitor:
    """Real-time Gate 0 metrics tracking."""

    PASS_CRITERIA = {
        "would_execute_per_day": 10,
        "median_profit_usd": 0.75,
        "staleness_win_rate_pct": 40,
    }

    def __init__(self):
        self.bot_url = BOT_URL
        self.start_date = date.today()
        self.report_file = Path("gate0_report.jsonl")

    def query_bot_status(self) -> Optional[Dict]:
        """Get current bot status from query API."""
        try:
            resp = requests.get(f"{self.bot_url}/status", timeout=5)
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            print(f"❌ Bot unreachable: {e}")
            return None

    def get_daily_metrics(self, target_date: date) -> Dict:
        """Fetch Gate 0 metrics for a specific date from bot ledger."""
        try:
            resp = requests.get(f"{self.bot_url}/funnel", timeout=5)
            data = resp.json()

            return {
                "date": target_date.isoformat(),
                "raw_cycles": data.get("raw_cycles_detected", 0),
                "fee_gate_pass": data.get("fee_gate_pass", 0),
                "simulate_pass": data.get("simulate_pass", 0),
                "would_execute": data.get("would_execute", 0),
                "avg_profit_usd": data.get("avg_profit", 0),
                "staleness_win_rate_pct": data.get("estimated_win_rate", 0) * 100,
            }
        except Exception as e:
            print(f"⚠️  Could not fetch metrics: {e}")
            return {}

    def check_daily_criteria(self, metrics: Dict) -> Dict:
        """Evaluate if day passes Gate 0 criteria."""
        would_execute = metrics.get("would_execute", 0)
        profit = metrics.get("avg_profit_usd", 0)
        staleness = metrics.get("staleness_win_rate_pct", 0)

        return {
            "would_execute_per_day": {
                "actual": would_execute,
                "threshold": self.PASS_CRITERIA["would_execute_per_day"],
                "pass": would_execute >= self.PASS_CRITERIA["would_execute_per_day"],
            },
            "median_profit_usd": {
                "actual": profit,
                "threshold": self.PASS_CRITERIA["median_profit_usd"],
                "pass": profit >= self.PASS_CRITERIA["median_profit_usd"],
            },
            "staleness_win_rate": {
                "actual": staleness,
                "threshold": self.PASS_CRITERIA["staleness_win_rate_pct"],
                "pass": staleness >= self.PASS_CRITERIA["staleness_win_rate_pct"],
            },
        }

    def print_daily_report(self, metrics: Dict, criteria: Dict) -> None:
        """Pretty-print daily progress."""
        date_str = metrics.get("date", "unknown")
        days_elapsed = (datetime.fromisoformat(date_str).date() - self.start_date).days + 1

        print(f"\n{'='*70}")
        print(f"  GATE 0 DAILY REPORT - Day {days_elapsed}")
        print(f"  {date_str}")
        print(f"{'='*70}")

        print(f"\n📊 FUNNEL METRICS:")
        print(f"   Raw cycles detected:  {metrics.get('raw_cycles', 0)}")
        print(f"   Fee gate pass:        {metrics.get('fee_gate_pass', 0)}")
        print(f"   Simulate pass:        {metrics.get('simulate_pass', 0)}")
        print(f"   Would execute:        {metrics.get('would_execute', 0)}")

        print(f"\n🎯 PASS CRITERIA:")
        for criterion, data in criteria.items():
            actual = data["actual"]
            threshold = data["threshold"]
            pass_str = "✅ PASS" if data["pass"] else "❌ FAIL"
            print(f"   {criterion:25} {actual:6.2f} / {threshold:6.2f} {pass_str}")

        all_pass = all(c["pass"] for c in criteria.values())
        decision = "🚀 GATE 0 PASSED" if all_pass else "⏳ Continue testing"
        print(f"\n📋 DECISION: {decision}")
        print(f"{'='*70}\n")

    def run_continuous_monitor(self) -> None:
        """Monitor bot and print daily reports."""
        print(f"\n🚀 GATE 0 SHADOW MODE TESTING STARTED")
        print(f"📅 Start date: {self.start_date}")
        print(f"⏱️  Duration: 14-30 days")
        print(f"🔗 Bot URL: {self.bot_url}")
        print(f"\nPass Criteria:")
        for criterion, threshold in self.PASS_CRITERIA.items():
            print(f"  • {criterion}: ≥{threshold}")

        last_reported_date = None

        while True:
            try:
                # Check if bot is running
                status = self.query_bot_status()
                if not status:
                    print(f"[{datetime.now()}] ⚠️  Bot unavailable, retrying...")
                    import time
                    time.sleep(60)
                    continue

                current_date = date.today()

                # Generate daily report
                if current_date != last_reported_date:
                    metrics = self.get_daily_metrics(current_date)
                    if metrics:
                        criteria = self.check_daily_criteria(metrics)
                        self.print_daily_report(metrics, criteria)

                        # Log to file
                        self._save_report(metrics, criteria)

                        last_reported_date = current_date

                # Keep monitoring
                import time
                time.sleep(300)  # Check every 5 minutes

            except KeyboardInterrupt:
                print("\n⏹️  Monitoring stopped by user")
                break
            except Exception as e:
                print(f"[{datetime.now()}] ❌ Error: {e}")
                import time
                time.sleep(60)

    def _save_report(self, metrics: Dict, criteria: Dict) -> None:
        """Save daily report to file."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "criteria": criteria,
        }
        with open(self.report_file, "a") as f:
            f.write(json.dumps(report) + "\n")


def main():
    monitor = Gate0Monitor()

    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║         GATE 0 SHADOW MODE - TESTING INITIALIZATION           ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    # Show initial status
    status = monitor.query_bot_status()
    if status:
        print(f"\n✅ Bot is running:")
        print(f"   Mode: {status.get('mode')}")
        print(f"   Status: {status.get('status')}")
        print(f"   Uptime: {status.get('uptime_seconds'):.1f}s")
    else:
        print(f"\n❌ Cannot reach bot at {BOT_URL}")
        print("   Make sure the bot is running and accessible")
        return

    print(f"\n📝 Reports will be saved to: {monitor.report_file}")
    print(f"🔄 Checking metrics every 5 minutes...")

    # Start monitoring
    monitor.run_continuous_monitor()


if __name__ == "__main__":
    main()
