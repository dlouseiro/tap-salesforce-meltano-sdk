"""Schema package for Salesforce tap.

This package handles schema generation and type mapping for Salesforce objects.
It includes functionality for:
- Converting Salesforce types to JSON Schema
- Dynamic schema discovery
- Field type validation
"""

from tap_salesforce.schemas.discovery import SalesforceSchemaGenerator
from tap_salesforce.schemas.types import SalesforceTypeHelper

__all__ = ["SalesforceSchemaGenerator", "SalesforceTypeHelper"]
