"""Salesforce authentication handling."""

# mypy: disable-error-code="no-untyped-def"
from datetime import datetime, timedelta
from typing import Any

import requests
from singer_sdk.authenticators import OAuthAuthenticator
from singer_sdk.helpers._util import utc_now


class SalesforceAuthenticator(OAuthAuthenticator):
    """Authenticator class for Salesforce."""

    def __init__(
        self,
        stream,
        auth_endpoint: str = "https://login.salesforce.com",
    ) -> None:
        """Initialize authenticator.

        Args:
            stream: The stream instance to authenticate
            auth_endpoint: The base authentication endpoint (sandbox or
                production)
        """
        super().__init__(stream=stream)

        # Set auth endpoint based on sandbox configuration
        is_sandbox = self.config.get("is_sandbox")
        self.auth_endpoint = "https://test.salesforce.com" if is_sandbox else auth_endpoint

        self._access_token: str | None = None
        self._instance_url: str | None = None
        self._expires_at: datetime | None = None

    @property
    def auth_headers(self) -> dict[str, Any]:
        """Return the authentication headers.

        Returns:
            Headers dictionary with authentication information
        """
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    @property
    def access_token(self) -> str | None:
        """Get the current access token.

        Returns:
            The current access token

        Raises:
            Exception: If authentication fails
        """
        self._ensure_access_token()
        return self._access_token

    @property
    def instance_url(self) -> str | None:
        """Get the Salesforce instance URL.

        Returns:
            The instance URL

        Raises:
            Exception: If no instance URL is available
        """
        if not self._instance_url:
            self._ensure_access_token()
        return self._instance_url

    def _ensure_access_token(self) -> None:
        """Ensure we have a valid access token."""
        if self._is_token_valid():
            return

        auth_type = self.config.get("auth_type", "oauth2")

        if auth_type == "oauth2":
            self._handle_oauth2_auth()
        elif auth_type == "password":
            self._handle_password_auth()
        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")

    def _is_token_valid(self) -> bool:
        """Check if the current token is valid.

        Returns:
            True if token is valid, False otherwise
        """
        if not self._access_token or not self._expires_at:
            return False

        # Add buffer to prevent token expiration during request
        buffer_seconds = 300  # 5 minutes
        return utc_now() < (self._expires_at - timedelta(seconds=buffer_seconds))

    def _handle_oauth2_auth(self) -> None:
        """Handle OAuth 2.0 authentication flow."""
        token_url = urllib.parse.urljoin(self.auth_endpoint, "/services/oauth2/token")

        response = requests.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
                "refresh_token": self.config["refresh_token"],
            },
            timeout=30,
        )

        self._handle_token_response(response)

    def _handle_password_auth(self) -> None:
        """Handle password-based authentication flow."""
        token_url = urljoin(self.auth_endpoint, "/services/oauth2/token")
        security_token = self.config.get("security_token", "")
        password = f"{self.config['password']}{security_token}"

        response = requests.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
                "username": self.config["username"],
                "password": password,
            },
            timeout=30,
        )

        self._handle_token_response(response)

    def _handle_token_response(self, response: requests.Response) -> None:
        """Handle the token endpoint response.

        Args:
            response: Response from token endpoint

        Raises:
            Exception: If authentication fails
        """
        try:
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            self._instance_url = data["instance_url"]

            # Salesforce tokens typically expire in 2 hours
            expires_in = int(data.get("expires_in", 7200))
            self._expires_at = utc_now() + timedelta(seconds=expires_in)

        except requests.exceptions.HTTPError as e:
            error_details = e.response.json()
            raise Exception(
                f"Authentication failed: {error_details.get('error_description', str(e))}"
            )
        except (KeyError, ValueError) as e:
            raise Exception(f"Invalid authentication response: {str(e)}")

    def validate_token(self, token: str) -> bool:
        """Validate an access token.

        Args:
            token: Access token to validate

        Returns:
            True if token is valid, False otherwise
        """
        url = urljoin(self._instance_url, "/services/data/v57.0/")
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,  # 30 second timeout
        )
        return response.status_code == 200
