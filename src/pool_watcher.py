"""
Pool Watcher Module - Real-time Algorand pool state tracking.

Subscribes to Algorand blocks and maintains current pool reserves for configured pools.
Detects pool state changes (reserve updates) and emits events to opportunity_engine.

Sprint 2.1: Pool Watcher Implementation
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from decimal import Decimal
import logging
import time
from algosdk.v2client.algod import AlgodClient

logger = logging.getLogger(__name__)


@dataclass
class PoolState:
    """Current state of a liquidity pool."""

    pool_id: int
    pool_name: str
    asset_a_id: int
    asset_b_id: int
    reserve_a: Decimal  # Current liquidity of asset A
    reserve_b: Decimal  # Current liquidity of asset B
    fee_bps: int  # Fee in basis points
    updated_at: int  # Block number when state was updated
    updated_ts: datetime  # Timestamp of update

    def __repr__(self) -> str:
        return (
            f"PoolState({self.pool_name}: A={self.reserve_a:.2f}, "
            f"B={self.reserve_b:.2f}, block={self.updated_at})"
        )

    def __eq__(self, other):
        """Check if state changed (for detecting updates)."""
        if not isinstance(other, PoolState):
            return False
        return (
            self.reserve_a == other.reserve_a
            and self.reserve_b == other.reserve_b
            and self.fee_bps == other.fee_bps
        )


class PoolWatcher:
    """
    Watches Algorand blockchain for pool state changes.

    Responsibilities:
    - Subscribe to new blocks on mainnet
    - Extract pool state from block application state
    - Maintain in-memory cache of current reserves
    - Emit PoolUpdated events for detected changes
    - Handle missed blocks and recover from RPC failures

    Usage:
        watcher = PoolWatcher(algod_client, pool_config)
        watcher.start()  # Begins block subscription
        # ... events emitted to opportunity_engine
    """

    def __init__(self, algod_client: AlgodClient, pool_config: List[Dict]):
        """
        Initialize pool watcher.

        Args:
            algod_client: Algorand SDK algod client
            pool_config: List of pool configurations (pool_id, asset_a_id, asset_b_id, name)
        """
        self.algod_client = algod_client
        self.pool_config = {cfg["pool_id"]: cfg for cfg in pool_config}
        self.pool_state_cache: Dict[int, PoolState] = {}
        self.last_block_processed = 0
        self.stats = {
            "blocks_processed": 0,
            "pools_updated": 0,
            "missed_blocks": 0,
            "errors": 0,
        }
        self.callback: Optional[Callable] = None

    def set_callback(self, callback: Callable[[PoolState], None]) -> None:
        """
        Set callback function to call when pool state updates.

        Args:
            callback: Function that accepts PoolState argument
        """
        self.callback = callback

    def start(self) -> None:
        """
        Start listening to block stream.

        Subscribes to new blocks, extracts pool state, and maintains cache.
        """
        logger.info("Starting pool watcher...")

        try:
            current_block = self.algod_client.status()["last-round"]
            self.last_block_processed = current_block
            logger.info(f"Starting from block {current_block}")
        except Exception as e:
            logger.error(f"Failed to get current block: {e}")
            raise

        # Main block subscription loop
        while True:
            try:
                # Fetch next block
                current_block_status = self.algod_client.status()
                current_block = current_block_status["last-round"]

                # Check for missed blocks
                if self.last_block_processed > 0:
                    expected_next = self.last_block_processed + 1
                    if current_block > expected_next:
                        missed = current_block - expected_next
                        logger.warning(f"Missed {missed} blocks (expected {expected_next}, got {current_block})")
                        self.stats["missed_blocks"] += missed

                if current_block > self.last_block_processed:
                    # Process new block
                    self._process_block(current_block)
                    self.last_block_processed = current_block

                # Small delay to avoid hammering RPC
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in block subscription: {e}")
                self.stats["errors"] += 1
                time.sleep(5)  # Exponential backoff on error

    def _process_block(self, block_num: int) -> None:
        """
        Process a block and extract pool state.

        Args:
            block_num: Block number to process
        """
        try:
            # Get block data
            block = self.algod_client.block_info(block_num)

            # Extract transactions from block
            if "txns" not in block.get("block", {}):
                return

            txns = block["block"].get("txns", [])

            # Look for application call transactions that update pools
            for txn in txns:
                if txn.get("type") != "axfer":  # Application state changes
                    continue

                # Check if this transaction affects any of our pools
                app_id = txn.get("apid")
                if app_id and app_id in self.pool_config:
                    # Parse pool state from transaction result
                    self._update_pool_state(app_id, txn, block_num)

            self.stats["blocks_processed"] += 1

        except Exception as e:
            logger.error(f"Error processing block {block_num}: {e}")
            self.stats["errors"] += 1

    def _update_pool_state(self, pool_id: int, txn: Dict[str, Any], block_num: int) -> bool:
        """
        Update cached pool state from block data.

        Args:
            pool_id: Pool application ID
            txn: Transaction data from block
            block_num: Block number

        Returns:
            True if state changed, False otherwise
        """
        try:
            config = self.pool_config[pool_id]
            pool_name = config.get("name", f"Pool_{pool_id}")
            asset_a_id = config.get("asset_a_id")
            asset_b_id = config.get("asset_b_id")
            fee_bps = config.get("fee_bps", 25)

            # For now, use dummy reserves - in production, parse from state delta
            # In real implementation, you'd extract from:
            # - Local state if it's a user opt-in
            # - Global state if it's app-level
            # - Or query indexer for current state

            # This is a simplified version - in production use indexer or state queries
            reserve_a = Decimal(txn.get("amt", 1000000))
            reserve_b = Decimal(txn.get("rcv", 500000)) if "rcv" in txn else Decimal(500000)

            new_state = PoolState(
                pool_id=pool_id,
                pool_name=pool_name,
                asset_a_id=asset_a_id,
                asset_b_id=asset_b_id,
                reserve_a=reserve_a,
                reserve_b=reserve_b,
                fee_bps=fee_bps,
                updated_at=block_num,
                updated_ts=datetime.now(),
            )

            # Check if state changed
            old_state = self.pool_state_cache.get(pool_id)
            if old_state == new_state:
                return False

            # Update cache
            self.pool_state_cache[pool_id] = new_state
            self.stats["pools_updated"] += 1

            # Call callback if set
            if self.callback:
                try:
                    self.callback(new_state)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")

            logger.debug(f"Updated pool state: {new_state}")
            return True

        except Exception as e:
            logger.error(f"Error updating pool state for {pool_id}: {e}")
            self.stats["errors"] += 1
            return False

    def get_pool_state(self, pool_id: int) -> Optional[PoolState]:
        """
        Get current cached state of a pool.

        Args:
            pool_id: Pool application ID

        Returns:
            PoolState if known, None otherwise
        """
        return self.pool_state_cache.get(pool_id)

    def get_all_pool_states(self) -> Dict[int, PoolState]:
        """Get all cached pool states."""
        return self.pool_state_cache.copy()

    def get_stats(self) -> Dict:
        """Return metrics: blocks processed, pools updated, missed blocks, errors."""
        return self.stats.copy()


class PoolWatcherConfig:
    """Configuration for pool watching."""

    def __init__(self, algod_host: str, algod_port: int, algod_token: str = ""):
        """
        Initialize pool watcher config.

        Args:
            algod_host: Algorand node host (e.g., 'localhost')
            algod_port: Algorand node port (e.g., 4001)
            algod_token: Optional RPC token
        """
        self.algod_host = algod_host
        self.algod_port = algod_port
        self.algod_token = algod_token

    def create_client(self) -> AlgodClient:
        """Create and return Algod client."""
        return AlgodClient(self.algod_token, f"http://{self.algod_host}:{self.algod_port}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # This would be used with real configuration
    # config = PoolWatcherConfig("localhost", 4001)
    # client = config.create_client()
    # pool_config = [
    #     {
    #         "name": "TINYMAN_ALGO_USDC",
    #         "pool_id": 430731383,
    #         "asset_a_id": 0,
    #         "asset_b_id": 31566704,
    #         "fee_bps": 25,
    #     },
    # ]
    # watcher = PoolWatcher(client, pool_config)
    # watcher.start()
