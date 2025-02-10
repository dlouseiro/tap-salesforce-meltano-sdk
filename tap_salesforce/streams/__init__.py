"""Salesforce stream implementations.

This module provides stream classes for different Salesforce API types:
- REST API for real-time and smaller dataset access
- Bulk API for large dataset processing
- Bulk2 API for improved performance and monitoring
"""

from tap_salesforce.streams.base import BaseSalesforceStream
from tap_salesforce.streams.bulk import SalesforceBulkStream
from tap_salesforce.streams.bulk2 import SalesforceBulk2Stream
from tap_salesforce.streams.rest import SalesforceRestStream

__all__ = [
    "BaseSalesforceStream",
    "SalesforceBulk2Stream",
    "SalesforceBulkStream",
    "SalesforceRestStream",
]
