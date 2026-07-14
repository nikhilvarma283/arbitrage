"""Example tests - remove after implementing actual tests."""

import pytest


def test_example_passing():
    """Example of a passing test."""
    assert 1 + 1 == 2


def test_example_with_fixture(mock_pool_state):
    """Example of using a fixture."""
    assert mock_pool_state["pool_id"] == 430731383
    assert mock_pool_state["reserve_a"] > 0


@pytest.mark.parametrize("a,b,expected", [
    (1, 1, 2),
    (2, 3, 5),
    (10, 20, 30),
])
def test_example_parametrized(a, b, expected):
    """Example of parametrized tests."""
    assert a + b == expected


# TODO: Delete this file and add real tests for each module (Sprint 2-4)
# See CONTRIBUTING.md for testing guidelines
