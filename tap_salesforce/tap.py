"""Salesforce tap class."""

from typing import List, Optional

from singer_sdk import Stream, Tap
from singer_sdk.typing import (
    ArrayType,
    BooleanType,
    DateTimeType,
    NumberType,
    ObjectType,
    PropertiesList,
    Property,
    StringType,
)
from tap_salesforce_sdk.client import SalesforceStream


class TapSalesforce(Tap):
    """Salesforce tap class."""

    name = "tap-salesforce-sdk"

    config_jsonschema = {
        "type": "object",
        "properties": {
            "auth_type": {
                "type": "string",
                "enum": ["oauth2", "password"],
                "default": "oauth2",
                "description": "Authentication method to use",
            },
            "client_id": {
                "type": "string",
                "description": "The OAuth client ID",
            },
            "client_secret": {
                "type": "string",
                "description": "The OAuth client secret",
            },
            "refresh_token": {
                "type": "string",
                "description": "The OAuth refresh token",
            },
            "username": {
                "type": "string",
                "description": "The username for password authentication",
            },
            "password": {
                "type": "string",
                "description": "The password for password authentication",
            },
            "security_token": {
                "type": "string",
                "description": "The security token for password authentication",
            },
            "start_date": {
                "type": "string",
                "format": "date-time",
                "description": "The earliest record date to sync",
            },
            "api_type": {
                "type": "string",
                "enum": ["REST", "BULK", "BULK2"],
                "default": "REST",
                "description": "Salesforce API type to use",
            },
            "is_sandbox": {
                "type": "boolean",
                "default": False,
                "description": "Whether to use Salesforce sandbox environment",
            },
            "quota_percent_total": {
                "type": "number",
                "default": 80.0,
                "description": "Maximum percentage of total quota to use",
            },
            "quota_percent_per_run": {
                "type": "number",
                "default": 25.0,
                "description": "Maximum percentage of quota to use per run",
            },
            "select_fields_by_default": {
                "type": "boolean",
                "default": True,
                "description": "Whether to select all fields by default during discovery",
            },
        },
        "required": [
            "api_type",
            "select_fields_by_default",
        ],
        "additionalProperties": False,
    }

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams.

        Returns:
            A list of discovered streams.
        """
        streams = []

        # Get list of all objects from Salesforce
        sobjects = self.client.describe()["sobjects"]

        for sobject in sobjects:
            if self._is_eligible_for_sync(sobject):
                streams.append(self._get_stream(sobject))

        return streams

    def _is_eligible_for_sync(self, sobject: dict) -> bool:
        """Determine if an SObject is eligible for syncing.

        Args:
            sobject: Salesforce object metadata

        Returns:
            bool: Whether the object is eligible for syncing
        """
        # Skip objects that aren't queryable
        if not sobject.get("queryable"):
            return False

        # Skip objects that aren't retrievable
        if not sobject.get("retrieveable"):
            return False

        return True

    def _get_stream(self, sobject: dict) -> Stream:
        """Create a stream instance for the given SObject.

        Args:
            sobject: Salesforce object metadata

        Returns:
            A stream instance
        """
        stream_name = sobject["name"]

        return SalesforceStream(
            tap=self,
            name=stream_name,
            schema=self._get_schema(sobject),
            replication_key=self._get_replication_key(sobject),
        )

    def _get_schema(self, sobject: dict) -> dict:
        """Get the schema for a Salesforce object.

        Args:
            sobject: Salesforce object metadata

        Returns:
            The schema for the object
        """
        properties = []

        # Get detailed object description
        object_desc = self.client.describe_object(sobject["name"])

        for field in object_desc["fields"]:
            properties.append(self._get_field_schema(field))

        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {prop.name: prop.to_dict() for prop in properties},
        }

    def _get_field_schema(self, field: dict) -> Property:
        """Convert a Salesforce field to a Singer SDK Property.

        Args:
            field: Salesforce field metadata

        Returns:
            A Property instance
        """
        field_name = field["name"]
        salesforce_type = field["type"]

        # Map Salesforce types to Singer SDK types
        if salesforce_type in ["string", "id", "reference", "picklist"]:
            return StringType(field_name)
        elif salesforce_type in ["datetime", "date"]:
            return DateTimeType(field_name)
        elif salesforce_type in ["boolean"]:
            return BooleanType(field_name)
        elif salesforce_type in ["double", "currency", "percent"]:
            return NumberType(field_name)
        elif salesforce_type in ["address", "location"]:
            return ObjectType(
                field_name,
                ObjectType.Property("street", StringType),
                ObjectType.Property("city", StringType),
                ObjectType.Property("state", StringType),
                ObjectType.Property("postalCode", StringType),
                ObjectType.Property("country", StringType),
            )
        else:
            return StringType(field_name)  # Default to string for unknown types

    def _get_replication_key(self, sobject: dict) -> Optional[str]:
        """Get the replication key for a Salesforce object.

        Args:
            sobject: Salesforce object metadata

        Returns:
            The name of the replication key field
        """
        # Get detailed object description
        object_desc = self.client.describe_object(sobject["name"])
        fields = object_desc["fields"]

        # Try standard replication key fields in order of preference
        replication_keys = ["SystemModstamp", "LastModifiedDate", "CreatedDate"]

        replication_key = None
        for key in replication_keys:
            if any(field["name"] == key for field in fields):
                replication_key = key

        return replication_key
