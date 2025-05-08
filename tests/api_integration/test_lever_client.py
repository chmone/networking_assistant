import pytest
import time
from unittest.mock import MagicMock, patch
import requests

# Assuming LeverClient is importable
# Add path adjustment if necessary
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.api_integration.lever_client import LeverClient, DEFAULT_LEVER_CACHE_EXPIRY_SECONDS
# Need a mock for ConfigManager
from src.config.config_manager import ConfigManager 

@pytest.fixture
def mock_config_manager():
    """Fixture for a mocked ConfigManager."""
    mock_cm = MagicMock(spec=ConfigManager)
    # Explicitly make get_config a MagicMock and set its default side_effect
    mock_cm.get_config = MagicMock(side_effect=lambda key, default=None: default)
    return mock_cm

class TestLeverClientInitialization:
    def test_initialization_default_expiry(self, mock_config_manager):
        client = LeverClient(config_manager=mock_config_manager)
        assert client.cache_expiry_seconds == DEFAULT_LEVER_CACHE_EXPIRY_SECONDS
        mock_config_manager.get_config.assert_called_once_with(
            "LEVER_CACHE_EXPIRY_SECONDS", 
            DEFAULT_LEVER_CACHE_EXPIRY_SECONDS
        )

    def test_initialization_custom_expiry(self, mock_config_manager):
        # Define a helper for side_effect
        def custom_expiry_side_effect(key, default=None):
            if key == "LEVER_CACHE_EXPIRY_SECONDS":
                return 9000
            return default
        mock_config_manager.get_config.side_effect = custom_expiry_side_effect
        client = LeverClient(config_manager=mock_config_manager)
        assert client.cache_expiry_seconds == 9000

    def test_initialization_invalid_expiry_string(self, mock_config_manager):
        # Define a helper for side_effect
        def invalid_expiry_side_effect(key, default=None):
            if key == "LEVER_CACHE_EXPIRY_SECONDS":
                return "invalid_string"
            return default
        mock_config_manager.get_config.side_effect = invalid_expiry_side_effect
        client = LeverClient(config_manager=mock_config_manager)
        # Should fall back to default if conversion fails
        assert client.cache_expiry_seconds == DEFAULT_LEVER_CACHE_EXPIRY_SECONDS

class TestLeverClientCacheLogic:
    @pytest.fixture
    def client(self, mock_config_manager):
        return LeverClient(config_manager=mock_config_manager)

    def test_is_cache_valid_true(self, client):
        entry = {"timestamp": time.time() - 100, "data": [{"id": 1}] }
        assert client._is_cache_valid(entry) is True

    def test_is_cache_valid_false_expired(self, client):
        client.cache_expiry_seconds = 500
        entry = {"timestamp": time.time() - 1000, "data": [{"id": 1}]}
        assert client._is_cache_valid(entry) is False

    def test_is_cache_valid_false_missing_timestamp(self, client):
        entry = {"data": [{"id": 1}]}
        assert client._is_cache_valid(entry) is False

    def test_is_cache_valid_false_missing_data(self, client):
        entry = {"timestamp": time.time()}
        assert client._is_cache_valid(entry) is False

    def test_clear_cache_all(self, client):
        client.cache["id1"] = {"timestamp": time.time(), "data": []}
        client.cache["id2"] = {"timestamp": time.time(), "data": []}
        client.clear_cache()
        assert not client.cache

    def test_clear_cache_specific(self, client):
        client.cache["id1"] = {"timestamp": time.time(), "data": [1]}
        client.cache["id2"] = {"timestamp": time.time(), "data": [2]}
        client.clear_cache("id1")
        assert "id1" not in client.cache
        assert "id2" in client.cache
        assert client.cache["id2"]["data"] == [2]

    def test_clear_cache_specific_not_found(self, client):
        client.cache["id1"] = {"timestamp": time.time(), "data": [1]}
        # Should not raise an error
        client.clear_cache("non_existent_id")
        assert "id1" in client.cache # Ensure other entries are untouched

class TestLeverClientGetPostings:
    @pytest.fixture
    def client(self, mock_config_manager):
        return LeverClient(config_manager=mock_config_manager)

    @pytest.fixture
    def mock_requests_get(self, mocker):
        return mocker.patch('src.api_integration.lever_client.requests.get')

    def test_get_postings_missing_company_id(self, client):
        result = client.get_postings(company_lever_id="")
        assert result == []
        # Optionally, check logger call for error

    def test_get_postings_success_no_keywords(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"text": "Software Engineer", "categories": {"location": "SF", "commitment": "Full-time"}, "hostedUrl": "url1", "descriptionPlain": "Develop cool stuff."},
            {"text": "Product Manager", "categories": {"location": "NY", "commitment": "Full-time"}, "hostedUrl": "url2", "descriptionPlain": "Manage products."}
        ]
        mock_response.raise_for_status = MagicMock() # Does not raise
        mock_requests_get.return_value = mock_response

        company_id = "testlever"
        result = client.get_postings(company_id)

        mock_requests_get.assert_called_once_with(f"https://api.lever.co/v0/postings/{company_id}", timeout=10)
        assert len(result) == 2
        assert result[0]["job_title"] == "Software Engineer"
        assert result[0]["source_api"] == "Lever"
        assert result[1]["job_title"] == "Product Manager"
        # Check cache
        cache_key = f"{company_id}_"
        assert cache_key in client.cache
        assert client.cache[cache_key]["data"] == result

    def test_get_postings_success_with_keywords(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"text": "Software Engineer", "categories": {"location": "SF"}, "hostedUrl": "url1", "descriptionPlain": "Python and Java skills required."},
            {"text": "Product Manager", "categories": {"location": "NY"}, "hostedUrl": "url2", "descriptionPlain": "Lead product vision."},
            {"text": "Data Analyst", "categories": {"location": "Remote"}, "hostedUrl": "url3", "descriptionPlain": "Analyze data with Python and SQL."}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        company_id = "testlever"
        keywords = ["Engineer", "Python"]
        result = client.get_postings(company_id, role_keywords=keywords)

        assert len(result) == 2 # Software Engineer (title) and Data Analyst (description)
        assert result[0]["job_title"] == "Software Engineer"
        assert result[1]["job_title"] == "Data Analyst"
        # Check cache key includes sorted keywords
        cache_key = f"{company_id}_Engineer_Python"
        assert cache_key in client.cache

    def test_get_postings_uses_cache(self, client, mock_requests_get):
        company_id = "testlevercache"
        cached_data = [{"job_title": "Cached Job"}]
        cache_key = f"{company_id}_"
        client.cache[cache_key] = {"timestamp": time.time() - 10, "data": cached_data}

        result = client.get_postings(company_id)
        assert result == cached_data
        mock_requests_get.assert_not_called() # Should not make HTTP call

    def test_get_postings_cache_expired(self, client, mock_requests_get):
        company_id = "testlevercache_exp"
        cached_data = [{"job_title": "Old Cached Job"}]
        cache_key = f"{company_id}_"
        client.cache_expiry_seconds = 1 # Set short expiry
        client.cache[cache_key] = {"timestamp": time.time() - 10, "data": cached_data} # Expired entry

        # Setup mock response for new API call
        mock_api_response = MagicMock()
        new_job_data = [{"text": "New Job From API", "categories": {}, "hostedUrl": "new_url"}]
        mock_api_response.json.return_value = new_job_data
        mock_api_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_api_response

        result = client.get_postings(company_id)
        
        mock_requests_get.assert_called_once() # Should make HTTP call
        assert len(result) == 1
        assert result[0]["job_title"] == "New Job From API"
        assert client.cache[cache_key]["data"] == result # New data in cache

    def test_get_postings_request_exception(self, client, mock_requests_get):
        mock_requests_get.side_effect = requests.exceptions.RequestException("Network Error")
        result = client.get_postings("test_error_co")
        assert result == []
        # Optionally check logger call

    def test_get_postings_json_decode_error(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Bad JSON") # Simulates JSONDecodeError
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        result = client.get_postings("test_json_error_co")
        assert result == []
        # Optionally check logger call

    def test_get_postings_skips_non_dict_item(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"text": "Valid Job", "categories": {}, "hostedUrl": "url1"},
            "this is not a dictionary", # Invalid item
            {"text": "Another Valid Job", "categories": {}, "hostedUrl": "url2"}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        result = client.get_postings("test_mixed_data")
        assert len(result) == 2
        assert result[0]["job_title"] == "Valid Job"
        assert result[1]["job_title"] == "Another Valid Job"

# --- Tests for get_postings will go here --- 