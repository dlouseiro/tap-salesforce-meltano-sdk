"""Salesforce Bulk 2.0 API stream implementation.

This module handles data extraction using Salesforce's Bulk 2.0 API with comprehensive
error handling, job monitoring, and logging. Key improvements over Bulk 1.0:
- No batches to manage - just single jobs
- Automatic optimization and chunking
- Better monitoring capabilities
- Improved error handling with detailed job info
"""

from __future__ import annotations

import time
from typing import (
    TYPE_CHECKING,
    Any,
)

import backoff
import requests
from singer_sdk import metrics

from tap_salesforce.exceptions import (
    Bulk2APIError,
    RetryableSalesforceError,
    raise_for_error, JobTimeoutError,
)
from tap_salesforce.streams.base import BaseSalesforceStream

if TYPE_CHECKING:
    from collections.abc import Iterator

# Bulk 2.0 specific constants
MAX_BULK2_RECORDS = 1_000_000_000  # 1B records per job
DEFAULT_TIMEOUT = 20 * 60  # 20 minutes
POLL_INTERVAL = 5  # Seconds between status checks
MAX_RETRIES = 3  # Number of retries for failed operations


class SalesforceBulk2Stream(BaseSalesforceStream):
    """Stream class for Salesforce Bulk 2.0 API.

    Key improvements over Bulk 1.0:
    1. No batch management needed
    2. Automatic optimization
    3. Simplified job lifecycle
    4. Better monitoring capabilities
    """

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the Bulk 2.0 stream."""
        super().__init__(*args, **kwargs)
        self.job_timeout = self.config.get("job_timeout", DEFAULT_TIMEOUT)
        self._current_job_id: str | None = None

        # Set up metrics tracking
        self.job_timer = metrics.Timer(metrics.Metric.JOB_DURATION)
        self.records_timer = metrics.Timer(metrics.Metric.RECORD_COUNT)

    def _extract_error_details(
        self, response: requests.Response
    ) -> tuple[str | None, str]:
        """Extract error details from a response.

        Args:
            response: HTTP response

        Returns:
            Tuple of (error_code, error_message)
        """
        try:
            error_data = response.json()[0]
            error_code = error_data.get("errorCode")
            error_message = error_data.get("message", response.text)
        except (IndexError, TypeError, ValueError):
            error_code = None
            error_message = response.text

        return error_code, error_message

    def _normalize_retry_after(self, retry_after: str | None) -> int:
        """Normalize retry-after header value.

        Args:
            retry_after: Raw retry-after value from headers

        Returns:
            Integer retry after value in seconds
        """
        try:
            return int(retry_after) if retry_after is not None else 60
        except ValueError:
            return 60

    def _validate_response(self, response: requests.Response) -> requests.Response:
        """Validate and process the API response.

        Args:
            response: HTTP response to validate

        Returns:
            Validated response

        Raises:
            RetryableSalesforceError: For rate limit or temporary errors
        """
        log_context = {
            "stream": self.name,
            "url": response.url,
            "method": response.request.method,
            "job_id": self._current_job_id,
        }

        if not response.ok:
            error_code, error_message = self._extract_error_details(response)

            log_context["error"] = error_message
            log_context["error_code"] = error_code

            if error_code in ["LIMIT_EXCEEDED", "REQUEST_LIMIT_EXCEEDED"]:
                self.logger.error(
                    "Bulk 2.0 API limit exceeded",
                    extra=log_context,
                )
                retry_after = self._normalize_retry_after(
                    response.headers.get("Retry-After")
                )
                raise RetryableSalesforceError(
                    error_message,
                    retry_after=retry_after,
                )

            # Let our error handler determine appropriate exception
            raise_for_error({"errorCode": error_code, "message": error_message})

        return response

    @backoff.on_exception(
        backoff.expo,
        (RetryableSalesforceError, requests.exceptions.RequestException),
        max_tries=MAX_RETRIES,
        giveup=lambda e: not isinstance(e, RetryableSalesforceError),
    )
    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Make HTTP request with error handling and backoff.

        Args:
            method: HTTP method to use
            url: URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            Bulk2APIError: For Bulk API 2.0 specific errors
            RetryableSalesforceError: For temporary failures
        """
        log_context = {
            "stream": self.name,
            "url": url,
            "method": method,
            "job_id": self._current_job_id,
        }

        try:
            self.logger.debug(
                "Making Bulk 2.0 API request",
                extra=log_context,
            )

            response = requests.request(
                method, url, timeout=self.config.get("request_timeout", 300), **kwargs
            )

            return self._validate_response(response)

        except requests.exceptions.RequestException as e:
            self.logger.exception(
                "Bulk 2.0 API request failed",
                extra={**log_context, "error": str(e)},
            )
            raise RetryableSalesforceError(str(e)) from e

    def create_query_job(self, query: str) -> str:
        """Create a new Bulk 2.0 query job.

        Args:
            query: SOQL query to execute

        Returns:
            ID of the created job

        Raises:
            Bulk2APIError: If job creation fails
        """
        headers = {
            "Content-Type": "application/json",
            **self.authenticator.auth_headers,
        }

        job_data = {
            "operation": "query",
            "query": query,
            "contentType": "CSV",
            "columnDelimiter": "COMMA",
            "lineEnding": "LF",
        }

        try:
            response = self._make_request(
                "POST",
                self.get_url(),
                headers=headers,
                json=job_data,
            )

            # Extract and log job details
            job_id = response.json()["id"]
            self._current_job_id = job_id

            self.logger.info(
                "Created Bulk 2.0 query job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "query": query,
                },
            )

        except Exception as e:
            # Capture and log the full error details
            error_msg = f"Failed to create job: {e!s}"
            self.logger.exception(
                "Failed to create Bulk 2.0 query job",
                extra={
                    "stream": self.name,
                    "error": error_msg,
                    "query": query,
                },
            )
            raise Bulk2APIError(error_msg) from e
        else:
            return job_id

    def wait_for_job(self, job_id: str) -> dict[str, Any]:
        """Wait for a Bulk 2.0 job to complete.

        Args:
            job_id: ID of job to monitor

        Returns:
            Final job status information

        Raises:
            JobTimeoutError: If job exceeds timeout
            JobFailedError: If job fails
        """
        start_time = time.time()

        while True:
            # Retrieve current job status
            status = self.get_job_status(job_id)
            state = status["state"].lower()

            # Log progress
            self.logger.info(
                "Bulk 2.0 job status",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "status": state,
                    "records_processed": status.get("numberRecordsProcessed", 0),
                    "records_failed": status.get("numberRecordsFailed", 0),
                    "total_processing_time": status.get("totalProcessingTime", 0),
                },
            )

            # Check for job completion
            if state == "jobcomplete":
                return status

            # Check for job failure
            if state in ["failed", "aborted"]:
                # Get detailed error information
                job_info = self._get_job_detailed_info(job_id)
                error_message = f"Job failed: {status.get('errorMessage', 'Unknown error')}"

                self.logger.error(
                    "Bulk 2.0 job failed",
                    extra={
                        "stream": self.name,
                        "job_id": job_id,
                        "error": error_message,
                        "job_info": job_info,
                    },
                )
                raise JobFailedError(error_message)

            # Check for timeout
            if time.time() - start_time > self.job_timeout:
                error_msg = f"Job {job_id} exceeded timeout of {self.job_timeout} seconds"

                self.logger.error(
                    "Bulk 2.0 job timed out",
                    extra={
                        "stream": self.name,
                        "job_id": job_id,
                        "timeout": self.job_timeout,
                        "final_status": status,
                    },
                )

                # Attempt to abort the job
                self.abort_job(job_id)

                raise JobTimeoutError(error_msg)

            # Wait before next status check
            time.sleep(POLL_INTERVAL)

    def _get_job_detailed_info(self, job_id: str) -> dict:
        """Get detailed job information including execution metrics.

        Args:
            job_id: ID of job to get info for

        Returns:
            Dictionary containing job statistics and metadata
        """
        response = self._make_request(
            "GET",
            f"{self.get_url(job_id)}/info",
            headers=self.authenticator.auth_headers,
        )
        return response.json()

    def process_job_results(self, job_id: str) -> Iterator[dict]:
        """Process job results.

        Args:
            job_id: ID of completed job

        Yields:
            Individual records from job results
        """
        # TODO: Implement actual result processing
        return iter([])

    def abort_job(self, job_id: str) -> None:
        """Abort a running Bulk 2.0 job.

        Args:
            job_id: ID of job to abort
        """
        try:
            self._make_request(
                "PATCH",
                self.get_url(job_id),
                headers=self.authenticator.auth_headers,
                json={"state": "Aborted"},
            )
            self.logger.info(
                "Aborted Bulk 2.0 job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                },
            )
        except Exception as e:
            self.logger.warning(
                "Failed to abort Bulk 2.0 job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "error": str(e),
                },
            )

    def get_records(self, context: dict | None = None) -> Iterator[dict]:
        """Get records using the Bulk 2.0 API.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Individual records from the Bulk 2.0 API
        """
        query = self.build_base_query(context)

        with self.job_timer:
            try:
                # Create and execute job
                job_id = self.create_query_job(query)
                job_status = self.wait_for_job(job_id)

                # Log job completion
                self.logger.info(
                    "Completed Bulk 2.0 job",
                    extra={
                        "stream": self.name,
                        "job_id": job_id,
                        "records_processed": job_status["numberRecordsProcessed"],
                        "total_time": job_status["totalProcessingTime"],
                    },
                )

                # Process results with record timing
                with self.records_timer:
                    yield from self.process_job_results(job_id)

            except Exception as e:
                self.logger.exception(
                    "Error during Bulk 2.0 sync",
                    extra={
                        "stream": self.name,
                        "error": str(e),
                        "job_id": self._current_job_id,
                        "context": context,
                    },
                )
                raise

            finally:
                # Clean up job if needed
                if self._current_job_id:
                    self.abort_job(self._current_job_id)
                    self._current_job_id = None
