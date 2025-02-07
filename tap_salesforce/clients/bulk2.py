"""Bulk 2.0 API client handling."""

import csv
import io
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from singer_sdk.helpers._util import utc_now

from tap_salesforce.clients.base import SalesforceClient


class Bulk2Client(SalesforceClient):
    """Salesforce Bulk 2.0 API client implementation."""

    def __init__(
        self,
        authenticator: "APIAuthenticatorBase",
        config: dict,
        api_version: str = "v57.0",
        poll_interval: int = 5,
        timeout: int = 1800,  # 30 minutes
    ) -> None:
        """Initialize client.

        Args:
            authenticator: API authenticator instance
            config: Tap configuration
            api_version: Salesforce API version to use
            poll_interval: Seconds to wait between job status checks
            timeout: Maximum seconds to wait for job completion
        """
        super().__init__(authenticator, config, api_version)
        self.poll_interval = poll_interval
        self.timeout = timeout

    @property
    def url_base(self) -> str:
        """Get base URL for Bulk 2.0 API."""
        return f"{self.authenticator.instance_url}/services/data/v{self.api_version}/jobs/query"

    def query(self, query: str, include_deleted: bool = False) -> Iterable[dict]:
        """Execute SOQL query using Bulk 2.0 API.

        Args:
            query: SOQL query string
            include_deleted: Whether to include deleted records

        Returns:
            Iterator of records

        Yields:
            Record dictionaries
        """
        # Create a new job
        job_id = self._create_query_job(query, include_deleted)

        try:
            # Wait for job to complete
            self._wait_for_job(job_id)

            # Get results
            yield from self._get_job_results(job_id)
        finally:
            # Always abort the job if it's still in progress
            self._abort_job_if_running(job_id)

    def _create_query_job(self, query: str, include_deleted: bool = False) -> str:
        """Create a new Bulk 2.0 API query job.

        Args:
            query: SOQL query string
            include_deleted: Whether to include deleted records

        Returns:
            Job ID
        """
        data = {
            "operation": "queryAll" if include_deleted else "query",
            "query": query,
            "contentType": "CSV",
            "columnDelimiter": "COMMA",
            "lineEnding": "LF",
        }

        response = self._make_request("POST", self.url_base, json=data)
        return response.json()["id"]

    def _wait_for_job(self, job_id: str) -> None:
        """Wait for a job to complete.

        Args:
            job_id: Bulk 2.0 API job ID

        Raises:
            Exception: If job fails or times out
        """
        start_time = time.time()

        while (time.time() - start_time) < self.timeout:
            status = self._get_job_status(job_id)

            if status["state"] in ["JobComplete", "Aborted", "Failed"]:
                if status["state"] != "JobComplete":
                    raise Exception(
                        f"Job {job_id} ended with state: {status['state']}, "
                        f"error: {status.get('errorMessage', 'Unknown error')}"
                    )
                return

            time.sleep(self.poll_interval)

        raise Exception(f"Job {job_id} timed out after {self.timeout} seconds")

    def _get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a job.

        Args:
            job_id: Bulk 2.0 API job ID

        Returns:
            Job status information
        """
        url = f"{self.url_base}/{job_id}"
        response = self._make_request("GET", url)
        return response.json()

    def _get_job_results(self, job_id: str) -> Iterable[dict]:
        """Get results from a completed job.

        Args:
            job_id: Bulk 2.0 API job ID

        Yields:
            Record dictionaries
        """
        url = f"{self.url_base}/{job_id}/results"
        response = self._make_request("GET", url)

        # Parse CSV response
        csv_file = io.StringIO(response.text)
        reader = csv.DictReader(csv_file)

        for row in reader:
            # Convert empty strings to None
            record = {k: (None if v == "" else v) for k, v in row.items()}
            yield record

    def _abort_job_if_running(self, job_id: str) -> None:
        """Abort a job if it's still in progress.

        Args:
            job_id: Bulk 2.0 API job ID
        """
        status = self._get_job_status(job_id)
        if status["state"] not in ["JobComplete", "Aborted", "Failed"]:
            self._abort_job(job_id)

    def _abort_job(self, job_id: str) -> None:
        """Abort a job.

        Args:
            job_id: Bulk 2.0 API job ID
        """
        url = f"{self.url_base}/{job_id}"
        data = {"state": "Aborted"}
        self._make_request("PATCH", url, json=data)

    def get_job_info(self, job_id: str) -> Dict[str, Any]:
        """Get detailed job information.

        Args:
            job_id: Bulk 2.0 API job ID

        Returns:
            Job information including status, records processed, etc.
        """
        url = f"{self.url_base}/{job_id}"
        response = self._make_request("GET", url)
        return response.json()

    def get_failed_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Get failed records from a job.

        Args:
            job_id: Bulk 2.0 API job ID

        Returns:
            List of failed records with error information
        """
        url = f"{self.url_base}/{job_id}/failedResults"
        try:
            response = self._make_request("GET", url)

            # Parse CSV response
            csv_file = io.StringIO(response.text)
            reader = csv.DictReader(csv_file)
            return list(reader)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No failed results
                return []
            raise

    def get_unprocessed_records(self, job_id: str) -> List[Dict[str, Any]]:
        """Get unprocessed records from a job.

        Args:
            job_id: Bulk 2.0 API job ID

        Returns:
            List of unprocessed records
        """
        url = f"{self.url_base}/{job_id}/unprocessedrecords"
        try:
            response = self._make_request("GET", url)

            # Parse CSV response
            csv_file = io.StringIO(response.text)
            reader = csv.DictReader(csv_file)
            return list(reader)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # No unprocessed records
                return []
            raise
