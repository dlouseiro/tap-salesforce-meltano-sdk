"""Salesforce tap class.

This module implements the Singer tap for Salesforce. It provides:
1. Configuration management and validation
2. Dynamic schema discovery
3. Stream creation and management
4. Authentication handling
5. API type selection (REST, BULK, BULK2)
"""

from __future__ import annotations

import typing as t
from datetime import datetime, timedelta, timezone
from pathlib import Path

from singer_sdk import Tap, Stream
from singer_sdk import typing as th
from singer_sdk.helpers.capabilities import (
    TapCapabilities,
    PluginCapabilities,
    CapabilitiesEnum,
)
from singer_sdk.helpers._util import utc_now
from singer_sdk.exceptions import ConfigValidationError

from tap_salesforce.auth import SalesforceAuthenticator
from tap_salesforce.streams import (
    SalesforceRestStream,
    SalesforceBulkStream,
    SalesforceBulk2Stream,
)
from tap_salesforce.schemas.discovery import SalesforceSchemaGenerator

class TapSalesforce(Tap):
    """Singer tap for Salesforce."""

    name = "tap-salesforce"
    package_name = "tap-salesforce"
    default_stream_name = "salesforce"

    # Stream classes keyed by API type
    STREAM_TYPES = {
        "REST": SalesforceRestStream,
        "BULK": SalesforceBulkStream,
        "BULK2": SalesforceBulk2Stream,
    }

    # Enable dynamic catalog discovery
    dynamic_catalog = True

    config_jsonschema = th.PropertiesList(
        # Authentication Settings
        th.Property(
            "auth_type",
            th.StringType(allowed_values=["oauth", "password"]),
            required=True,
            description="Authentication method to use",
        ),
        th.Property(
            "client_id",
            th.StringType,
            secret=True,
            description="OAuth 2.0 Client ID",
        ),
        th.Property(
            "client_secret",
            th.StringType,
            secret=True,
            description="OAuth 2.0 Client Secret",
        ),
        th.Property(
            "refresh_token",
            th.StringType,
            secret=True,
            description="OAuth 2.0 Refresh Token",
        ),
        th.Property(
            "username",
            th.StringType,
            description="Salesforce username for password authentication",
        ),
        th.Property(
            "password",
            th.StringType,
            secret=True,
            description="Salesforce password for password authentication",
        ),
        th.Property(
            "security_token",
            th.StringType,
            secret=True,
            description="Salesforce security token for password authentication",
        ),

        # API Configuration
        th.Property(
            "api_type",
            th.StringType(allowed_values=["REST", "BULK", "BULK2"]),
            required=True,
            default="REST",
            description=(
                "Salesforce API to use. REST for real-time/small datasets, "
                "BULK/BULK2 for large datasets"
            ),
        ),
        th.Property(
            "api_version",
            th.StringType,
            default="v60.0",
            description="Salesforce API version to use",
        ),
        th.Property(
            "is_sandbox",
            th.BooleanType,
            default=False,
            description="Set to true when connecting to a Salesforce sandbox",
        ),

        # Stream Selection
        th.Property(
            "streams_to_discover",
            th.ArrayType(th.StringType),
            description=(
                "List of Salesforce objects to sync. If empty, all accessible "
                "objects will be discovered"
            ),
        ),
        th.Property(
            "select_fields_by_default",
            th.BooleanType,
            default=True,
            description=(
                "When true, newly discovered fields will be selected for "
                "extraction by default"
            ),
        ),

        # Performance Settings
        th.Property(
            "request_timeout",
            th.IntegerType,
            default=300,
            description="Timeout in seconds for API requests",
        ),
        th.Property(
            "batch_size",
            th.IntegerType,
            default=10000,
            description="Number of records to process in each batch",
        ),
        th.Property(
            "max_workers",
            th.IntegerType,
            default=8,
            description="Maximum number of concurrent API requests",
        ),

        # Replication Settings
        th.Property(
            "start_date",
            th.DateTimeType,
            description=(
                "Earliest record date to replicate. Defaults to yesterday if not set"
            ),
        ),
        th.Property(
            "lookback_window",
            th.IntegerType,
            default=0,
            description=(
                "Number of minutes to look back when resuming replication to "
                "catch any updated records"
            ),
        ),

        # Advanced Settings
        th.Property(
            "enable_pk_chunking",
            th.BooleanType,
            default=True,
            description=(
                "Enable automatic primary key chunking for large object syncs"
            ),
        ),
        th.Property(
            "sync_deleted_records",
            th.BooleanType,
            default=True,
            description="Whether to sync records that have been deleted in Salesforce",
        ),
    ).to_dict()

    @property
    def catalog_dict(self) -> dict:
        """Get catalog dictionary.

        Returns:
            The tap's catalog as a dict
        """
        if hasattr(self, "_catalog_dict"):
            return self._catalog_dict
        return super().catalog_dict

    @property
    def authenticator(self) -> SalesforceAuthenticator:
        """Get authenticator instance.

        Returns:
            An authenticator instance for this tap
        """
        if not hasattr(self, "_authenticator"):
            self._authenticator = SalesforceAuthenticator(
                stream_name=self.default_stream_name,
                config=self.config,
            )
        return self._authenticator

    def discover_streams(self) -> list[Stream]:
        """Return a list of discovered streams.

        Returns:
            List of discovered Stream objects
        """
        schema_generator = SalesforceSchemaGenerator(
            authenticator=self.authenticator,
            logger=self.logger,
        )

        streams: list[Stream] = []
        available_objects = schema_generator.get_available_objects()

        # Filter to specific objects if configured
        objects_to_discover = self.config.get("streams_to_discover", [])
        if objects_to_discover:
            available_objects = {
                name: meta
                for name, meta in available_objects.items()
                if name in objects_to_discover
            }

        # Create streams for each discovered object
        api_type = self.config["api_type"].upper()
        stream_class = self.STREAM_TYPES[api_type]

        for object_name, object_meta in available_objects.items():
            try:
                # Generate schema
                schema = schema_generator.generate_schema(object_name)

                # Determine replication key - prefer SystemModstamp
                replication_key = None
                schema_properties = schema.get("properties", {})
                if "SystemModstamp" in schema_properties:
                    replication_key = "SystemModstamp"
                elif "LastModifiedDate" in schema_properties:
                    replication_key = "LastModifiedDate"

                # Create stream instance
                stream = stream_class(
                    tap=self,
                    name=object_name,
                    schema=schema,
                    replication_key=replication_key,
                    primary_keys=["Id"],  # Salesforce always uses Id
                    authenticator=self.authenticator,
                    api_type=api_type,
                )

                # Configure stream properties based on object metadata
                stream.selected_by_default = object_meta.get("queryable", True)

                streams.append(stream)

                self.logger.info(
                    "Discovered stream '%s' (API: %s, Replication Key: %s)",
                    object_name,
                    api_type,
                    replication_key or "N/A",
                    )

            except Exception as err:
                self.logger.warning(
                    "Failed to discover stream '%s': %s",
                    object_name,
                    str(err),
                )
                continue

        return streams

    def validate_config(self) -> None:
        """Validate tap configuration.

        Raises:
            ConfigValidationError: If the config is invalid
        """
        super().validate_config()

        # Validate authentication settings
        auth_type = self.config["auth_type"]
        if auth_type == "oauth":
            required_fields = ["client_id", "client_secret", "refresh_token"]
            missing = [f for f in required_fields if not self.config.get(f)]
            if missing:
                raise ConfigValidationError(
                    f"Missing required OAuth fields: {', '.join(missing)}"
                )
        elif auth_type == "password":
            required_fields = ["username", "password", "security_token"]
            missing = [f for f in required_fields if not self.config.get(f)]
            if missing:
                raise ConfigValidationError(
                    f"Missing required password auth fields: {', '.join(missing)}"
                )

        # Validate API version format
        api_version = self.config["api_version"]
        if not api_version.startswith("v") or not api_version.split(".")[-1].isdigit():
            raise ConfigValidationError(
                f"Invalid API version format: {api_version}. Expected format: 'vXX.0'"
            )

    @property
    def capabilities(self) -> list[CapabilitiesEnum]:
        """Get tap capabilities.

        Returns:
            List of capabilities supported by this tap
        """
        return [
            TapCapabilities.CATALOG,
            TapCapabilities.STATE,
            TapCapabilities.DISCOVER,
            PluginCapabilities.ABOUT,
            PluginCapabilities.STREAM_MAPS,
            PluginCapabilities.FLATTENING,
        ]

    def get_starting_replication_value(self, stream) -> datetime | None:
        """Get starting replication value for incremental sync.

        Args:
            stream: Stream instance to get starting value for

        Returns:
            Starting datetime for replication or None
        """
        # Check state for existing bookmark
        state_bookmark = self.get_state_bookmark(stream.tap_stream_id)
        if state_bookmark:
            return state_bookmark

        # Apply lookback window if configured
        lookback_minutes = self.config.get("lookback_window", 0)
        if lookback_minutes and state_bookmark:
            return state_bookmark - timedelta(minutes=lookback_minutes)

        # Default to configured start_date or 24 hours ago
        if "start_date" in self.config:
            return datetime.fromisoformat(self.config["start_date"])

        return utc_now() - timedelta(days=1)

    def get_state_bookmark(self, stream_id: str) -> datetime | None:
        """Get bookmark value from state.

        Args:
            stream_id: Stream identifier

        Returns:
            Bookmark datetime if found, None otherwise
        """
        bookmark = (
            self.state.get("bookmarks", {})
            .get(stream_id, {})
            .get("replication_key_value")
        )
        if bookmark:
            try:
                return datetime.fromisoformat(bookmark)
            except ValueError:
                self.logger.warning(
                    "Invalid bookmark format for stream '%s': %s",
                    stream_id,
                    bookmark,
                )
        return None
