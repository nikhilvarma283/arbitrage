"""
Alerts Module - Telegram notifications for bot events.

Sends alerts to operator via Telegram bot for:
- Trade fills (successful executions)
- Breaker events (circuit breaker trips)
- Daily/weekly summaries
- Critical errors

Sprint 2.4 / 4.1: Alerts Implementation
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Sends alerts via Telegram bot.

    Responsibilities:
    - Format alert messages
    - Send to Telegram bot
    - Retry on failure
    - Categorize alerts (fills, breakers, summaries)

    Usage:
        alerts = AlertManager(bot_token, chat_id)
        alerts.send_fill(opportunity, actual_profit)
        alerts.send_breaker("5_consecutive_failures")
        alerts.send_daily_summary(daily_kpi)
    """

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize alert manager.

        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Telegram chat ID to send to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)

    def send_fill(self, pool_a: str, pool_b: str, profit_usd: float, gas_usd: float) -> bool:
        """
        Send alert for successful trade fill.

        Args:
            pool_a: Source pool name
            pool_b: Destination pool name
            profit_usd: Profit in USD
            gas_usd: Gas/fee cost in USD

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        message = f"""✅ Trade Fill!
{pool_a} → {pool_b}
Profit: ${profit_usd:.2f}
Gas: ${gas_usd:.2f}
Net: ${profit_usd - gas_usd:.2f}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"""

        return self._send_message(message)

    def send_breaker(self, breaker_name: str, reason: str) -> bool:
        """
        Send alert for circuit breaker trip.

        Args:
            breaker_name: Name of breaker (e.g., "5_consecutive_failures")
            reason: Reason for trip

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        message = f"""🚨 BREAKER TRIP: {breaker_name}
Reason: {reason}
Bot halted. Check logs immediately.
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"""

        logger.critical(f"Breaker trip: {breaker_name}")
        return self._send_message(message)

    def send_daily_summary(self, daily_kpi: Dict) -> bool:
        """
        Send daily summary alert.

        Args:
            daily_kpi: Dict from ledger.get_daily_summary()

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        message = f"""📊 Daily Summary - {daily_kpi.get('date', 'N/A')}
Opportunities: {daily_kpi.get('opportunities_detected', 0)}
Avg Spread: {daily_kpi.get('avg_spread_bps', 0):.1f}bps
Trades: {daily_kpi.get('trades_won', 0)}W / {daily_kpi.get('trades_submitted', 0)}T
Win Rate: {daily_kpi.get('win_rate', 0):.1f}%
Net Profit: ${daily_kpi.get('net_profit_usd', 0):.2f}
Decay Ratio: {daily_kpi.get('decay_ratio', 1.0):.2f}"""

        return self._send_message(message)

    def send_error(self, error_msg: str, severity: str = "error") -> bool:
        """
        Send error alert.

        Args:
            error_msg: Error message
            severity: "warning", "error", "critical"

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        emoji = {"warning": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "ℹ️")

        message = f"""{emoji} {severity.upper()}
{error_msg}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"""

        return self._send_message(message)

    def _send_message(self, message: str) -> bool:
        """
        Send raw message via Telegram bot.

        Args:
            message: Formatted message text

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.warning("Telegram alerts disabled")
            return False

        try:
            import requests

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": message}

            response = requests.post(url, data=data, timeout=5)
            if response.status_code == 200:
                logger.info("Alert sent to Telegram")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False


class AlertConfig:
    """Configuration for alerts."""

    def __init__(self, telegram_bot_token: str = "", telegram_chat_id: str = ""):
        """Initialize alert config."""
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.enabled = bool(telegram_bot_token and telegram_chat_id)

    @staticmethod
    def from_env() -> "AlertConfig":
        """Load from environment variables."""
        import os

        return AlertConfig(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        )

    @staticmethod
    def from_yaml(config_dict: Dict) -> "AlertConfig":
        """Load from YAML dict."""
        # TODO: Parse from config/bot.yaml
        raise NotImplementedError()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage (after implementation)
    # alerts = AlertManager(bot_token, chat_id)
    # alerts.send_fill("TINYMAN", "PACT", 3.25, 0.10)
    # alerts.send_daily_summary({"profit": 486.32, "win_rate": 0.48})
