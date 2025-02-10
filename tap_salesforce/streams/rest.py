"""REST API implementation for Salesforce streams.

This module handles data extraction using Salesforce's REST API with comprehensive
error handling and logging.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
)

import backoff
import requests
from singer_sdk.pagination import BaseAPIPaginator

from tap_salesforce.exceptions import (
    QueryTimeoutError,
    RESTAPIError,
    RetryableSalesforceError,
    raise_for_error,
)
from tap_salesforce.streams.base import BaseSalesforceStream

if TYPE_CHECKING:
    from collections.abc import Iterator


class SalesforceRestPaginator(BaseAPIPaginator):
    """Paginator for Salesforce REST API endpoints."""

    def __init__(self) -> None:
        """Initialize the paginator."""
        super().__init__()
        self._next_records_url: str | None = None

    @property
    def current_value(self) -> str | None:
        """Get the current pagination value.

        Returns:
            URL for the next page of records, or None if no more pages
        """
        return self._next_records_url

    def advance(self, response: requests.Response) -> None:
        """Advance the paginator based on response.

        Args:
            response: Response from the last API call
        """
        response_json = response.json()
        self._next_records_url = response_json.get("nextRecordsUrl")
        self.finished = not bool(self._next_records_url)


class SalesforceRestStream(BaseSalesforceStream):
    """Stream class for Salesforce REST API endpoints."""

    # URL patterns for REST API
    URL_TEMPLATE = "{instance_url}/services/data/{api_version}/query"

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the REST stream."""
        super().__init__(*args, **kwargs)
        self._next_page_token: str | None = None
        self.request_timeout = self.config.get("request_timeout", 300)

    def get_url_params(
        self,
        context: dict[str, Any] | None,
        next_page_token: str | None,
    ) -> dict[str, str]:
        """Get URL query parameters.

        Args:
            context: Stream context
            next_page_token: Token for retrieving next page of data

        Returns:
            Dictionary of query parameters
        """
        # No params needed for subsequent pages
        if next_page_token:
            return {}

        return {"q": self.build_base_query(context)}

    @backoff.on_exception(
        backoff.expo,
        (RetryableSalesforceError, requests.exceptions.RequestException),
        max_tries=5,
        giveup=lambda e: not isinstance(e, RetryableSalesforceError),
    )
    def _request_with_backoff(
        self,
        prepared_request: requests.PreparedRequest,
        context: dict[str, Any] | None,
    ) -> requests.Response:
        """Make HTTP request with exponential backoff retry.

        Args:
            prepared_request: The prepared HTTP request
            context: Stream context

        Returns:
            The API response

        Raises:
            RESTAPIError: For REST API-specific errors
            QueryTimeoutError: If the query times out
            RetryableSalesforceError: For retryable errors
        """
        log_context = {
            "stream": self.name,
            "url": prepared_request.url,
            "method": prepared_request.method,
        }
        if context:
            log_context["context"] = context

        try:
            self.logger.debug(
                "Making REST API request",
                extra=log_context,
            )

            response = self.requests_session.send(
                prepared_request,
                timeout=self.request_timeout,
            )

            # Track API usage metrics
            self.authenticator.check_api_limits(response.headers)

            # Handle specific error cases
            bad_request_status = 400
            if (
                response.status_code == bad_request_status
                and "INVALID_QUERY" in response.text
            ):
                query_error_msg = f"Invalid SOQL query: {response.text}"
                self.logger.error(
                    "Invalid SOQL query",
                    extra={**log_context, "response": response.text},
                )
                raise RESTAPIError(query_error_msg)

            if (
                response.status_code == bad_request_status
                and "QUERY_TIMEOUT" in response.text
            ):
                timeout_msg = (
                    f"Query exceeded timeout of {self.request_timeout} seconds"
                )
                self.logger.error(
                    "Query timed out",
                    extra={
                        **log_context,
                        "timeout": self.request_timeout,
                        "response": response.text,
                    },
                )
                raise QueryTimeoutError(timeout_msg)

            response.raise_for_status()

            self.logger.debug(
                "REST API request completed successfully",
                extra={
                    **log_context,
                    "status_code": response.status_code,
                    "elapsed": response.elapsed.total_seconds(),
                },
            )

        except requests.exceptions.HTTPError as e:
            try:
                error_data = e.response.json()[0]
            except Exception:
                self.logger.warning(
                    "Could not parse error response as JSON",
                    extra={**log_context, "response": e.response.text},
                )
                error_data = {}

            # Let our error handler determine the appropriate exception
            raise_for_error(error_data)

        except requests.exceptions.Timeout as e:
            timeout_msg = f"Request exceeded timeout of {self.request_timeout} seconds"
            self.logger.exception(
                "Request timed out",
                extra={**log_context, "timeout": self.request_timeout},
            )
            raise QueryTimeoutError(timeout_msg) from e

        except requests.exceptions.RequestException as e:
            self.logger.exception(
                "Request failed",
                extra={**log_context, "error": str(e)},
            )
            raise RetryableSalesforceError(str(e)) from e
        else:
            return response

    def get_records(self, context: dict | None = None) -> Iterator[dict]:
        """Get records from Salesforce REST API.

        Args:
            context: Stream context

        Yields:
            Individual records from the REST API
        """
        try:
            paginator = self.get_new_paginator()
            next_page_token = None

            while not paginator.finished:
                prepared_request = self.prepare_request(context, next_page_token)
                response = self._request_with_backoff(prepared_request, context)
                records = self.parse_response(response)

                for record in records:
                    processed_record = self.post_process(record, context)
                    if processed_record:
                        yield processed_record

                # Advance the paginator
                paginator.advance(response)
                next_page_token = paginator.current_value

        except Exception as e:
            self.logger.exception(
                "Error syncing stream",
                extra={
                    "stream": self.name,
                    "error": str(e),
                    "context": context,
                },
            )
            raise
