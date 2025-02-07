"""Bulk API integration tests."""

# mypy: disable-error-code="no-untyped-def"

import time
from typing import List

import pytest


def test_bulk_query_execution(tap):
    """Test Bulk API query execution."""
    config = {**tap.config, "api_type": "BULK"}
    tap.config = config

    # Before stream lookup
    streams = tap.discover_streams()
    account_stream = next(s for s in streams if s.name == "Account")
    start_time = time.time()

    records = list(account_stream.get_records(context={}))
    duration = time.time() - start_time

    assert len(records) > 0
    assert all("Id" in record for record in records)


def test_bulk_parallel_processing(tap):
    """Test Bulk API parallel processing."""
    config = {
        **tap.config,
        "api_type": "BULK",
        "bulk_api_hints": True,
    }
    tap.config = config

    streams = tap.discover_streams()
    opportunity_stream = next(s for s in streams if s.name == "Opportunity")

    records = list(opportunity_stream.get_records(context={}))
    assert len(records) > 0


@pytest.mark.parametrize("include_deleted", [True, False])
def test_bulk_deleted_records(tap, include_deleted):
    """Test Bulk API deleted record handling."""
    config = {
        **tap.config,
        "api_type": "BULK",
        "include_deleted": include_deleted,
    }
    tap.config = config

    streams = tap.discover_streams()
    account_stream = next(s for s in streams if s.name == "Account")
    records = list(account_stream.get_records(context={}))

    if include_deleted:
        # Verify IsDeleted field is present when requested
        assert any(record.get("IsDeleted") for record in records)


def test_bulk2_locator(tap):
    """Test Bulk 2.0 API locator functionality."""
    config = {
        **tap.config,
        "api_type": "BULK2",
        "bulk2_use_locator": True,
    }
    tap.config = config

    streams = tap.discover_streams()
    account_stream = next(s for s in streams if s.name == "Account")
    records = list(account_stream.get_records(context={}))

    assert len(records) > 0


def test_bulk2_error_handling(tap):
    """Test Bulk 2.0 API error handling and failed results."""
    config = {**tap.config, "api_type": "BULK2"}
    tap.config = config

    streams = tap.discover_streams()
    account_stream = next(s for s in streams if s.name == "Account")

    # Inject invalid SOQL
    account_stream._build_query = lambda ctx: "SELECT Invalid FROM Account"

    with pytest.raises(Exception) as exc_info:
        list(account_stream.get_records(context={}))

    # Verify failed results are accessible
    assert hasattr(account_stream.client, "get_failed_results")
