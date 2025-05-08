import pytest
import time
from unittest.mock import MagicMock, patch
import requests # Needed for exception testing

# Assuming GreenhouseClient is importable
# Add path adjustment if necessary
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.api_integration.greenhouse_client import GreenhouseClient, DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS
# Need a mock for ConfigManager
from src.config.config_manager import ConfigManager

@pytest.fixture
def mock_config_manager():
    """Fixture for a mocked ConfigManager."""
    mock_cm = MagicMock(spec=ConfigManager)
    # Explicitly make get_config a MagicMock and set its default side_effect
    mock_cm.get_config = MagicMock(side_effect=lambda key, default=None: default)
    return mock_cm

class TestGreenhouseClientInitialization:
    def test_initialization_default_expiry(self, mock_config_manager):
        client = GreenhouseClient(config_manager=mock_config_manager)
        assert client.cache_expiry_seconds == DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS
        mock_config_manager.get_config.assert_called_once_with(
            "GREENHOUSE_CACHE_EXPIRY_SECONDS", 
            DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS
        )

    def test_initialization_custom_expiry(self, mock_config_manager):
        def custom_expiry_side_effect(key, default=None):
            return 7200 if key == "GREENHOUSE_CACHE_EXPIRY_SECONDS" else default
        mock_config_manager.get_config.side_effect = custom_expiry_side_effect
        client = GreenhouseClient(config_manager=mock_config_manager)
        assert client.cache_expiry_seconds == 7200

    def test_initialization_invalid_expiry_string(self, mock_config_manager):
        def invalid_expiry_side_effect(key, default=None):
            return "not_a_number" if key == "GREENHOUSE_CACHE_EXPIRY_SECONDS" else default
        mock_config_manager.get_config.side_effect = invalid_expiry_side_effect
        client = GreenhouseClient(config_manager=mock_config_manager)
        assert client.cache_expiry_seconds == DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS

class TestGreenhouseClientCacheLogic:
    @pytest.fixture
    def client(self, mock_config_manager):
        # Reset cache for each test
        client = GreenhouseClient(config_manager=mock_config_manager)
        client.cache = {}
        return client

    def test_is_cache_valid_true(self, client):
        entry = {"timestamp": time.time() - 100, "data": [{"id": 1}] }
        assert client._is_cache_valid(entry) is True

    def test_is_cache_valid_false_expired(self, client):
        client.cache_expiry_seconds = 500
        entry = {"timestamp": time.time() - 1000, "data": [{"id": 1}]}
        assert client._is_cache_valid(entry) is False

    # _is_cache_valid tests for missing keys are same as Lever, skipping for brevity

    def test_clear_cache_all(self, client):
        client.cache["token1_kw1_True"] = {"timestamp": time.time(), "data": []}
        client.cache["token2__True"] = {"timestamp": time.time(), "data": []}
        client.clear_cache()
        assert not client.cache

    def test_clear_cache_specific_token(self, client):
        # Keys can vary based on keywords and content flag
        client.cache["token1_kw1_True"] = {"timestamp": time.time(), "data": [1]}
        client.cache["token1_kw2_kw1_True"] = {"timestamp": time.time(), "data": [1,2]}
        client.cache["token1__False"] = {"timestamp": time.time(), "data": [3]} # Different content flag
        client.cache["token2__True"] = {"timestamp": time.time(), "data": [4]} # Different token
        
        client.clear_cache("token1")
        
        assert "token1_kw1_True" not in client.cache
        assert "token1_kw2_kw1_True" not in client.cache
        assert "token1__False" not in client.cache
        assert "token2__True" in client.cache # Ensure other token's cache remains
        assert client.cache["token2__True"]["data"] == [4]

    def test_clear_cache_specific_token_not_found(self, client):
        client.cache["token1_kw1_True"] = {"timestamp": time.time(), "data": [1]}
        # Should not raise an error
        client.clear_cache("non_existent_token")
        assert "token1_kw1_True" in client.cache # Ensure other entry is untouched 

class TestGreenhouseClientGetPostings:
    @pytest.fixture
    def client(self, mock_config_manager):
        client = GreenhouseClient(config_manager=mock_config_manager)
        client.cache = {} # Ensure clean cache for each test
        return client

    @pytest.fixture
    def mock_requests_get(self, mocker):
        return mocker.patch('src.api_integration.greenhouse_client.requests.get')

    def test_get_postings_missing_board_token(self, client):
        result = client.get_postings(board_token="")
        assert result == []

    def test_get_postings_success_no_keywords_with_content(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_job1 = {"id": 1, "title": "Engineer", "absolute_url": "url1", "location": {"name": "SF"}, "content": "<p>Code stuff</p>"}
        mock_job2 = {"id": 2, "title": "Manager", "absolute_url": "url2", "location": {"name": "NY"}, "content": "<p>Manage stuff</p>"}
        mock_response.json.return_value = {"jobs": [mock_job1, mock_job2]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        board_token = "test_co"
        result = client.get_postings(board_token, content=True)

        expected_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        mock_requests_get.assert_called_once_with(expected_url, timeout=15)
        assert len(result) == 2
        assert result[0]["job_id"] == 1
        assert result[0]["job_title"] == "Engineer"
        assert result[0]["source_api"] == "Greenhouse"
        assert result[0]["job_description_snippet"].startswith("<p>Code stuff</p>") # Basic check
        assert result[1]["job_id"] == 2
        # Check cache
        cache_key = f"{board_token}__True" # No keywords, content=True
        assert cache_key in client.cache
        assert client.cache[cache_key]["data"] == result

    def test_get_postings_success_no_keywords_no_content(self, client, mock_requests_get):
        # API response when content=False might not include 'content' field
        mock_response = MagicMock()
        mock_job1 = {"id": 1, "title": "Engineer", "absolute_url": "url1", "location": {"name": "SF"}}
        mock_response.json.return_value = {"jobs": [mock_job1]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        board_token = "test_co_nocontent"
        result = client.get_postings(board_token, content=False)

        expected_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
        mock_requests_get.assert_called_once_with(expected_url, timeout=15)
        assert len(result) == 1
        assert result[0]["job_id"] == 1
        assert result[0]["job_description_snippet"] == "" # No content requested
        # Check cache
        cache_key = f"{board_token}__False" # No keywords, content=False
        assert cache_key in client.cache
        assert client.cache[cache_key]["data"] == result

    def test_get_postings_success_with_keywords(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_job1 = {"id": 1, "title": "Software Engineer", "absolute_url": "url1", "location": {"name": "SF"}, "content": "<p>Backend Python work</p>"}
        mock_job2 = {"id": 2, "title": "Product Manager", "absolute_url": "url2", "location": {"name": "NY"}, "content": "<p>Lead product</p>"}
        mock_job3 = {"id": 3, "title": "Data Scientist", "absolute_url": "url3", "location": {"name": "Remote"}, "content": "<p>Python and ML</p>"}
        mock_response.json.return_value = {"jobs": [mock_job1, mock_job2, mock_job3]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        
        board_token = "test_co_kw"
        keywords = ["Engineer", "Python"]
        result = client.get_postings(board_token, role_keywords=keywords, content=True)

        assert len(result) == 2 # Engineer (title), Data Scientist (content)
        assert result[0]["job_id"] == 1
        assert result[1]["job_id"] == 3
        # Check cache key includes sorted keywords and content flag
        cache_key = f"{board_token}_Engineer_Python_True"
        assert cache_key in client.cache

    def test_get_postings_uses_cache(self, client, mock_requests_get):
        board_token = "test_gh_cache"
        keywords = ["DevOps"]
        content = True
        cached_data = [{"job_title": "Cached GH Job"}]
        cache_key = f"{board_token}_DevOps_True"
        client.cache[cache_key] = {"timestamp": time.time() - 10, "data": cached_data}

        result = client.get_postings(board_token, role_keywords=keywords, content=content)
        assert result == cached_data
        mock_requests_get.assert_not_called() # Should not make HTTP call

    def test_get_postings_cache_expired(self, client, mock_requests_get):
        board_token = "test_gh_cache_exp"
        keywords = ["Analyst"]
        content = True
        cached_data = [{"job_title": "Old Cached GH Job"}]
        cache_key = f"{board_token}_Analyst_True"
        client.cache_expiry_seconds = 1 # Short expiry
        client.cache[cache_key] = {"timestamp": time.time() - 10, "data": cached_data}
        
        # Mock new API response
        mock_api_response = MagicMock()
        new_job_data = [{"id": 10, "title": "New Analyst Job", "absolute_url": "url_new", "location": {"name": "Remote"}, "content": "..."}]
        mock_api_response.json.return_value = {"jobs": new_job_data}
        mock_api_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_api_response
        
        result = client.get_postings(board_token, role_keywords=keywords, content=content)
        
        mock_requests_get.assert_called_once()
        assert len(result) == 1
        assert result[0]["job_title"] == "New Analyst Job"
        assert client.cache[cache_key]["data"] == result # New data cached

    def test_get_postings_request_exception(self, client, mock_requests_get):
        mock_requests_get.side_effect = requests.exceptions.RequestException("GH Network Error")
        result = client.get_postings("test_error_token")
        assert result == []

    def test_get_postings_json_decode_error(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("GH Bad JSON")
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        result = client.get_postings("test_json_error_token")
        assert result == []
        
    def test_get_postings_api_returns_no_jobs_key(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected_key": []} # Missing 'jobs' key
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        result = client.get_postings("test_no_jobs_key")
        assert result == []
        
    def test_get_postings_api_returns_non_list_for_jobs(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"jobs": "this should be a list"}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        result = client.get_postings("test_jobs_not_list")
        assert result == []

    def test_get_postings_skips_non_dict_item_in_jobs_list(self, client, mock_requests_get):
        mock_response = MagicMock()
        mock_job1 = {"id": 1, "title": "Valid Job 1", "absolute_url": "url1"}
        mock_job2 = {"id": 2, "title": "Valid Job 2", "absolute_url": "url2"}
        mock_response.json.return_value = {"jobs": [mock_job1, None, mock_job2, "invalid"]}
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response
        result = client.get_postings("test_mixed_items")
        assert len(result) == 2
        assert result[0]["job_id"] == 1
        assert result[1]["job_id"] == 2 