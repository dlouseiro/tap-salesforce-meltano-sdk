"""Unit tests for streams."""

from unittest.mock import MagicMock

from singer_sdk import Tap

from tap_salesforce.streams.base import SalesforceStream
from tap_salesforce.streams.bulk import BulkStream
from tap_salesforce.streams.bulk2 import Bulk2Stream
from tap_salesforce.streams.rest import RestStream


class TestSalesforceStream:
    """Test cases for base stream."""

    def test_schema_generation(self, mock_config, sample_object_metadata):
        """Test dynamic schema generation."""
        stream = SalesforceStream(tap=MagicMock(spec=Tap))
        stream.config = mock_config
        stream.name = "Account"

        # Mock client's get_all_fields method
        mock_client = MagicMock()
        mock_client.get_all_fields.return_value = sample_object_metadata["fields"]
        stream._client = mock_client

        schema = stream.schema

        assert schema["type"] == "object"
        assert "Id" in schema["properties"]
        assert schema["properties"]["CreatedDate"]["type"] == "string"
        assert schema["properties"]["CreatedDate"]["format"] == "date-time"

    def test_query_building(self, mock_config):
        """Test SOQL query building."""
        stream = SalesforceStream(tap=MagicMock(spec=Tap))
        stream.config = mock_config
        stream.name = "Account"
        stream.replication_key = "LastModifiedDate"
        # Mock selected fields
        stream._get_selected_fields = MagicMock(
            return_value=["Id", "Name", "LastModifiedDate"],
        )

        query = stream._build_query({"start_date": "2023-01-01T00:00:00Z"})

        assert "SELECT Id,Name,LastModifiedDate FROM Account" in query
        assert "WHERE LastModifiedDate >=" in query
        assert "ORDER BY LastModifiedDate ASC" in query


class TestRestStream:
    """Test cases for REST stream."""

    def test_rest_pagination(self, mock_config):
        """Test REST API pagination."""
        stream = RestStream(tap=MagicMock(spec=Tap))
        stream.config = mock_config
        stream.name = "Account"

        # Mock client query method
        mock_client = MagicMock()
        mock_client.query.return_value = iter(
            [
                {"Id": "001", "Name": "Test 1"},
                {"Id": "002", "Name": "Test 2"},
            ]
        )
        stream._client = mock_client

        records = list(stream.get_records(None))
        assert len(records) == 2
        assert "LIMIT 2000" in mock_client.query.call_args[0][0]


class TestBulkStream:
    """Test cases for Bulk API stream."""

    def test_bulk_query_hints(self, mock_config):
        """Test Bulk API query optimization hints."""
        stream = BulkStream(tap=MagicMock(spec=Tap))
        stream.config = {**mock_config, "bulk_api_hints": True}
        stream.name = "Account"

        # Mock selected fields
        stream._get_selected_fields = MagicMock(return_value=["Id", "Name"])

        query = stream._build_query()
        assert "DISABLE_QUERY_OPTIMIZATION" in query
        assert "ENABLE_PARALLEL_PROCESSING" in query


class TestBulk2Stream:
    """Test cases for Bulk 2.0 API stream."""

    def test_bulk2_locator_hint(self, mock_config):
        """Test Bulk 2.0 API locator hint."""
        stream = Bulk2Stream(tap=MagicMock(spec=Tap))
        stream.config = {**mock_config, "bulk2_use_locator": True}
        stream.name = "Account"

        # Mock selected fields
        stream._get_selected_fields = MagicMock(return_value=["Id", "Name"])

        query = stream._build_query()
        assert "ENABLE_LOCATOR" in query
