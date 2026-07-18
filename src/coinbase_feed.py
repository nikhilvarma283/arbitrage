"""
Coinbase public market-data feed (CEX-DEX price comparison, detection only)

Uses Coinbase Exchange's public, unauthenticated REST endpoint -- no API
key, no account, no ability to place orders -- to fetch real-time ALGO-USD
bid/ask for comparison against Algorand DEX pool prices.

IMPORTANT: unlike the on-chain DEX-vs-DEX cycles detected elsewhere in this
bot, a CEX-DEX "opportunity" here can never be executed atomically. It would
require two separate legs -- a real Coinbase order via their authenticated
trading API, and a real signed Algorand transaction -- with real execution
risk between them (one leg fills and the price moves before the other
does). This module only fetches and compares prices; it has no order
placement capability at all, and nothing here should be read as "ready to
trade."
"""

import logging
import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{product_id}/ticker"


@dataclass
class CexPrice:
    """A single CEX price snapshot (public market data only)."""
    product_id: str
    bid: float
    ask: float
    fetched_at: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


def fetch_coinbase_price(product_id: str = "ALGO-USD", timeout: float = 5.0) -> Optional[CexPrice]:
    """
    Fetch current bid/ask for a Coinbase product via the public ticker
    endpoint. Returns None on any failure (network, bad response, product
    not found) rather than raising, since this feed is best-effort and a
    single failed poll shouldn't interrupt on-chain detection.
    """
    try:
        resp = requests.get(
            COINBASE_TICKER_URL.format(product_id=product_id),
            headers={"User-Agent": "arbitrage-bot-shadow-mode/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return CexPrice(
            product_id=product_id,
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            fetched_at=datetime.now(),
        )
    except Exception as e:
        logger.warning(f"Failed to fetch Coinbase price for {product_id}: {e}")
        return None
