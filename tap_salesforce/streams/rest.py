"""REST stream class for Salesforce."""

from typing import Any, Dict, Iterable, Optional

from tap_salesforce.streams.base import SalesforceStream


class RestStream(SalesforceStream):
    """Stream class for REST API based streams."""

    @property
    def page_size(self) -> int:
        """Get the page size for REST API queries.

        Returns:
            Number of records per page
        """
        return self.config.get("page_size", 2000)

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        """Get records using REST API.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Record dictionaries from REST API
        """
        query = self._build_query(context)
        yield from self.client.query(query)

    def _build_query(self, context: Optional[dict] = None) -> str:
        """Build SOQL query with REST-specific options.

        Args:
            context: Stream partition or context dictionary

        Returns:
            SOQL query string
        """
        query = super()._build_query(context)
        return f"{query} LIMIT {self.page_size}"
