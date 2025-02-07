"""Integration test configuration and fixtures."""

import os
from typing import Any, Dict

import pytest
from singer_sdk.testing import get_tap_test_class

from tap_salesforce.tap import TapSalesforce


@pytest.fixture(scope="session")
def tap_config() -> Dict[str, Any]:
    """Get test config from environment variables."""
    return {
        "auth_type": os.getenv("TAP_SALESFORCE_AUTH_TYPE", "oauth2"),
        "client_id": os.getenv("TAP_SALESFORCE_CLIENT_ID"),
        "client_secret": os.getenv("TAP_SALESFORCE_CLIENT_SECRET"),
        "refresh_token": os.getenv("TAP_SALESFORCE_REFRESH_TOKEN"),
        "start_date": "2023-01-01T00:00:00Z",
        "api_type": os.getenv("TAP_SALESFORCE_API_TYPE", "REST"),
        "select_fields_by_default": True,
        "is_sandbox": os.getenv("TAP_SALESFORCE_IS_SANDBOX", "false").lower() == "true",
    }


@pytest.fixture(scope="session")
def tap(tap_config) -> TapSalesforce:
    """Get configured tap instance."""
    return TapSalesforce(config=tap_config)
