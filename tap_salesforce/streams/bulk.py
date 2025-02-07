"""Bulk API stream class for Salesforce."""

import time
from typing import Any, Dict, Iterable, Optional

from singer_sdk.helpers._util import utc_now

from tap_salesforce.streams.base import SalesforceStream


class BulkStream(SalesforceStream):
    """Stream class for Bulk API based streams."""

    @property
    def batch_size(self) -> int:
        """Get the batch size for Bulk API queries.

        Returns:
            Number of records per batch
        """
        return self.config.get("batch_size", 10000)

    @property
    def poll_interval(self) -> int:
        """Get polling interval for Bulk API jobs.

        Returns:
            Number of seconds between status checks
        """
        return self.config.get("bulk_poll_interval", 10)

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        """Get records using Bulk API.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Record dictionaries from Bulk API
        """
        query = self._build_query(context)

        # Track job start time for logging
        start_time = utc_now()
        self.logger.info(f"Starting Bulk API job for {self.name}")

        try:
            yield from self.client.query(
                query, include_deleted=self.config.get("include_deleted", False)
            )

            end_time = utc_now()
            duration = (end_time - start_time).total_seconds()
            self.logger.info(f"Completed Bulk API job for {self.name} in {duration:.2f} seconds")

        except Exception as e:
            self.logger.error(f"Bulk API job failed for {self.name}: {str(e)}")
            raise

    def _build_query(self, context: Optional[dict] = None) -> str:
        """Build SOQL query with Bulk-specific optimizations.

        Args:
            context: Stream partition or context dictionary

        Returns:
            SOQL query string
        """
        query = super()._build_query(context)

        # Add optimization hints for Bulk API
        if not query.upper().startswith("SELECT"):
            return query

        # Add hints for better performance
        hints = []

        if self.config.get("bulk_api_hints", True):
            hints.extend(
                [
                    "DISABLE_QUERY_OPTIMIZATION",
                    "ENABLE_PARALLEL_PROCESSING",
                ]
            )

        if hints:
            query = f"/*+ {' '.join(hints)} */ {query}"

        return query
