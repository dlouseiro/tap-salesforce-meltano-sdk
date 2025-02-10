"""Error handling for Salesforce tap.

This module provides specialized error classes and handling utilities for common
Salesforce API issues, network problems, and sync-related errors.

Error categories:
1. Authentication errors
2. API-specific errors (REST, Bulk, Bulk2)
3. Rate limiting and quota errors
4. Data validation errors
5. State/bookmark errors
"""

from singer_sdk.exceptions import RetriableAPIError

RETRYABLE_ERROR_CODES = {
    "REQUEST_LIMIT_EXCEEDED",
    "INVALID_SESSION_ID",
    "SERVER_UNAVAILABLE",
    "RESOURCE_NOT_AVAILABLE",
    "DB_TIMEOUT",
    "QUERY_TIMEOUT",
}


class SalesforceError(Exception):
    """Base exception for all Salesforce-related errors."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        """Initialize base error.

        Args:
            message: Error description
            error_code: Optional Salesforce error code
        """
        super().__init__(message)
        self.error_code = error_code


# Authentication Errors
class SalesforceAuthError(SalesforceError):
    """Raised when authentication fails."""


class ExpiredCredentialsError(SalesforceAuthError):
    """Raised when OAuth tokens or passwords expire."""


class InvalidCredentialsError(SalesforceAuthError):
    """Raised when credentials are invalid."""


# API Errors
class SalesforceAPIError(SalesforceError):
    """Base class for API-related errors."""


class RESTAPIError(SalesforceAPIError):
    """Errors specific to REST API operations."""


class BulkAPIError(SalesforceAPIError):
    """Errors specific to Bulk API operations."""


class Bulk2APIError(SalesforceAPIError):
    """Errors specific to Bulk 2.0 API operations."""


class QueryTimeoutError(SalesforceAPIError):
    """Raised when a query exceeds the timeout limit."""


class ResultTimeoutError(SalesforceAPIError):
    """Raised when waiting for results exceeds timeout."""


# Rate Limiting
class SalesforceQuotaError(SalesforceAPIError):
    """Base class for quota and rate limit errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize quota error.

        Args:
            message: Error description
            error_code: Optional Salesforce error code
            retry_after: Seconds to wait before retrying
        """
        super().__init__(message, error_code=error_code)
        self.retry_after = retry_after


class DailyAPILimitError(SalesforceQuotaError):
    """Raised when daily API limits are exceeded."""


class ConcurrentAPILimitError(SalesforceQuotaError):
    """Raised when too many concurrent API requests are made."""


class BulkQuotaError(SalesforceQuotaError):
    """Raised when Bulk API quotas are exceeded."""


# Data Validation
class SalesforceDataError(SalesforceError):
    """Base class for data-related errors."""


class InvalidFieldError(SalesforceDataError):
    """Raised when referencing invalid fields."""


class InvalidFilterError(SalesforceDataError):
    """Raised when filter conditions are invalid."""


class RecordTypeError(SalesforceDataError):
    """Raised when record type issues occur."""


# State/Bookmark Errors
class SalesforceStateError(SalesforceError):
    """Base class for state-related errors."""


class InvalidBookmarkError(SalesforceStateError):
    """Raised when bookmark values are invalid."""


class StateValidationError(SalesforceStateError):
    """Raised when state validation fails."""


# Retryable Errors
class RetryableSalesforceError(SalesforceError, RetriableAPIError):
    """Base class for retryable Salesforce errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize retryable error.

        Args:
            message: Error description
            error_code: Optional Salesforce error code
            retry_after: Seconds to wait before retrying
        """
        SalesforceError.__init__(self, message, error_code=error_code)
        self.retry_after = retry_after


# Object/Schema Errors
class InvalidSalesforceObjectError(SalesforceError):
    """Raised when a Salesforce object is invalid or inaccessible."""


# Job Management
class BulkJobError(SalesforceError):
    """Base class for bulk job errors."""


class JobTimeoutError(BulkJobError):
    """Raised when a bulk job exceeds timeout."""


class JobFailedError(BulkJobError):
    """Raised when a bulk job fails."""


class BatchError(BulkJobError):
    """Raised when a batch operation fails."""


def is_retryable_error(error_code: str) -> bool:
    """Check if a Salesforce error code indicates a retryable error.

    Args:
        error_code: Salesforce API error code

    Returns:
        True if error is retryable
    """
    return error_code in RETRYABLE_ERROR_CODES


def get_error_details(response_json: dict) -> tuple[str | None, str]:
    """Extract error details from Salesforce API response.

    Args:
        response_json: Response JSON from Salesforce API

    Returns:
        Tuple of (error_code, error_message)
    """
    # Handle list responses (common in batch operations)
    if isinstance(response_json, list):
        response_json = response_json[0]

    error_code = response_json.get("errorCode")
    error_message = response_json.get("message", "Unknown error")

    return error_code, error_message


def raise_for_error(response_json: dict) -> None:
    """Raise appropriate exception based on Salesforce error response.

    Args:
        response_json: Error response from Salesforce API

    Raises:
        Appropriate SalesforceError subclass based on error details
    """
    error_code, message = get_error_details(response_json)

    # Authentication errors
    if error_code in ["INVALID_SESSION_ID", "INVALID_AUTH"]:
        raise InvalidCredentialsError(message, error_code=error_code)
    if error_code == "EXPIRED_ACCESS_TOKEN":
        raise ExpiredCredentialsError(message, error_code=error_code)

    # Quota errors
    if error_code == "REQUEST_LIMIT_EXCEEDED":
        retry_after = int(response_json.get("retryAfter", 60))
        raise DailyAPILimitError(
            message, error_code=error_code, retry_after=retry_after
        )

    # Data errors
    if error_code == "INVALID_FIELD":
        raise InvalidFieldError(message, error_code=error_code)
    if error_code == "MALFORMED_QUERY":
        raise InvalidFilterError(message, error_code=error_code)

    # Retryable errors
    if is_retryable_error(error_code):
        retry_after = int(response_json.get("retryAfter", 60))
        raise RetryableSalesforceError(
            message, error_code=error_code, retry_after=retry_after
        )

    # Default to base error
    raise SalesforceError(message, error_code=error_code)
