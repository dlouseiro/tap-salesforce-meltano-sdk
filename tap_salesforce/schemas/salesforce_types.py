"""Salesforce type system definitions.

This module serves as the single source of truth for Salesforce field type mappings
and related type conversion logic. It's used by both schema discovery and stream
processing code.
"""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict

from singer_sdk import typing as th


class SalesforceFieldInfo(TypedDict, total=False):
    """Type definition for Salesforce field metadata."""

    type: str
    nillable: bool
    picklistValues: list[dict[str, Any]]
    compound: bool
    createable: bool


class SalesforceTypeHelper:
    """Helper class for Salesforce type operations."""

    # Master mapping of Salesforce types to JSON Schema types
    SF_TYPE_MAPPING: ClassVar[dict[str, type[th.JSONTypeHelper]]] = {
        # String types
        "id": th.StringType,
        "string": th.StringType,
        "picklist": th.StringType,
        "multipicklist": th.ArrayType(th.StringType),
        "combobox": th.StringType,
        "reference": th.StringType,
        "encryptedstring": th.StringType,
        "email": th.StringType,
        "url": th.StringType,
        "phone": th.StringType,
        "textarea": th.StringType,
        # Numeric types
        "double": th.NumberType,
        "currency": th.NumberType,
        "percent": th.NumberType,
        "int": th.IntegerType,
        "long": th.IntegerType,
        # Date/time types
        "datetime": th.DateTimeType,
        "date": th.DateType,
        "time": th.TimeType,
        # Other types
        "boolean": th.BooleanType,
        "base64": th.StringType,
        "anyType": th.StringType,
    }

    # Fields that need special handling
    COMPOUND_TYPES: ClassVar[dict[str, dict[str, type[th.JSONTypeHelper]]]] = {
        "address": {
            "street": th.StringType,
            "city": th.StringType,
            "state": th.StringType,
            "postalCode": th.StringType,
            "country": th.StringType,
            "latitude": th.NumberType,
            "longitude": th.NumberType,
            "geocodeAccuracy": th.StringType,
        },
        "location": {
            "latitude": th.NumberType,
            "longitude": th.NumberType,
        },
    }

    @classmethod
    def get_json_schema_type(
        cls,
        salesforce_type: str,
        field_info: SalesforceFieldInfo | None = None,
    ) -> th.JSONTypeHelper:
        """Convert a Salesforce field type to its JSON Schema equivalent.

        Args:
            salesforce_type: The Salesforce field type name
            field_info: Optional additional field metadata

        Returns:
            The appropriate JSON Schema type definition
        """
        base_type = salesforce_type.lower()

        # Handle compound types
        if base_type in cls.COMPOUND_TYPES:
            return th.ObjectType(
                **{
                    name: type_class()
                    for name, type_class in cls.COMPOUND_TYPES[base_type].items()
                }
            )

        # Get base type mapping
        schema_type = cls.SF_TYPE_MAPPING.get(base_type, th.StringType)

        # Apply field-specific customizations if we have field info
        if field_info:
            # Handle picklist values
            if base_type == "picklist" and field_info.get("picklistValues"):
                allowed_values = [
                    val["value"]
                    for val in field_info["picklistValues"]
                    if val.get("active", True)
                ]
                return th.StringType(allowed_values=allowed_values)

            # Handle required fields
            if not field_info.get("nillable", True):
                return schema_type(nullable=False)

        return schema_type()
