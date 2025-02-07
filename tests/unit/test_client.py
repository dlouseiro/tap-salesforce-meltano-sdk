"""Unit tests for Salesforce clients."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import HTTPError

from tap_salesforce.clients.bulk import BulkClient
from tap_salesforce.clients.bulk2 import Bulk2Client
from tap_salesforce.clients.rest import RestClient


class TestRestClient:
    """Test cases for REST API client."""

    def test_query_success(self, mock_authenticator, mock_config):
        """Test successful query execution."""
        client = RestClient(mock_authenticator, mock_config)

        # Mock response for query
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "records": [
                {"Id": "001", "Name": "Test 1", "attributes": {"type": "Account"}},
                {"Id": "002", "Name": "Test 2", "attributes": {"type": "Account"}},
            ],
            "done": True,
            "totalSize": 2,
        }

        with patch("requests.get", return_value=mock_response):
            records = list(client.query("SELECT Id, Name FROM Account"))

            assert len(records) == 2
            assert records[0]["Id"] == "001"
            assert "attributes" not in records[0]

    def test_query_pagination(self, mock_authenticator, mock_config):
        """Test query pagination."""
        client = RestClient(mock_authenticator, mock_config)

        # Mock responses for paginated query
        responses = [
            {
                "records": [{"Id": "001", "Name": "Test 1"}],
                "done": False,
                "nextRecordsUrl": "/services/data/v57.0/query/01gxx000000001",
            },
            {
                "records": [{"Id": "002", "Name": "Test 2"}],
                "done": True,
            },
        ]

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [MagicMock(json=lambda: resp) for resp in responses]

            records = list(client.query("SELECT Id, Name FROM Account"))
            assert len(records) == 2
            assert mock_get.call_count == 2

    def test_query_error(self, mock_authenticator, mock_config):
        """Test error handling in query."""
        client = RestClient(mock_authenticator, mock_config)
        error_response = MagicMock()
        error_response.raise_for_status.side_effect = HTTPError("Invalid query")

        with patch("requests.get", return_value=error_response):
            with pytest.raises(HTTPError):
                list(client.query("INVALID QUERY"))


class TestBulkClient:
    """Test cases for Bulk API client."""

    def test_create_job(self, mock_authenticator, mock_config):
        """Test job creation."""
        client = BulkClient(mock_authenticator, mock_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "750xx000000001"}

        with patch("requests.post", return_value=mock_response):
            job_id = client._create_query_job("SELECT Id FROM Account")
            assert job_id == "750xx000000001"

    def test_get_job_results(self, mock_authenticator, mock_config):
        """Test getting job results."""
        client = BulkClient(mock_authenticator, mock_config)

        # Mock CSV response
        csv_content = "Id,Name\n001,Test 1\n002,Test 2"
        mock_response = MagicMock()
        mock_response.text = csv_content

        with patch("requests.get", return_value=mock_response):
            results = list(client._get_job_results("750xx000000001"))
            assert len(results) == 2
            assert results[0]["Id"] == "001"


class TestBulk2Client:
    """Test cases for Bulk 2.0 API client."""

    def test_query_with_locator(self, mock_authenticator, mock_config):
        """Test query execution with locator."""
        client = Bulk2Client(mock_authenticator, mock_config)

        # Mock job creation
        job_response = MagicMock()
        job_response.json.return_value = {"id": "750xx000000001"}

        # Mock job status
        status_response = MagicMock()
        status_response.json.return_value = {"state": "JobComplete"}

        # Mock results
        results_response = MagicMock()
        results_response.text = "Id,Name\n001,Test 1"

        with patch("requests.post", return_value=job_response), patch(
            "requests.get", side_effect=[status_response, results_response]
        ):
            records = list(client.query("SELECT Id, Name FROM Account"))
            assert len(records) == 1
            assert records[0]["Id"] == "001"

    def test_failed_results(self, mock_authenticator, mock_config):
        """Test retrieving failed results."""
        client = Bulk2Client(mock_authenticator, mock_config)

        # Mock failed results response
        failed_response = MagicMock()
        failed_response.text = "Id,Error\n001,Record locked"

        with patch("requests.get", return_value=failed_response):
            failed_records = client.get_failed_results("750xx000000001")
            assert len(failed_records) == 1
            assert failed_records[0]["Error"] == "Record locked"
