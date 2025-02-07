"""Bulk API client handling."""

import csv
import io
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from singer_sdk.helpers._util import utc_now

from tap_salesforce.clients.base import SalesforceClient


class BulkClient(SalesforceClient):
    """Salesforce Bulk API client implementation."""

    def __init__(
        self,
        authenticator: "APIAuthenticatorBase",
        config: dict,
        api_version: str = "v57.0",
        batch_size: int = 10000,
        poll_interval: int = 10,
    ) -> None:
        """Initialize client.

        Args:
            authenticator: API authenticator instance
            config: Tap configuration
            api_version: Salesforce API version to use
            batch_size: Number of records per batch
            poll_interval: Seconds to wait between job status checks
        """
        super().__init__(authenticator, config, api_version)
        self.batch_size = batch_size
        self.poll_interval = poll_interval

    @property
    def url_base(self) -> str:
        """Get base URL for Bulk API."""
        return f"{self.authenticator.instance_url}/services/async/{self.api_version}"

    def query(self, query: str, include_deleted: bool = False) -> Iterable[dict]:
        """Execute SOQL query using Bulk API.

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
            # Always close the job
            self._close_job(job_id)

    def _create_query_job(self, query: str, include_deleted: bool = False) -> str:
        """Create a new Bulk API query job.

        Args:
            query: SOQL query string
            include_deleted: Whether to include deleted records

        Returns:
            Job ID
        """
        url = f"{self.url_base}/job"

        data = {
            "operation": "queryAll" if include_deleted else "query",
            "object": self._get_object_from_query(query),
            "contentType": "CSV",
            "query": query,
        }

        response = self._make_request("POST", url, json=data)
        return response.json()["id"]

    def _wait_for_job(self, job_id: str) -> None:
        """Wait for a job to complete.

        Args:
            job_id: Bulk API job ID

        Raises:
            Exception: If job fails or times out
        """
        max_retries = 50  # Maximum number of status checks
        retries = 0

        while retries < max_retries:
            status = self._get_job_status(job_id)

            if status["state"] in ["JobComplete", "Aborted", "Failed"]:
                if status["state"] != "JobComplete":
                    raise Exception(
                        f"Job {job_id} ended with state: {status['state']}, "
                        f"error: {status.get('errorMessage', 'Unknown error')}"
                    )
                return

            time.sleep(self.poll_interval)
            retries += 1

        raise Exception(f"Job {job_id} timed out after {max_retries} checks")

    def _get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get status of a job.

        Args:
            job_id: Bulk API job ID

        Returns:
            Job status information
        """
        url = f"{self.url_base}/job/{job_id}"
        response = self._make_request("GET", url)
        return response.json()

    def _get_job_results(self, job_id: str) -> Iterable[dict]:
        """Get results from a completed job.

        Args:
            job_id: Bulk API job ID

        Yields:
            Record dictionaries
        """
        url = f"{self.url_base}/job/{job_id}/results"
        response = self._make_request("GET", url)

        # Parse CSV response
        csv_file = io.StringIO(response.text)
        reader = csv.DictReader(csv_file)

        for row in reader:
            # Convert empty strings to None
            record = {k: (None if v == "" else v) for k, v in row.items()}
            yield record

    def _close_job(self, job_id: str) -> None:
        """Close a job.

        Args:
            job_id: Bulk API job ID
        """
        url = f"{self.url_base}/job/{job_id}"
        data = {"state": "Closed"}
        self._make_request("PATCH", url, json=data)

    def _get_object_from_query(self, query: str) -> str:
        """Extract object name from SOQL query.

        Args:
            query: SOQL query string

        Returns:
            Object API name

        Raises:
            ValueError: If object name cannot be extracted
        """
        # Simple parsing - assumes standard SOQL format
        try:
            from_clause = query.split("FROM")[1].strip().split()[0]
            return from_clause
        except IndexError:
            raise ValueError(f"Could not extract object name from query: {query}")

    def create_bulk_job(self, object_name: str, operation: str, data: List[Dict[str, Any]]) -> str:
        """Create a bulk job for insert/update/delete operations.

        Args:
            object_name: API name of the Salesforce object
            operation: Operation type (insert, update, delete, etc.)
            data: List of records to process

        Returns:
            Job ID
        """
        url = f"{self.url_base}/job"

        job_data = {
            "object": object_name,
            "operation": operation,
            "contentType": "CSV",
        }

        response = self._make_request("POST", url, json=job_data)
        job_id = response.json()["id"]

        # Upload data
        self._upload_job_data(job_id, data)

        # Close job to start processing
        self._close_job(job_id)

        return job_id

    def _upload_job_data(self, job_id: str, data: List[Dict[str, Any]]) -> None:
        """Upload data for a bulk job.

        Args:
            job_id: Bulk API job ID
            data: List of records to process
        """
        url = f"{self.url_base}/job/{job_id}/batches"

        # Convert data to CSV
        output = io.StringIO()
        if data:
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        headers = {
            **self.authenticator.auth_headers,
            "Content-Type": "text/csv",
        }

        self._make_request("PUT", url, data=output.getvalue(), headers=headers)
