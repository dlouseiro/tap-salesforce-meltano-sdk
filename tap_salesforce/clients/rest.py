"""REST client handling."""

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from singer_sdk.helpers._util import utc_now

from tap_salesforce.clients.base import SalesforceClient


class RestClient(SalesforceClient):
    """Salesforce REST API client implementation."""

    def query(self, query: str, include_deleted: bool = False) -> Iterable[dict]:
        """Execute SOQL query using REST API.

        Args:
            query: SOQL query string
            include_deleted: Whether to include deleted records

        Returns:
            Iterator of records

        Yields:
            Record dictionaries
        """
        endpoint = "queryAll" if include_deleted else "query"
        url = f"{self.url_base}/{endpoint}"

        params = {"q": query}
        next_url = url

        while next_url:
            # If we have a full URL from nextRecordsUrl, use it directly
            if next_url.startswith("http"):
                response = self._make_request("GET", next_url)
            else:
                response = self._make_request("GET", url, params=params)

            response_data = response.json()

            # Yield records
            for record in response_data.get("records", []):
                # Remove Salesforce metadata
                record.pop("attributes", None)
                yield record

            # Get next page URL if it exists
            next_url = response_data.get("nextRecordsUrl")
            # Clear params as they're included in the nextRecordsUrl
            params = None

    def get_deleted(self, object_name: str, start_date: str, end_date: str) -> Iterable[dict]:
        """Get deleted records for an object.

        Args:
            object_name: API name of the Salesforce object
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            Iterator of deleted record dictionaries

        Yields:
            Deleted record information
        """
        url = f"{self.url_base}/sobjects/{object_name}/deleted"
        params = {
            "start": start_date,
            "end": end_date,
        }

        response = self._make_request("GET", url, params=params)
        data = response.json()

        for record in data.get("deletedRecords", []):
            yield {
                "id": record["id"],
                "deleted_date": record["deletedDate"],
            }

    def get_updated(self, object_name: str, start_date: str, end_date: str) -> Iterable[str]:
        """Get IDs of updated records for an object.

        Args:
            object_name: API name of the Salesforce object
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            Iterator of record IDs

        Yields:
            Record IDs that were updated in the date range
        """
        url = f"{self.url_base}/sobjects/{object_name}/updated"
        params = {
            "start": start_date,
            "end": end_date,
        }

        response = self._make_request("GET", url, params=params)
        data = response.json()

        for record_id in data.get("ids", []):
            yield record_id

    def get_all_fields(self, object_name: str) -> List[Dict[str, Any]]:
        """Get all field metadata for an object.

        Args:
            object_name: API name of the Salesforce object

        Returns:
            List of field metadata dictionaries
        """
        object_desc = self.describe_object(object_name)
        return object_desc.get("fields", [])

    def create(self, object_name: str, data: dict) -> dict:
        """Create a new record.

        Args:
            object_name: API name of the Salesforce object
            data: Record data

        Returns:
            Created record response
        """
        url = f"{self.url_base}/sobjects/{object_name}"
        response = self._make_request("POST", url, json=data)
        return response.json()

    def update(self, object_name: str, record_id: str, data: dict) -> None:
        """Update an existing record.

        Args:
            object_name: API name of the Salesforce object
            record_id: Record ID to update
            data: Updated record data
        """
        url = f"{self.url_base}/sobjects/{object_name}/{record_id}"
        self._make_request("PATCH", url, json=data)

    def delete(self, object_name: str, record_id: str) -> None:
        """Delete a record.

        Args:
            object_name: API name of the Salesforce object
            record_id: Record ID to delete
        """
        url = f"{self.url_base}/sobjects/{object_name}/{record_id}"
        self._make_request("DELETE", url)

    def get_record_by_id(
        self, object_name: str, record_id: str, fields: Optional[List[str]] = None
    ) -> dict:
        """Get a record by ID.

        Args:
            object_name: API name of the Salesforce object
            record_id: Record ID to retrieve
            fields: List of fields to retrieve (optional)

        Returns:
            Record data
        """
        url = f"{self.url_base}/sobjects/{object_name}/{record_id}"
        params = {}

        if fields:
            params["fields"] = ",".join(fields)

        response = self._make_request("GET", url, params=params)
        record = response.json()
        record.pop("attributes", None)
        return record
