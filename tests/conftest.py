"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def test_data_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_pool_state():
    """Return a mock pool state for testing."""
    return {
        "pool_id": 430731383,
        "pool_name": "TINYMAN_ALGO_USDC",
        "asset_a_id": 0,
        "asset_b_id": 31566704,
        "reserve_a": 1000000.0,
        "reserve_b": 500000.0,
        "fee_bps": 25,
        "updated_at": 30000000,
    }


@pytest.fixture
def mock_block_data():
    """Return mock Algorand block data."""
    return {
        "rnd": 30000000,
        "ts": 1626000000,
        "prev": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "gen": "mainnet-v1.0",
    }


# Add more fixtures as needed for each sprint
