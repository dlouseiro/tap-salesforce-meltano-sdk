"""Unit tests for authentication."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import HTTPError

from tap_salesforce.auth.authenticator import SalesforceAuthenticator


class TestSalesforceAuthenticator:
    """Test cases for Salesforce authenticator."""

    def test_oauth2_authentication(self, mock_config):
        """Test OAuth 2.0 authentication flow."""
        authenticator = SalesforceAuthenticator(MagicMock())
        authenticator.config = mock_config

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_token",
            "instance_url": "https://test.salesforce.com",
            "expires_in": 7200,
        }

        with patch("requests.post", return_value=mock_response):
            token = authenticator.access_token
            assert token == "new_token"
            assert authenticator.instance_url == "https://test.salesforce.com"

    def test_password_authentication(self, mock_config):
        """Test password-based authentication."""
        config = {**mock_config, "auth_type": "password", "username": "test", "password": "test"}
        authenticator = SalesforceAuthenticator(MagicMock())
        authenticator.config = config

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "password_token",
            "instance_url": "https://test.salesforce.com",
        }

        with patch("requests.post", return_value=mock_response):
            token = authenticator.access_token
            assert token == "password_token"

    def test_token_refresh(self, mock_config):
        """Test token refresh behavior."""
        authenticator = SalesforceAuthenticator(MagicMock())
        authenticator.config = mock_config

        # Set expired token
        authenticator._access_token = "old_token"
        authenticator._expires_at = datetime.utcnow() - timedelta(hours=1)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "refreshed_token",
            "instance_url": "https://test.salesforce.com",
        }

        with patch("requests.post", return_value=mock_response):
            token = authenticator.access_token
            assert token == "refreshed_token"

    def test_authentication_error(self, mock_config):
        """Test authentication error handling."""
        authenticator = SalesforceAuthenticator(MagicMock())
        authenticator.config = mock_config

        error_response = MagicMock()
        error_response.raise_for_status.side_effect = HTTPError("Invalid credentials")
        error_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid refresh token",
        }

        with patch("requests.post", return_value=error_response):
            with pytest.raises(Exception) as exc_info:
                _ = authenticator.access_token
            assert "Invalid refresh token" in str(exc_info.value)
