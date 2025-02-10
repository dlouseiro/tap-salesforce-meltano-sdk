"""Schema discovery functionality for Salesforce tap.

This module is responsible for dynamically discovering and generating JSON schemas
for Salesforce objects. Key functionality includes:

1. Object discovery:
   - Finding available Salesforce objects
   - Filtering based on permissions
   - Handling custom and standard objects

2. Schema generation:
   - Converting Salesforce field types to JSON Schema
   - Handling compound fields (addresses, locations)
   - Managing object relationships
   - Supporting field metadata (descriptions, picklists)

Example usage:
    schema_generator = SalesforceSchemaGenerator(authenticator, logger)
    available_objects = schema_generator.get_available_objects()
    for object_name in available_objects:
        schema = schema_generator.generate_schema(object_name)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging

    from requests import Response

if TYPE_CHECKING:
    from tap_salesforce.auth import SalesforceAuthenticator

from tap_salesforce.schemas.types import SalesforceTypeHelper


class SalesforceSchemaGenerator:
    """Handles schema generation for Salesforce objects.

    This class is responsible for discovering available Salesforce objects and
    generating corresponding JSON schemas based on their metadata.
    """

    def __init__(
        self,
        authenticator: SalesforceAuthenticator,
        logger: logging.Logger,
    ) -> None:
        """Initialize the schema generator.

        Args:
            authenticator: Salesforce authenticator instance
            logger: Logger instance for recording progress/issues
        """
        self.authenticator = authenticator
        self.logger = logger
        self._global_describe: dict[str, Any] | None = None

    def get_available_objects(self) -> dict[str, dict[str, Any]]:
        """Get list of available Salesforce objects.

        Objects are filtered based on:
        1. Queryable flag (can be accessed via SOQL)
        2. User permissions
        3. Object type (custom vs standard)

        Returns:
            Dictionary mapping object names to their metadata
        """
        if not self._global_describe:
            response = self.authenticator.make_request(
                "GET",
                "/services/data/v60.0/sobjects/",
            )
            self._global_describe = response.json()

        available_objects: dict[str, dict[str, Any]] = {}
        if self._global_describe and "sobjects" in self._global_describe:
            for obj in self._global_describe["sobjects"]:
                # Skip objects we can't query
                if not obj["queryable"]:
                    continue

                # Skip objects user can't access
                if not (obj["retrieveable"] and obj["accessible"]):
                    continue

                available_objects[obj["name"]] = {
                    "label": obj["label"],
                    "custom": obj["custom"],
                    "createable": obj["createable"],
                    "updateable": obj["updateable"],
                    "deletable": obj["deletable"],
                }

        return available_objects

    def _get_object_description(self, object_name: str) -> dict[str, Any]:
        """Get detailed object metadata from Salesforce.

        Args:
            object_name: Name of the Salesforce object

        Returns:
            Complete object metadata from Salesforce describe call

        Raises:
            ValueError: If the object doesn't exist or is inaccessible
        """
        response: Response = self.authenticator.make_request(
            "GET",
            f"/services/data/v60.0/sobjects/{object_name}/describe",
        )

        # Use HTTP status code
        if response.status_code in (404, 400):
            error_msg = f"Object {object_name} not found or not accessible"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        return response.json()

    def generate_schema(self, object_name: str) -> dict[str, Any]:
        """Generate JSON Schema for a Salesforce object.

        Processes object metadata to create a complete JSON Schema that:
        1. Maps Salesforce types to JSON Schema types
        2. Includes field metadata like descriptions
        3. Handles compound fields
        4. Specifies required fields

        Args:
            object_name: Name of the Salesforce object

        Returns:
            Complete JSON Schema for the object

        Raises:
            ValueError: If object doesn't exist or is inaccessible
        """
        object_desc = self._get_object_description(object_name)

        properties: dict[str, dict[str, Any]] = {}
        required_fields: list[str] = []

        for field in object_desc["fields"]:
            field_name = field["name"]

            # Skip compound fields that will be expanded
            if field["compound"]:
                continue

            # Convert field type using shared type helper
            field_schema = SalesforceTypeHelper.get_json_schema_type(
                field["type"],
                field,
            )

            # Add field metadata
            field_props = {
                "type": field_schema.type_dict["type"],
                "description": field.get("description", ""),
            }

            # Add format for date/time fields
            if field["type"].lower() in ["datetime", "date", "time"]:
                field_props["format"] = field["type"].lower()

            # Handle required fields
            if not field.get("nillable", True) and field.get("createable", True):
                required_fields.append(field_name)

            properties[field_name] = field_props

        # Build complete schema
        schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
        }

        if required_fields:
            schema["required"] = required_fields

        return schema
