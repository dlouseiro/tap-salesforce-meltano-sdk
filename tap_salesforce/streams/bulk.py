"""Salesforce Bulk API stream implementation.

This module handles data extraction using Salesforce's Bulk API with comprehensive
error handling, job monitoring, and logging.
"""

from __future__ import annotations

import csv
import io
import time
from typing import (
    TYPE_CHECKING,
    Any,
)

import backoff
import requests
from singer_sdk import metrics

from tap_salesforce.exceptions import (
    BulkAPIError,
    BulkJobError,
    JobFailedError,
    JobTimeoutError,
    RetryableSalesforceError,
    raise_for_error,
)
from tap_salesforce.streams.base import BaseSalesforceStream
from tap_salesforce.streams.chunking import PKChunkingMixin

if TYPE_CHECKING:
    from collections.abc import Iterator

# Bulk API limits and settings
MAX_BULK_RECORDS = 10_000_000  # 10M records per job
MAX_BATCH_SIZE = 10_000  # Records per batch
BULK_API_POLL_INTERVAL = 5  # Seconds between status checks
MAX_POLL_ATTEMPTS = 50  # Max times to check job status
JOB_TIMEOUT = 20 * 60  # 20 minutes in seconds


class SalesforceBulkStream(BaseSalesforceStream, PKChunkingMixin):
    """Stream class for Salesforce Bulk API.

    Handles large data volumes by:
    1. Creating an async bulk job
    2. Monitoring job status
    3. Processing results as they complete
    4. Managing state throughout
    """

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the bulk stream with batch settings."""
        super().__init__(*args, **kwargs)
        # Configure from tap settings
        self.batch_size = self.config.get("batch_size", MAX_BATCH_SIZE)
        self.job_timeout = self.config.get("job_timeout", JOB_TIMEOUT)
        self._current_job_id: str | None = None
        self._batches_in_progress: dict[str, Any] = {}

        # Set up job monitoring
        self.job_timer = metrics.Timer(metrics.Metric.SYNC_DURATION)
        self.batch_timer = metrics.Timer(metrics.Metric.BATCH_PROCESSING_TIME)

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

    @backoff.on_exception(
        backoff.expo,
        (RetryableSalesforceError, requests.exceptions.RequestException),
        max_tries=5,
        giveup=lambda e: not isinstance(e, RetryableSalesforceError),
    )
    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an HTTP request with error handling and backoff.

        Args:
            method: HTTP method to use
            url: URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            BulkAPIError: For Bulk API-specific errors
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
                "Making Bulk API request",
                extra=log_context,
            )

            response = requests.request(
                method, url, timeout=self.config.get("request_timeout", 300), **kwargs
            )

            # Handle error responses
            if not response.ok:
                error_code, error_message = self._extract_error_details(response)

                if error_code in ["EXCEEDED_MAX_JOBS_LIMIT", "REQUEST_LIMIT_EXCEEDED"]:
                    self.logger.error(
                        "Bulk API limit exceeded",
                        extra={**log_context, "error": error_message},
                    )
                    raise RetryableSalesforceError(error_message)

                # Let our error handler determine appropriate exception
                raise_for_error({"errorCode": error_code, "message": error_message})

        except requests.exceptions.RequestException as e:
            self.logger.exception(
                "Bulk API request failed",
                extra={**log_context, "error": str(e)},
            )
            raise RetryableSalesforceError(str(e)) from e
        else:
            return response

    def create_bulk_job(self, query: str) -> str:
        """Create a new bulk API job for the query.

        Args:
            query: SOQL query to execute

        Returns:
            ID of the created job

        Raises:
            BulkAPIError: If job creation fails
        """
        headers = {
            "Content-Type": "application/json",
            **self.authenticator.auth_headers,
        }

        job_data = {
            "operation": "query",
            "object": self.name,
            "contentType": "CSV",
            "query": query,
        }

        # Add PK chunking headers if enabled
        pk_headers = self.setup_pk_chunking(self.config)
        headers.update(pk_headers)

        try:
            response = self._make_request(
                "POST", self.get_job_url(), headers=headers, json=job_data
            )

            job_id = response.json()["id"]
            self._current_job_id = job_id

            self.logger.info(
                "Created Bulk API job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "object": self.name,
                },
            )

        except Exception as e:
            # Capture and log the full error details
            error_msg = f"Failed to create job: {e!s}"
            self.logger.exception(
                "Failed to create Bulk API job",
                extra={
                    "stream": self.name,
                    "error": error_msg,
                    "query": query,
                },
            )
            raise BulkJobError(error_msg) from e
        else:
            return job_id

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get status of a Bulk 2.0 job.

        Args:
            job_id: ID of job to check

        Returns:
            Dictionary containing job status and statistics
        """
        response = self._make_request(
            "GET",
            self.get_url(job_id),
            headers=self.authenticator.auth_headers,
        )
        return response.json()

    def wait_for_job(self, job_id: str) -> bool:
        """Wait for a bulk job to complete.

        Args:
            job_id: ID of job to monitor

        Returns:
            True if job completed successfully

        Raises:
            JobTimeoutError: If job takes too long
            JobFailedError: If job fails
        """
        start_time = time.time()
        attempts = 0

        while attempts < MAX_POLL_ATTEMPTS:
            job_status = self.get_job_status(job_id)
            status = job_status["state"].lower()

            # Log progress
            self.logger.info(
                "Bulk job status",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "status": status,
                    "processed": job_status.get("numberRecordsProcessed", 0),
                    "failed": job_status.get("numberRecordsFailed", 0),
                    "total_time": job_status.get("totalProcessingTime", 0),
                },
            )

            if status == "completed":
                return True
            if status in ["failed", "aborted"]:
                error_message = (
                    f"Job failed: {job_status.get('errorMessage', 'Unknown error')}"
                )
                self.logger.error(
                    "Bulk job failed",
                    extra={
                        "stream": self.name,
                        "job_id": job_id,
                        "error": error_message,
                        "status": job_status,
                    },
                )
                raise JobFailedError(error_message)

            if time.time() - start_time > self.job_timeout:
                error_msg = (
                    f"Job {job_id} exceeded timeout of {self.job_timeout} seconds"
                )
                self.logger.error(
                    "Bulk job timed out",
                    extra={
                        "stream": self.name,
                        "job_id": job_id,
                        "timeout": self.job_timeout,
                        "status": job_status,
                    },
                )
                raise JobTimeoutError(error_msg)

            attempts += 1
            time.sleep(BULK_API_POLL_INTERVAL)

        self.logger.error(
            "Max polling attempts reached",
            extra={
                "stream": self.name,
                "job_id": job_id,
                "max_attempts": MAX_POLL_ATTEMPTS,
            },
        )
        return False

    def process_job_results(self, job_id: str) -> Iterator[dict]:
        """Process results from a completed bulk job.

        Args:
            job_id: ID of completed job

        Yields:
            Individual records from the job results

        Raises:
            BulkAPIError: If results cannot be retrieved
        """
        try:
            # Get result ID first
            response = self._make_request(
                "GET",
                f"{self.get_job_url(job_id)}/result",
                headers=self.authenticator.auth_headers,
            )

            result_id = response.json()[0]  # First result file

            # Download and process results
            response = self._make_request(
                "GET",
                f"{self.get_job_url(job_id)}/result/{result_id}",
                headers=self.authenticator.auth_headers,
            )

            # Process CSV data
            csv_file = io.StringIO(response.text)
            reader = csv.DictReader(csv_file)

            records_processed = 0
            for row in reader:
                records_processed += 1
                # Convert types and clean up record
                processed_record = self.post_process(row)
                if processed_record:
                    if self.replication_key:
                        # Update state for every record in bulk results
                        self._increment_stream_state(processed_record)
                    yield processed_record

            self.logger.info(
                "Processed Bulk API results",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "records_processed": records_processed,
                },
            )

        except Exception as e:
            error_msg = f"Failed to process job results: {e!s}"
            self.logger.exception(
                "Failed to process job results",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "error": error_msg,
                },
            )
            raise BulkAPIError(error_msg) from e

    def get_records(self, context: dict | None = None) -> Iterator[dict]:
        """Get records using the bulk API.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Individual records from the bulk API
        """
        query = self.build_base_query(context)

        with self.job_timer:
            try:
                # Create and monitor bulk job
                job_id = self.create_bulk_job(query)
                job_succeeded = self.wait_for_job(job_id)

                if not job_succeeded:
                    error_msg = f"Bulk job {job_id} did not complete successfully"
                    raise JobFailedError(error_msg)

                # Process results with batch timer
                with self.batch_timer:
                    yield from self.process_job_results(job_id)

            except Exception as e:
                self.logger.exception(
                    "Error during bulk sync",
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

    def abort_job(self, job_id: str) -> None:
        """Abort a bulk job if it's still running.

        Args:
            job_id: ID of job to abort
        """
        try:
            self._make_request(
                "POST",
                f"{self.get_job_url(job_id)}/abort",
                headers=self.authenticator.auth_headers,
            )
            self.logger.info(
                "Aborted Bulk API job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                },
            )
        except Exception as e:
            self.logger.warning(
                "Failed to abort Bulk API job",
                extra={
                    "stream": self.name,
                    "job_id": job_id,
                    "error": str(e),
                },
            )
