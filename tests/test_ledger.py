"""
Tests for ledger module.

Sprint 2.3: Ledger Testing
"""

import pytest
import tempfile
import os
from datetime import date
from src.ledger import Ledger


@pytest.fixture
def temp_ledger():
    """Create temporary ledger for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    ledger = Ledger(db_path)
    yield ledger
    # Close the sqlite connection before unlinking -- on Windows, deleting a
    # file a process still has open raises PermissionError (WinError 32);
    # Linux permits it, which is why this went unnoticed on CI.
    ledger.close()
    os.unlink(db_path)


class TestLedgerInitialization:
    """Test ledger initialization."""

    def test_create_ledger(self, temp_ledger):
        """Test creating a new ledger."""
        assert temp_ledger.db_path is not None
        assert temp_ledger.conn is not None

    def test_schema_created(self, temp_ledger):
        """Test that schema is created on initialization."""
        # TODO: Query schema_tables
        # TODO: Verify opportunities, trades, daily_summary tables exist
        pass


class TestLedgerOpportunities:
    """Test opportunity logging."""

    def test_log_opportunity(self, temp_ledger):
        """Test logging an opportunity.

        TODO:
        - Create opportunity
        - Call log_opportunity()
        - Verify inserted in database
        - Verify row ID returned
        """
        # TODO: Implement
        pass

    def test_log_multiple_opportunities(self, temp_ledger):
        """Test logging multiple opportunities."""
        # TODO: Log 100 opportunities
        # TODO: Verify all inserted
        # TODO: Verify no data loss
        pass

    def test_export_opportunities(self, temp_ledger):
        """Test exporting opportunities for dashboard."""
        # TODO: Log opportunities
        # TODO: Call export_for_dashboard()
        # TODO: Verify format
        # TODO: Verify filtering by date range
        pass


class TestLedgerTrades:
    """Test trade logging."""

    def test_log_trade(self, temp_ledger):
        """Test logging a trade submission.

        TODO:
        - Create opportunity and log trade
        - Verify status="submitted"
        - Verify row ID returned
        """
        # TODO: Implement
        pass

    def test_update_trade_result_won(self, temp_ledger):
        """Test updating trade result (won).

        TODO:
        - Log trade, then update with status="won"
        - Verify actual_profit_usd is set
        - Verify settled_at timestamp is updated
        """
        # TODO: Implement
        pass

    def test_update_trade_result_lost(self, temp_ledger):
        """Test updating trade result (lost race).

        TODO:
        - Log trade, then update with status="lost"
        - Verify reason field set
        """
        # TODO: Implement
        pass

    def test_update_trade_result_failed(self, temp_ledger):
        """Test updating trade result (failed).

        TODO:
        - Log trade, then update with status="failed"
        - Verify gas_spent_usd set
        - Verify reason (network error, timeout, etc.)
        """
        # TODO: Implement
        pass


class TestLedgerDailySummary:
    """Test daily KPI calculation."""

    @pytest.mark.skip(
        reason="Ledger has no get_daily_summary() -- this test targets an "
        "opportunities/trades/daily_summary API from an earlier design that "
        "was superseded by the cycles/funnel_report model (see get_funnel_report)"
    )
    def test_get_daily_summary_empty(self, temp_ledger):
        """Test daily summary with no data."""
        summary = temp_ledger.get_daily_summary(date.today())
        assert summary["opportunities_detected"] == 0
        assert summary["trades_submitted"] == 0

    def test_get_daily_summary_with_data(self, temp_ledger):
        """Test daily summary with opportunities and trades.

        TODO:
        - Log 100 opportunities, 50 trades
        - Call get_daily_summary()
        - Verify win_rate = (trades_won / trades_submitted)
        - Verify net_profit_usd = total_profit_usd - total_gas_usd
        - Verify decay_ratio if applicable
        """
        # TODO: Implement
        pass

    def test_decay_ratio_calculation(self, temp_ledger):
        """Test decay_ratio (last week / first week).

        TODO:
        - Log opportunities over 14 days
        - Calculate decay_ratio
        - Verify formula: (profit_week2) / (profit_week1)
        """
        # TODO: Implement
        pass


class TestLedgerDataIntegrity:
    """Test data integrity and validation."""

    @pytest.mark.skip(reason="Ledger has no validate() method implemented yet")
    def test_validate_empty_db(self, temp_ledger):
        """Test validation on empty database."""
        is_valid = temp_ledger.validate()
        assert is_valid is True

    def test_validate_with_data(self, temp_ledger):
        """Test validation with data."""
        # TODO: Log data, then validate
        # TODO: Verify returns True
        pass

    def test_negative_profit_detection(self, temp_ledger):
        """Test that negative profits are detected (should be impossible).

        TODO:
        - Insert trade with negative profit (should trigger error)
        - Verify validation catches it
        """
        # TODO: Implement
        pass


class TestLedgerStress:
    """Stress tests for ledger."""

    @pytest.mark.skip(reason="Takes time")
    def test_1m_opportunities_write(self, temp_ledger):
        """Test writing 1M opportunities.

        TODO:
        - Insert 1M opportunities
        - Verify zero corruption
        - Measure performance (should be fast)
        - Verify database size < 500MB
        """
        # TODO: Implement
        pass

    @pytest.mark.skip(reason="Takes time")
    def test_query_performance(self, temp_ledger):
        """Test query performance with large dataset.

        TODO:
        - Insert 100k opportunities
        - Query daily_summary (should be <10ms)
        - Query export_for_dashboard (should be <100ms)
        """
        # TODO: Implement
        pass


class TestLedgerContext:
    """Test context manager usage."""

    def test_context_manager(self):
        """Test using ledger with context manager."""
        # TODO: Use: with Ledger(path) as ledger: ...
        # TODO: Verify close() called automatically
        pass
