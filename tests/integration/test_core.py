"""Core integration tests."""
# mypy: disable-error-code="no-untyped-def"
import datetime
from typing import Dict, List

import pytest
from singer_sdk.testing import get_standard_tap_tests

from tap_salesforce.tap import TapSalesforce


def test_standard_tap_tests(tap_config):
    """Run standard tap tests."""
    tests = get_standard_tap_tests(TapSalesforce, config=tap_config)
    for test in tests:
        test()


def test_discover_mode(tap):
    """Test catalog discovery."""
    catalog = tap.discover_streams()

    # Verify common objects are present
    common_objects = {"Account", "Contact", "Opportunity", "Lead"}
    discovered_objects = {stream.name for stream in catalog}

    for obj in common_objects:
        assert obj in discovered_objects, f"Missing common object: {obj}"

    # Verify schema structure for a specific object
    account_stream = next(s for s in catalog if s.name == "Account")
    schema = account_stream.schema

    assert schema["type"] == "object"
    assert "Id" in schema["properties"]
    assert "Name" in schema["properties"]
    assert "CreatedDate" in schema["properties"]


def test_basic_read(tap):
    """Test basic record extraction."""
    account_stream = next(s for s in tap.discover_streams() if s.name == "Account")
    records = list(account_stream.get_records(context={}))

    assert len(records) > 0
    assert all("Id" in record for record in records)
    assert all("Name" in record for record in records)


@pytest.mark.parametrize("api_type", ["REST", "BULK", "BULK2"])
def test_api_types(tap_config, api_type):
    """Test different API types."""
    config = {**tap_config, "api_type": api_type}
    tap = TapSalesforce(config=config)

    account_stream = next(s for s in tap.discover_streams() if s.name == "Account")
    records = list(account_stream.get_records(context={}))

    assert len(records) > 0
