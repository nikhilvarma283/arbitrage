#!/usr/bin/env python3
"""
Bootstrap script to discover and lock pool app IDs.

Usage:
    python scripts/discover_pools.py --algod-host algod --algod-port 8080 --token <token>

This script:
1. Connects to Algorand mainnet
2. Discovers pools from all DEXes
3. Creates pools.lock.json with resolved app IDs
4. Verifies assets (USDC, goBTC, goETH)

NOTE: Requires internet access to fetch Pact/Humble/Vestige APIs
"""

import argparse
import json
import logging
from pathlib import Path
from algosdk.v2client.algod import AlgodClient

from src.pool_discovery import PoolDiscovery, ASSETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Discover and lock pool app IDs")
    parser.add_argument("--algod-host", default="localhost", help="Algod host")
    parser.add_argument("--algod-port", type=int, default=4001, help="Algod port")
    parser.add_argument("--token", default="", help="Algod token")

    args = parser.parse_args()

    # Connect to algod
    logger.info(f"Connecting to algod at {args.algod_host}:{args.algod_port}...")
    client = AlgodClient(args.token, f"http://{args.algod_host}:{args.algod_port}")

    try:
        status = client.status()
        logger.info(f"Connected! Block: {status['last-round']}")
    except Exception as e:
        logger.error(f"Failed to connect to algod: {e}")
        return 1

    # Initialize discovery
    discovery = PoolDiscovery(client)

    # Define pairs to discover
    pairs = [
        (ASSETS["ALGO"], ASSETS["USDC"]),
        (ASSETS["ALGO"], ASSETS["USDT"]),
        (ASSETS["USDC"], ASSETS["USDT"]),
    ]

    logger.info(f"Discovering pools for {len(pairs)} pairs across 4 DEXes...")

    # Verify assets first
    logger.info("Verifying asset IDs...")
    if not discovery.verify_assets():
        logger.error("Asset verification failed")
        return 1

    # Discover pools
    pools = discovery.discover_all(pairs)

    logger.info("Pool discovery complete!")
    logger.info(f"Lockfile saved to: {discovery.lockfile.lock_path}")

    # Summary
    logger.info("\n" + "="*60)
    logger.info("DISCOVERY SUMMARY")
    logger.info("="*60)

    for dex, dex_pools in pools.items():
        logger.info(f"\n{dex.upper()}:")
        for pair, pool_info in dex_pools.items():
            asset_a, asset_b = pair
            app_id = pool_info.get("app_id", "PENDING")
            logger.info(f"  {asset_a}/{asset_b}: app_id={app_id}")

    logger.info("\n" + "="*60)
    logger.info("NEXT STEPS:")
    logger.info("="*60)
    logger.info("1. Verify pools.lock.json has correct app IDs")
    logger.info("2. If any app_id is null, manually add to lockfile")
    logger.info("3. Run: python -m src.main --config config/bot.multi-dex.yaml")
    logger.info("="*60)

    return 0


if __name__ == "__main__":
    exit(main())
