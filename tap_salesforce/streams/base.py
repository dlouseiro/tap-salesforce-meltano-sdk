"""Base stream class for Salesforce."""

from abc import ABC
from typing import Any, Dict, Iterable, List, Optional, Union

from singer_sdk import typing as th
from singer_sdk.streams import Stream

from tap_salesforce.auth import SalesforceAuthenticator
from tap_salesforce.clients.base import SalesforceClient


class SalesforceStream(Stream, ABC):
    """Base stream class for Salesforce."""

    def __init__(
        self,
        tap,
        schema: Optional[Union[Dict[str, Any], str]] = None,
        name: Optional[str] = None,
    ) -> None:
        """Initialize the Salesforce stream.

        Args:
            tap: The tap instance
            schema: The stream schema
            name: The stream name
        """
        super().__init__(tap=tap, schema=schema, name=name)
        self._client: Optional[SalesforceClient] = None
        self._authenticator: Optional[SalesforceAuthenticator] = None
        self._fields: Optional[List[Dict[str, Any]]] = None

    @property
    def authenticator(self) -> SalesforceAuthenticator:
        """Get or create authenticator instance.

        Returns:
            A SalesforceAuthenticator instance
        """
        if not self._authenticator:
            self._authenticator = SalesforceAuthenticator(self)
        return self._authenticator

    @property
    def client(self) -> SalesforceClient:
        """Get or create client instance.

        Returns:
            A SalesforceClient instance
        """
        if not self._client:
            self._client = self._get_client()
        return self._client

    def _get_client(self) -> SalesforceClient:
        """Get the appropriate Salesforce client based on config.

        Returns:
            A SalesforceClient instance
        """
        api_type = self.config.get("api_type", "REST").upper()

        if api_type == "REST":
            from tap_salesforce.clients.rest import RestClient

            return RestClient(self.authenticator, self.config)
        elif api_type == "BULK":
            from tap_salesforce.clients.bulk import BulkClient

            return BulkClient(self.authenticator, self.config)
        elif api_type == "BULK2":
            from tap_salesforce.clients.bulk2 import Bulk2Client

            return Bulk2Client(self.authenticator, self.config)
        else:
            raise ValueError(f"Unsupported API type: {api_type}")

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        """Get records from Salesforce.

        Args:
            context: Stream partition or context dictionary

        Yields:
            Record dictionaries from Salesforce
        """
        query = self._build_query(context)
        yield from self.client.query(query)

    def _build_query(self, context: Optional[dict] = None) -> str:
        """Build SOQL query for the stream.

        Args:
            context: Stream partition or context dictionary

        Returns:
            A SOQL query string
        """
        fields = self._get_selected_fields()
        query = f"SELECT {','.join(fields)} FROM {self.name}"

        # Add conditions based on context and replication key
        where_clauses = []

        # Add replication key condition if available
        if self.replication_key:
            start_date = self.get_starting_timestamp(context)
            if start_date:
                where_clauses.append(
                    f"{self.replication_key} >= {start_date.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                )

        # Add any custom filters from config
        custom_filter = self.config.get("custom_filters", {}).get(self.name)
        if custom_filter:
            where_clauses.append(f"({custom_filter})")

        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"

        # Add ORDER BY for replication key
        if self.replication_key:
            query += f" ORDER BY {self.replication_key} ASC"

        return query

    def _get_selected_fields(self) -> List[str]:
        """Get list of fields to query.

        Returns:
            List of field names to include in query
        """
        if not self._fields:
            self._fields = self.client.get_all_fields(self.name)

        selected_fields = []
        for field in self._fields:
            # Skip unsupported field types
            if field["type"] in ["address", "location"]:
                continue

            # Include field if it's selected in catalog or if select_fields_by_default is True
            if self.config.get("select_fields_by_default", True) or self.schema.get(
                "properties", {}
            ).get(field["name"]):
                selected_fields.append(field["name"])

        return selected_fields

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Get context dictionary for child streams.

        Args:
            record: Record dictionary from Salesforce
            context: Stream partition or context dictionary

        Returns:
            A context dictionary for child streams
        """
        to_return = {"parent_id": record["Id"]}
        if context:
            to_return.update(context)

        return to_return

    @property
    def schema(self) -> dict:
        """Get dynamically generated schema.

        Returns:
            JSON Schema dictionary
        """
        if not self._schema:
            self._schema = self._get_schema()
        return self._schema

    def _get_schema(self) -> dict:
        """Generate schema from Salesforce metadata.

        Returns:
            JSON Schema dictionary
        """
        properties = {}

        for field in self.client.get_all_fields(self.name):
            field_name = field["name"]
            field_type = field["type"]

            # Map Salesforce types to JSON Schema types
            json_schema_type = self._get_json_schema_type(field_type)

            if json_schema_type:
                properties[field_name] = json_schema_type

        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
        }

    def _get_json_schema_type(self, salesforce_type: str) -> dict:
        """Map Salesforce field type to JSON Schema type.

        Args:
            salesforce_type: Salesforce field type

        Returns:
            JSON Schema type definition
        """
        # Basic type mappings
        type_map = {
            "string": th.StringType,
            "id": th.StringType,
            "reference": th.StringType,
            "boolean": th.BooleanType,
            "int": th.IntegerType,
            "double": th.NumberType,
            "currency": th.NumberType,
            "percent": th.NumberType,
            "date": th.DateType,
            "datetime": th.DateTimeType,
            "time": th.TimeType,
            "url": th.URIType,
            "email": th.EmailType,
            "phone": th.StringType,
            "textarea": th.StringType,
            "picklist": th.StringType,
            "multipicklist": th.ArrayType(th.StringType),
            "combobox": th.StringType,
            "encryptedstring": th.StringType,
            "base64": th.StringType,
        }

        field_type = type_map.get(salesforce_type.lower())
        if field_type:
            return field_type().to_dict()

        # Complex types
        if salesforce_type.lower() in ["address", "location"]:
            return th.ObjectType(
                th.Property("street", th.StringType),
                th.Property("city", th.StringType),
                th.Property("state", th.StringType),
                th.Property("postalCode", th.StringType),
                th.Property("country", th.StringType),
                th.Property("latitude", th.NumberType),
                th.Property("longitude", th.NumberType),
            ).to_dict()

        # Default to string type for unknown types
        return th.StringType().to_dict()
