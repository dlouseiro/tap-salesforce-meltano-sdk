"""Base stream class for Salesforce tap streams.

This module provides the foundation for all Salesforce stream types (REST, Bulk, Bulk2).
It handles common concerns like:
- Record type conversion and processing
- Replication key management
- Compound field handling
- Deleted record tracking
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
)

from singer_sdk import typing as th
from singer_sdk.streams import Stream

from tap_salesforce.auth import SalesforceAuthenticator
from tap_salesforce.exceptions import InvalidSalesforceObjectError
from tap_salesforce.schemas.salesforce_types import SalesforceTypeHelper

if TYPE_CHECKING:
    from collections.abc import Iterator


class BaseSalesforceStream(Stream, abc.ABC):
    """Base stream class for all Salesforce streams.

    This abstract base class provides core functionality used by all Salesforce
    API implementations. It handles field mapping, record processing, and other
    common concerns.
    """

    # Default primary key for all Salesforce objects
    primary_keys: ClassVar[list[str]] = ["Id"]

    # Fields that shouldn't be selected or synced
    UNSUPPORTED_FIELDS: ClassVar[dict[str, set[str]]] = {
        # Fields that can't be queried in certain contexts
        "ActivityMetric": {"ComplexValue"},
        "ContentVersion": {"VersionData"},
        "Document": {"Body"},
        "Attachment": {"Body"},
        # Fields causing issues with Bulk API
        "EntityParticle": {"FieldDefinition"},
        "FieldDefinition": {"Metadata"},
    }

    def __init__(
        self,
        tap: BaseSalesforceStream,
        name: str,
        schema: dict | None = None,
        authenticator: SalesforceAuthenticator | None = None,
        api_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Salesforce stream.

        Args:
            tap: The parent tap object
            name: Name of the Salesforce object/stream
            schema: Optional schema dictionary
            authenticator: Optional authenticator instance
            api_type: API type (REST, BULK, or BULK2)
            **kwargs: Additional arguments passed to parent class
        """
        # Initialize parent Stream class
        super().__init__(tap=tap, name=name, schema=schema, **kwargs)

        # Store Salesforce-specific attributes
        self._authenticator = authenticator
        self.api_type = api_type or self.config["api_type"]

        # Cache for expensive operations
        self._field_descriptions: dict[str, Any] | None = None
        self._compound_fields: set[str] | None = None
        self._unsupported_fields: set[str] | None = None

    @property
    def authenticator(self) -> SalesforceAuthenticator:
        """Get the authenticator instance.

        Returns:
            The Salesforce authenticator for this stream

        Note:
            Creates a new authenticator if one wasn't provided at initialization.
        """
        if not self._authenticator:
            self._authenticator = SalesforceAuthenticator(
                stream_name=self.name,
                config=self.config,
            )
        return self._authenticator

    def get_field_descriptions(self) -> dict[str, Any]:
        """Get field descriptions for this Salesforce object.

        Returns:
            Dictionary mapping field names to their descriptions

        Raises:
            InvalidSalesforceObject: If the object doesn't exist or is inaccessible
        """
        if self._field_descriptions is None:
            try:
                self._field_descriptions = self.authenticator.describe_sobject(
                    self.name
                )
            except Exception as exc:
                error_msg = f"Could not get field descriptions for {self.name}: {exc!s}"
                self.logger.exception(error_msg)
                raise InvalidSalesforceObjectError(error_msg) from exc
        return self._field_descriptions

    def get_compound_fields(self) -> set[str]:
        """Get compound fields for this object.

        Returns:
            Set of compound field names
        """
        if self._compound_fields is None:
            self._compound_fields = {
                field_name
                for field_name, field_info in self.get_field_descriptions().items()
                if field_info["type"].lower() in ["address", "location"]
            }
        return self._compound_fields

    def get_unsupported_fields(self) -> set[str]:
        """Get fields that can't be queried for this object.

        Returns:
            Set of unsupported field names
        """
        if self._unsupported_fields is None:
            # Start with globally unsupported fields for this object
            self._unsupported_fields = set(
                self.UNSUPPORTED_FIELDS.get(self.name, set())
            )

            # Add API-specific unsupported fields based on field descriptions
            for field_name, field_info in self.get_field_descriptions().items():
                field_type = field_info["type"].lower()

                # Bulk API can't handle certain field types
                if self.api_type in ["BULK", "BULK2"] and field_type in [
                    "address",
                    "location",
                ]:
                    self._unsupported_fields.add(field_name)

                # No API can handle binary fields
                if field_type in ["base64", "blob"]:
                    self._unsupported_fields.add(field_name)

        return self._unsupported_fields

    def get_queryable_fields(self) -> list[str]:
        """Get list of fields that can be included in queries.

        Returns:
            List of field names to use in queries
        """
        queryable_fields = []

        for field_name, field_info in self.get_field_descriptions().items():
            # Skip unsupported fields
            if field_name in self.get_unsupported_fields():
                continue

            # Handle compound fields
            if field_name in self.get_compound_fields():
                field_type = field_info["type"].lower()
                queryable_fields.extend(
                    self.process_compound_field(field_name, field_type)
                )
            else:
                queryable_fields.append(field_name)

        return queryable_fields

    def process_compound_field(self, field_name: str, field_type: str) -> list[str]:
        """Handle compound fields by breaking them into components.

        Args:
            field_name: Name of the compound field
            field_type: Type of the compound field

        Returns:
            List of component field names
        """
        if field_type == "address":
            return [
                f"{field_name}.street",
                f"{field_name}.city",
                f"{field_name}.state",
                f"{field_name}.postalCode",
                f"{field_name}.country",
                f"{field_name}.latitude",
                f"{field_name}.longitude",
                f"{field_name}.geocodeAccuracy",
            ]
        if field_type == "location":
            return [
                f"{field_name}.latitude",
                f"{field_name}.longitude",
            ]
        return [field_name]

    def format_datetime_value(self, value: datetime) -> str:
        """Format datetime values for Salesforce queries.

        Args:
            value: Datetime value to format

        Returns:
            Formatted datetime string
        """
        # Ensure timezone awareness
        if not value.tzinfo:
            value = value.replace(tzinfo=timezone.utc)

        # Format with millisecond precision
        formatted = value.isoformat(timespec="milliseconds")

        # Standardize UTC representation
        if formatted.endswith("+00:00"):
            formatted = formatted.replace("+00:00", "Z")

        return formatted

    def build_base_query(self, context: dict | None = None) -> str:
        """Build base SOQL query with proper field selection and filtering.

        Args:
            context: Optional stream context/partition info

        Returns:
            Base SOQL query string
        """
        # Get fields to query
        selected_fields = self.get_queryable_fields()
        # ruff: noqa: S608
        query = f"SELECT {','.join(selected_fields)} FROM {self.name}"

        # Add replication key filtering
        if self.replication_key:
            start_date = self.get_starting_timestamp(context)
            if start_date:
                formatted_date = self.format_datetime_value(start_date)
                query += f" WHERE {self.replication_key} >= {formatted_date}"

                # Include deleted records if possible
                if "IsDeleted" in selected_fields:
                    query = query.replace(
                        "WHERE", "WHERE (IsDeleted = true OR IsDeleted = false) AND"
                    )

        # Add ordering for consistent data retrieval
        if self.replication_key:
            query += f" ORDER BY {self.replication_key} ASC"

        return query

    def post_process(self, row: dict, context: dict | None = None) -> dict | None:
        """Process a record after retrieval from Salesforce.

        This method handles:
        1. Type conversion
        2. Field filtering
        3. Compound field processing
        4. Deleted record handling

        Args:
            row: Raw record from Salesforce
            context: Optional context information

        Returns:
            Processed record, or None if record should be skipped
        """
        # Remove Salesforce metadata
        row.pop("attributes", None)

        # Handle deleted records
        if row.get("IsDeleted") and not self.config.get("sync_deleted_records", True):
            return None

        processed: dict[str, Any] = {}
        field_descriptions = self.get_field_descriptions()

        for field_name, value in row.items():
            if value is None:
                processed[field_name] = None
                continue

            # Get field type information
            field_parts = field_name.split(".")
            base_field = field_parts[0]
            field_info = field_descriptions.get(base_field, {})
            field_type = field_info.get("type", "string").lower()

            # Convert types appropriately using shared type helper
            schema_type = SalesforceTypeHelper.get_json_schema_type(
                field_type, field_info
            )

            if isinstance(schema_type, th.DateTimeType) and value:
                try:
                    processed[field_name] = datetime.fromisoformat(
                        value.rstrip("Z")
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    self.logger.warning(
                        "Could not parse datetime value '%s' for field '%s'",
                        value,
                        field_name,
                    )
                    processed[field_name] = value
            else:
                processed[field_name] = value

        return processed

    @abc.abstractmethod
    def get_records(self, context: dict | None) -> Iterator[dict]:
        """Get records from Salesforce using the appropriate API.

        This abstract method must be implemented by specific API classes
        to handle their unique protocols and requirements.

        Args:
            context: Optional context dictionary for stream partitioning

        Raises:
            NotImplementedError: Must be implemented by API-specific classes
        """
        raise NotImplementedError
