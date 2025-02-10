"""PK chunking implementation for Salesforce streams.

This module provides PK (Primary Key) chunking functionality used across different
API types. PK chunking helps handle large datasets by breaking queries into
manageable chunks based on record IDs.
"""

from __future__ import annotations

import abc
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class PKChunkingMixin(abc.ABC):
    """Mixin providing PK chunking capabilities for any stream type.

    PK chunking is Salesforce's recommended approach for handling large datasets.
    This mixin provides the core functionality needed to:
    1. Configure chunking parameters
    2. Handle parent-child relationships
    3. Manage chunk processing
    """

    @classmethod
    def setup_pk_chunking(
        cls,
        config: dict[str, Any],
        chunk_size: int | None = None,
    ) -> dict[str, str]:
        """Configure PK chunking headers and settings.

        Args:
            config: Configuration dictionary
            chunk_size: Optional override for chunk size. If not provided,
                       uses the config setting or default.

        Returns:
            Dictionary of headers needed for PK chunking.
        """
        chunk_size = chunk_size or config.get("pk_chunk_size", 100000)
        headers = {"Sforce-Enable-PKChunking": f"chunkSize={chunk_size}"}

        # Handle parent object chunking for special objects
        if cls._needs_parent_chunking():
            parent_object = cls._get_parent_object()
            headers["Sforce-Enable-PKChunking"] += f";parent={parent_object}"

        return headers

    @classmethod
    def _needs_parent_chunking(cls) -> bool:
        """Check if this object needs parent-based chunking.

        Returns:
            True if this object should use parent-based chunking.
        """
        return False

    @classmethod
    def _get_parent_object(cls) -> str:
        """Get the parent object name for chunking.

        Returns:
            Name of the parent object.
        """
        return ""

    def build_chunk_queries(self, base_query: str, object_name: str) -> Iterator[str]:
        """Build chunked queries based on ID ranges.

        This method splits a query into chunks based on ID ranges. It's used
        when PK chunking isn't supported directly by the API endpoint.

        Args:
            base_query: The base SOQL query to chunk
            object_name: Name of the Salesforce object

        Yields:
            Individual chunked queries
        """
        # Query for ID ranges first
        # ruff: noqa: S608
        id_query = f"SELECT MIN(Id), MAX(Id) FROM {object_name}"
        ranges = self._get_id_ranges(id_query)

        for start_id, end_id in ranges:
            # Add ID range to WHERE clause
            if " WHERE " in base_query:
                chunked_query = base_query.replace(
                    " WHERE ", f" WHERE Id >= '{start_id}' AND Id < '{end_id}' AND "
                )
            else:
                chunked_query = (
                    f"{base_query} WHERE Id >= '{start_id}' AND Id < '{end_id}'"
                )

            yield chunked_query

    @abc.abstractmethod
    def _get_id_ranges(self, query: str) -> list[tuple[str, str]]:
        """Get ID ranges for chunking.

        This abstract method must be implemented by API-specific classes
        to fetch ID ranges in a way appropriate for that API type.

        Args:
            query: Query to execute for getting ID ranges

        Returns:
            List of (start_id, end_id) tuples
        """
        raise NotImplementedError
