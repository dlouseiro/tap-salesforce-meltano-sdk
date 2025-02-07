"""REST API integration tests."""

import datetime
from typing import List

import pytest

from tap_salesforce.clients.rest import RestClient


def test_rest_pagination(tap):
    """Test REST API pagination."""
    config = {**tap.config, "page_size": 2}  # Small page size to force pagination
    account_stream = next(s for s in tap.discover_streams() if s.name == "Account")
    account_stream.config = config

    records = list(account_stream.get_records(context={}))
    assert len(records) > 2  # Ensure we got more than one page


def test_rest_field_selection(tap):
    """Test field selection in REST API."""
    account_stream = next(s for s in tap.discover_streams() if s.name == "Account")

    # Select specific fields
    selected_fields = ["Id", "Name", "Industry"]
    account_stream._get_selected_fields = lambda: selected_fields

    records = list(account_stream.get_records(context={}))
    assert all(set(record.keys()).issubset(set(selected_fields)) for record in records)


def test_rest_error_handling(tap):
    """Test REST API error handling."""
    account_stream = next(s for s in tap.discover_streams() if s.name == "Account")

    # Inject invalid SOQL
    account_stream._build_query = lambda ctx: "SELECT Invalid FROM Account"

    with pytest.raises(Exception) as exc_info:
        list(account_stream.get_records(context={}))
    assert "INVALID_FIELD" in str(exc_info.value)
