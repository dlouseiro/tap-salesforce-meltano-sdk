"""Test configuration and fixtures."""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from singer_sdk.authenticators import APIAuthenticatorBase


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Create a mock configuration."""
    return {
        "auth_type": "oauth2",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "refresh_token": "test_refresh_token",
        "start_date": "2023-01-01T00:00:00Z",
        "api_type": "REST",
        "select_fields_by_default": True,
    }

@pytest.fixture
def mock_auth_token() -> str:
    """Create a mock authentication token."""
    return "mock_access_token"

@pytest.fixture
def mock_instance_url() -> str:
    """Create a mock Salesforce instance URL."""
    return "https://test.salesforce.com"

@pytest.fixture
def mock_authenticator(mock_auth_token, mock_instance_url) -> MagicMock:
    """Create a mock authenticator."""
    authenticator = MagicMock(spec=APIAuthenticatorBase)
    authenticator.access_token = mock_auth_token
    authenticator.instance_url = mock_instance_url
    authenticator.auth_headers = {"Authorization": f"Bearer {mock_auth_token}"}
    return authenticator

@pytest.fixture
def sample_object_metadata() -> Dict[str, Any]:
    """Create sample Salesforce object metadata."""
    return {
        "fields": [
            {
                "name": "Id",
                "type": "id",
                "label": "Record ID",
                "updateable": False,
            },
            {
                "name": "Name",
                "type": "string",
                "label": "Name",
                "updateable": True,
            },
            {
                "name": "CreatedDate",
                "type": "datetime",
                "label": "Created Date",
                "updateable": False,
            },
            {
                "name": "LastModifiedDate",
                "type": "datetime",
                "label": "Last Modified Date",
                "updateable": False,
            },
        ]
    }
    }
