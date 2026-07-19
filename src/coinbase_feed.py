"""
Coinbase public market-data feed (CEX-DEX price comparison, detection only)

Uses Coinbase's newer "Advanced Trade" public REST endpoint -- no API key,
no account, no ability to place orders -- to fetch real-time ALGO-USD
bid/ask for comparison against Algorand DEX pool prices.

This module previously used the older Exchange API
(api.exchange.coinbase.com/products/{id}/ticker). That endpoint was found,
via direct testing, to serve the same trade_id/timestamp/order-book
sequence for 3+ minutes straight -- confirmed genuinely stale (not just
CDN-cached: cache-busting query params produced verified cf-cache-status
MISS responses that still returned identical data) from two independent
network paths (this machine and the deployed VPS). The Advanced Trade
endpoint used here was verified to show best_bid/best_ask actually moving
between polls and a real new trade appearing with a timestamp matching
elapsed wall-clock time.

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
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

COINBASE_TICKER_URL = (
    "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/ticker"
    "?limit=1"
)

# If the most recent trade's own timestamp is older than this, warn rather
# than silently trusting a feed that may have gone stale again (this is
# exactly the failure mode that caught the previous endpoint).
STALE_THRESHOLD_SECONDS = 120


@dataclass
class CexPrice:
    """A single CEX price snapshot (public market data only)."""

    product_id: str
    bid: float
    ask: float
    fetched_at: datetime
    last_trade_time: Optional[datetime] = None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def staleness_seconds(self) -> Optional[float]:
        if self.last_trade_time is None:
            return None
        return (self.fetched_at - self.last_trade_time).total_seconds()


@dataclass
class Trade:
    """A single real, executed Coinbase trade (public market data only)."""

    trade_id: int
    price: float
    size: float
    side: str  # "BUY" or "SELL" (taker side)
    time: datetime


def fetch_recent_trades(
    product_id: str = "ALGO-USD", limit: int = 25, timeout: float = 5.0
) -> list:
    """
    Fetch the most recent real trades for a product, oldest-problem-free:
    used by the maker-flip paper trader to check every trade since the
    last poll against its current hypothetical quotes (a single best_bid/
    best_ask snapshot per poll could silently miss a real trade that
    ticked through a quote between polls). Returns [] on any failure.
    """
    try:
        url = (
            "https://api.coinbase.com/api/v3/brokerage/market/products/"
            f"{product_id}/ticker?limit={limit}"
        )
        resp = requests.get(
            url,
            headers={"User-Agent": "arbitrage-bot-shadow-mode/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        trades = []
        for t in data.get("trades") or []:
            raw_time = t.get("time")
            if not raw_time:
                continue
            trades.append(
                Trade(
                    trade_id=int(t["trade_id"]),
                    price=float(t["price"]),
                    size=float(t["size"]),
                    side=t.get("side", ""),
                    time=datetime.fromisoformat(raw_time.replace("Z", "+00:00")),
                )
            )
        # Coinbase returns newest-first; callers want oldest-first so
        # processing them in order matches the sequence they actually happened in.
        trades.reverse()
        return trades
    except Exception as e:
        logger.warning(f"Failed to fetch Coinbase trades for {product_id}: {e}")
        return []


def fetch_coinbase_price(
    product_id: str = "ALGO-USD", timeout: float = 5.0
) -> Optional[CexPrice]:
    """
    Fetch current best bid/ask for a Coinbase product via the public
    Advanced Trade market-trades endpoint. Returns None on any failure
    (network, bad response, product not found) rather than raising, since
    this feed is best-effort and a single failed poll shouldn't interrupt
    on-chain detection.
    """
    try:
        resp = requests.get(
            COINBASE_TICKER_URL.format(product_id=product_id),
            headers={"User-Agent": "arbitrage-bot-shadow-mode/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        fetched_at = datetime.now(timezone.utc)
        last_trade_time = None
        trades = data.get("trades") or []
        if trades:
            raw_time = trades[0].get("time")
            if raw_time:
                # Coinbase timestamps look like "2026-07-19T04:27:22.034585Z"
                last_trade_time = datetime.fromisoformat(
                    raw_time.replace("Z", "+00:00")
                )

        price = CexPrice(
            product_id=product_id,
            bid=float(data["best_bid"]),
            ask=float(data["best_ask"]),
            fetched_at=fetched_at,
            last_trade_time=last_trade_time,
        )

        staleness = price.staleness_seconds
        if staleness is not None and staleness > STALE_THRESHOLD_SECONDS:
            logger.warning(
                f"Coinbase {product_id} last trade is {staleness:.0f}s old "
                f"(> {STALE_THRESHOLD_SECONDS}s threshold) -- feed may be stale"
            )

        return price
    except Exception as e:
        logger.warning(f"Failed to fetch Coinbase price for {product_id}: {e}")
        return None
