"""Bulk 2.0 API stream class for Salesforce."""

from typing import Any, Dict, Iterable, Optional

from singer_sdk.helpers._util import utc_now

from tap_salesforce.streams.base import SalesforceStream


class Bulk2Stream(SalesforceStream):
    """Stream class for Bulk 2.0 API based streams."""

    @property
    def timeout(self) -> int:
        """Get timeout for Bulk 2.0 API jobs.

        Returns:
            Maximum seconds to wait for job completion
        """
        return self.config.get("bulk2_timeout", 1800)  # 30 minutes default

    @property
    def poll_interval(self) -> int:
        """Get polling interval for Bulk 2.0 API jobs.

        Returns:
            Number of seconds between status checks
        """
        return self.config.get("bulk2_poll_interval", 5)

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        """Get records using Bulk 2.0 API.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Record dictionaries from Bulk 2.0 API
        """
        query = self._build_query(context)

        # Track job start time for logging
        start_time = utc_now()
        self.logger.info(f"Starting Bulk 2.0 API job for {self.name}")

        try:
            records_yielded = 0
            for record in self.client.query(
                query, include_deleted=self.config.get("include_deleted", False)
            ):
                records_yielded += 1
                if records_yielded % 10000 == 0:
                    self.logger.info(f"Retrieved {records_yielded} records from {self.name}")
                yield record

            end_time = utc_now()
            duration = (end_time - start_time).total_seconds()
            self.logger.info(
                f"Completed Bulk 2.0 API job for {self.name} in {duration:.2f} "
                f"seconds, {records_yielded} records retrieved"
            )

        except Exception as e:
            self.logger.error(f"Bulk 2.0 API job failed for {self.name}: {str(e)}")

            # Check for failed records
            if hasattr(self.client, "get_failed_results"):
                failed_records = self.client.get_failed_results(self.client.job_id)
                if failed_records:
                    self.logger.error(f"Failed records for {self.name}: {len(failed_records)}")
                    for record in failed_records[:5]:  # Log first 5 failures
                        self.logger.error(f"Failed record: {record}")

            raise

    def _build_query(self, context: Optional[dict] = None) -> str:
        """Build SOQL query with Bulk 2.0-specific optimizations.

        Args:
            context: Stream partition or context dictionary

        Returns:
            SOQL query string
        """
        query = super()._build_query(context)

        # Add locator hint for better performance in Bulk 2.0
        if self.config.get("bulk2_use_locator", True) and not query.upper().startswith(
            "SELECT /*+"
        ):
            query = f"SELECT /*+ ENABLE_LOCATOR */ {query[6:]}"

        return query
