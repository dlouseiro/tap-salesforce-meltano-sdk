"""Salesforce authentication handling.

This module implements authentication for Salesforce's REST and Bulk APIs, with
robust error handling and logging. It supports both OAuth 2.0 and password-based
authentication methods.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import backoff
from singer_sdk.authenticators import APIAuthenticatorBase
from singer_sdk.helpers._util import utc_now

from tap_salesforce.exceptions import (
    ExpiredCredentialsError,
    InvalidCredentialsError,
    SalesforceAuthError,
    RetryableSalesforceError,
    raise_for_error,
)

# Define URLs and timeouts
PROD_LOGIN_URL = "https://login.salesforce.com"
SANDBOX_LOGIN_URL = "https://test.salesforce.com"
DEFAULT_AUTH_TIMEOUT = 300  # 5 minutes

@dataclass
class OAuthCredentials:
    """OAuth 2.0 credentials for Salesforce."""
    client_id: str
    client_secret: str
    refresh_token: str

    def __bool__(self) -> bool:
        """Check if all required OAuth fields are present."""
        return all((self.client_id, self.client_secret, self.refresh_token))

@dataclass
class PasswordCredentials:
    """Username/password credentials for Salesforce."""
    username: str
    password: str
    security_token: str

    def __bool__(self) -> bool:
        """Check if all required password auth fields are present."""
        return all((self.username, self.password, self.security_token))

class SalesforceAuthenticator(APIAuthenticatorBase):
    """Salesforce API authenticator.

    Handles authentication for both REST and Bulk APIs with comprehensive
    error handling and logging.
    """

    def __init__(
            self,
            stream_name: str,
            config: dict[str, Any],
    ) -> None:
        """Initialize the authenticator.

        Args:
            stream_name: Name of the stream using this authenticator
            config: Tap configuration dictionary
        """
        super().__init__(stream_name=stream_name)
        self._config = config
        self.logger = logging.getLogger("tap_salesforce.authenticator")

        # Initialize auth-related attributes
        self._access_token: str | None = None
        self._instance_url: str | None = None
        self._last_refreshed: datetime | None = None
        self._expires_in: int | None = None

        # Track API usage
        self.rest_requests_attempted = 0
        self.jobs_completed = 0

        # Get login URL based on environment
        self.is_sandbox = config.get("is_sandbox", False)
        self.base_url = SANDBOX_LOGIN_URL if self.is_sandbox else PROD_LOGIN_URL

        # Set up logging with context
        self._setup_logging_context()

    def _setup_logging_context(self) -> None:
        """Configure logging with authentication context."""
        self.log_context = {
            "authenticator": "salesforce",
            "stream": self.stream_name,
            "sandbox": self.is_sandbox,
            "auth_type": self._config.get("auth_type"),
        }

    @property
    def auth_headers(self) -> dict:
        """Get authentication headers.

        Returns:
            Dictionary of auth headers

        Raises:
            SalesforceAuthError: If unable to get valid auth headers
        """
        if not self.is_token_valid():
            try:
                self._refresh_access_token()
            except Exception as e:
                self.logger.error(
                    "Failed to refresh access token",
                    extra={**self.log_context, "error": str(e)},
                )
                raise SalesforceAuthError(
                    f"Unable to authenticate: {str(e)}"
                ) from e

        return {"Authorization": f"Bearer {self._access_token}"}

    @property
    def oauth_request_body(self) -> dict:
        """Get OAuth token request body.

        Returns:
            Dictionary containing OAuth request parameters

        Raises:
            InvalidCredentialsError: If credentials are missing or invalid
        """
        auth_type = self._config["auth_type"]

        if auth_type == "oauth":
            credentials = OAuthCredentials(
                client_id=self._config.get("client_id", ""),
                client_secret=self._config.get("client_secret", ""),
                refresh_token=self._config.get("refresh_token", ""),
            )
            if not credentials:
                raise InvalidCredentialsError(
                    "Missing OAuth credentials. Need client_id, client_secret, "
                    "and refresh_token."
                )

            return {
                "grant_type": "refresh_token",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "refresh_token": credentials.refresh_token,
            }

        elif auth_type == "password":
            credentials = PasswordCredentials(
                username=self._config.get("username", ""),
                password=self._config.get("password", ""),
                security_token=self._config.get("security_token", ""),
            )
            if not credentials:
                raise InvalidCredentialsError(
                    "Missing password authentication credentials. Need username, "
                    "password, and security_token."
                )

            return {
                "grant_type": "password",
                "client_id": credentials.username,
                "client_secret": f"{credentials.password}{credentials.security_token}",
            }

        raise InvalidCredentialsError(f"Invalid auth_type: {auth_type}")

    def is_token_valid(self) -> bool:
        """Check if the current access token is valid.

        A token is considered valid if:
        1. We have an access token
        2. We know when it was last refreshed
        3. It hasn't expired (with 5-minute buffer)

        Returns:
            True if the token is valid
        """
        if not all([self._access_token, self._last_refreshed, self._expires_in]):
            return False

        # Add 5-minute buffer before expiration
        expiration = self._last_refreshed + timedelta(
            seconds=self._expires_in - 300
        )
        return utc_now() < expiration

    @backoff.on_exception(
        backoff.expo,
        (RetryableSalesforceError, requests.exceptions.RequestException),
        max_tries=5,
        giveup=lambda e: not isinstance(e, RetryableSalesforceError),
    )
    def _refresh_access_token(self) -> None:
        """Refresh the access token.

        Raises:
            ExpiredCredentialsError: If refresh token has expired
            InvalidCredentialsError: If credentials are invalid
            RetryableSalesforceError: For temporary auth failures
            SalesforceAuthError: For other auth-related errors
        """
        request_time = utc_now()
        auth_url = f"{self.base_url}/services/oauth2/token"

        try:
            response = requests.post(
                auth_url,
                data=self.oauth_request_body,
                timeout=DEFAULT_AUTH_TIMEOUT,
            )

            if response.status_code == 401:
                raise InvalidCredentialsError(
                    f"Authentication failed: {response.text}"
                )

            response.raise_for_status()
            token_json = response.json()

            self._access_token = token_json["access_token"]
            self._instance_url = token_json["instance_url"]
            self._expires_in = int(token_json.get("expires_in", 7200))
            self._last_refreshed = request_time

            self.logger.info(
                "Successfully refreshed Salesforce access token",
                extra={
                    **self.log_context,
                    "expires_in": self._expires_in,
                    "instance_url": self._instance_url,
                },
            )

        except requests.exceptions.HTTPError as e:
            # Parse error response
            try:
                error_json = e.response.json()[0]
                error_code = error_json.get("errorCode")
                message = error_json.get("message", str(e))
            except Exception:
                error_code = None
                message = str(e)

            if error_code in ["INVALID_GRANT", "EXPIRED_ACCESS_TOKEN"]:
                raise ExpiredCredentialsError(
                    f"Refresh token has expired: {message}",
                    error_code=error_code,
                )

            # Let raise_for_error handle other error types
            raise_for_error({"errorCode": error_code, "message": message})

        except requests.exceptions.RequestException as e:
            self.logger.error(
                "Network error during token refresh",
                extra={**self.log_context, "error": str(e)},
            )
            raise RetryableSalesforceError(
                f"Network error during authentication: {str(e)}"
            ) from e

    def check_api_limits(self, headers: dict) -> None:
        """Check API quota usage from response headers.

        Args:
            headers: Response headers from a Salesforce API request

        Raises:
            QuotaExceededException: If quota limits would be exceeded
        """
        limit_header = headers.get("Sforce-Limit-Info", "")
        if not limit_header:
            return

        try:
            usage = limit_header.split("=")[1]
            used, total = map(int, usage.split("/"))
            percent_used = (used / total) * 100

            # Log current usage
            self.logger.info(
                "API quota usage",
                extra={
                    **self.log_context,
                    "used": used,
                    "total": total,
                    "percent_used": percent_used,
                },
            )

            # Check against configured limits
            max_percent = self._config.get("quota_percent_total", 80)
            max_requests = int(
                (self._config.get("quota_percent_per_run", 25) * total) / 100
            )

            if percent_used > max_percent:
                raise QuotaExceededException(
                    f"Total API quota usage ({percent_used:.1f}%) exceeds "
                    f"limit of {max_percent}%"
                )

            if self.rest_requests_attempted > max_requests:
                raise QuotaExceededException(
                    f"Per-run API quota usage ({self.rest_requests_attempted} "
                    f"requests) exceeds limit of {max_requests} requests"
                )

        except (IndexError, ValueError) as e:
            self.logger.warning(
                "Could not parse quota usage from header",
                extra={
                    **self.log_context,
                    "header": limit_header,
                    "error": str(e),
                },
            )

class QuotaExceededException(Exception):
    """Raised when Salesforce API quota limits would be exceeded."""
