"""Base client handling."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from singer_sdk.authenticators import APIAuthenticatorBase
from singer_sdk.helpers._util import utc_now
from singer_sdk.streams import RESTStream


class SalesforceClient(ABC):
    """Abstract base client for Salesforce."""

    def __init__(
        self, authenticator: APIAuthenticatorBase, config: dict, api_version: str = "v57.0"
    ) -> None:
        """Initialize client.

        Args:
            authenticator: API authenticator instance
            config: Tap configuration
            api_version: Salesforce API version to use
        """
        self._authenticator = authenticator
        self.config = config
        self.api_version = api_version.lstrip("v")

    @property
    def authenticator(self) -> APIAuthenticatorBase:
        """Get authenticator instance."""
        return self._authenticator

    @property
    def url_base(self) -> str:
        """Get base URL for API."""
        return f"{self.authenticator.instance_url}/services/data/v{self.api_version}"

    @abstractmethod
    def query(self, query: str, include_deleted: bool = False) -> Iterable[dict]:
        """Execute query and return results.

        Args:
            query: SOQL query string
            include_deleted: Whether to include deleted records

        Returns:
            Iterator of records
        """
        pass

    def describe_global(self) -> Dict[str, Any]:
        """Get information about all objects available in the org.

        Returns:
            Dictionary containing information about all objects
        """
        url = f"{self.url_base}/sobjects"
        response = self._make_request("GET", url)
        return response.json()

    def describe_object(self, object_name: str) -> dict[str, Any]:
        """Get metadata about specific object.

        Args:
            object_name: API name of the Salesforce object

        Returns:
            Object metadata
        """
        url = f"{self.url_base}/sobjects/{object_name}/describe"
        response = self._make_request("GET", url)
        return response.json()

    def get_object_count(self, object_name: str) -> int:
        """Get total number of records for an object.

        Args:
            object_name: API name of the Salesforce object

        Returns:
            Total record count
        """
        query = f"SELECT COUNT() FROM {object_name}"
        response = self._make_request("GET", f"{self.url_base}/query", params={"q": query})
        return response.json()["totalSize"]

    def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an authenticated request to Salesforce.

        Args:
            method: HTTP method
            url: Request URL
            params: URL parameters
            json: JSON body
            **kwargs: Additional request parameters

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        headers = self.authenticator.auth_headers

        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=json,
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()

        return response

    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle rate limiting response.

        Args:
            response: Response object

        Raises:
            Exception: If rate limit is exceeded
        """
        if response.status_code == 429:  # Too Many Requests
            retry_after = int(response.headers.get("Retry-After", 60))
            raise Exception(f"Rate limit exceeded. Retry after {retry_after} seconds.")
