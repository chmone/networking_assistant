import pytest
import requests
from unittest.mock import MagicMock, patch, call
import requests
import re # Import re

# Path adjustment
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data_acquisition.linkedin_scraper import LinkedInScraper
from src.config.config_manager import ConfigManager # For spec
# Use module import for exceptions
import core.exceptions 
# from core.exceptions import ApiAuthError, ApiLimitError, DataAcquisitionError # REMOVE direct import

# --- Fixtures --- 

@pytest.fixture
def mock_config_manager_with_key():
    mock = MagicMock(spec=ConfigManager)
    # Provide the specific attribute the scraper uses
    mock.scraping_api_key = "test_linkedin_key"
    # Mock get_config just in case it's used elsewhere, though scraper uses attribute directly
    mock.get_config = MagicMock(side_effect=lambda key, default=None: default if key != 'SCRAPING_API_KEY' else "test_linkedin_key")
    return mock

@pytest.fixture
def mock_config_manager_no_key():
    mock = MagicMock(spec=ConfigManager)
    mock.scraping_api_key = None
    mock.get_config = MagicMock(side_effect=lambda key, default=None: default if key != 'SCRAPING_API_KEY' else None)
    return mock

@pytest.fixture
def mock_requests_get(mocker):
    # Patch requests.get within the linkedin_scraper module context
    return mocker.patch('src.data_acquisition.linkedin_scraper.requests.get')

# --- Test Class --- 

class TestLinkedInScraperInitialization:
    def test_init_with_api_key(self, mock_config_manager_with_key):
        scraper = LinkedInScraper(config_manager=mock_config_manager_with_key)
        assert scraper.api_key == "test_linkedin_key"
        assert scraper.base_url == "https://serpapi.com/search.json"

    def test_init_without_api_key(self, mock_config_manager_no_key):
        scraper = LinkedInScraper(config_manager=mock_config_manager_no_key)
        assert scraper.api_key is None
        # Optionally check logger warning

    def test_init_creates_config_if_none_provided(self, mocker):
        # Mock the ConfigManager constructor called within __init__
        mock_cm_constructor = mocker.patch('src.data_acquisition.linkedin_scraper.ConfigManager')
        mock_cm_instance = MagicMock(spec=ConfigManager)
        mock_cm_instance.scraping_api_key = "key_created_internally"
        mock_cm_constructor.return_value = mock_cm_instance
        
        # Patch os.path.exists used in the internal config creation logic
        mocker.patch('src.data_acquisition.linkedin_scraper.os.path.exists', return_value=True) # Assume .env exists
        
        scraper = LinkedInScraper(config_manager=None) # Pass None
        
        mock_cm_constructor.assert_called_once()
        # Verify the path used if needed (might be complex due to path logic)
        # mock_cm_constructor.assert_called_once_with(env_file_path=...) 
        assert scraper.config is mock_cm_instance
        assert scraper.api_key == "key_created_internally"

class TestLinkedInScraperMakeApiRequest:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    def test_make_request_success(self, scraper, mock_requests_get):
        mock_response = MagicMock()
        expected_json = {"search_metadata": {"status": "success"}}
        mock_response.json.return_value = expected_json
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock() # Mock this so it doesn't raise
        mock_requests_get.return_value = mock_response
        
        params = {"q": "test", "api_key": scraper.api_key}
        result = scraper._make_api_request(params, "test success")
        
        mock_requests_get.assert_called_once_with(scraper.base_url, params=params, timeout=20)
        assert result == expected_json

    def test_make_request_auth_error_401(self, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Auth failed"
        http_error_instance = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error_instance
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test 401")
            pytest.fail("ApiAuthError not raised") 
        except Exception as e: 
            assert isinstance(e, core.exceptions.ApiAuthError), f"Expected ApiAuthError, got {type(e)}"
            assert mock_requests_get.call_count == 1 
            assert "Not retrying authentication errors." in caplog.text
            
    def test_make_request_auth_error_403(self, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        http_error_instance = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error_instance
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test 403")
            pytest.fail("ApiAuthError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.ApiAuthError), f"Expected ApiAuthError, got {type(e)}"
            assert mock_requests_get.call_count == 1 
            assert "Not retrying authentication errors." in caplog.text

    @patch('src.core.retry_utils.time.sleep', return_value=None)
    def test_make_request_client_error_400(self, mock_sleep, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        http_error_instance = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error_instance 
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test 400")
            pytest.fail("DataAcquisitionError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.DataAcquisitionError), f"Expected DataAcquisitionError, got {type(e)}"
            assert mock_requests_get.call_count == 4 
            assert "Max retries (3) reached" in caplog.text

    @patch('src.core.retry_utils.time.sleep', return_value=None)
    def test_make_request_rate_limit_error_429_final(self, mock_sleep, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate Limit Exceeded"
        http_error_instance = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error_instance  
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test 429 final")
            pytest.fail("ApiLimitError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.ApiLimitError), f"Expected ApiLimitError, got {type(e)}"
            assert mock_requests_get.call_count == 4 
            assert "Max retries (3) reached" in caplog.text
             
    @patch('src.core.retry_utils.time.sleep', return_value=None)
    def test_make_request_server_error_500_final(self, mock_sleep, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        http_error_instance = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error_instance  
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test 500 final")
            pytest.fail("DataAcquisitionError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.DataAcquisitionError), f"Expected DataAcquisitionError, got {type(e)}"
            assert mock_requests_get.call_count == 4 
            assert "Max retries (3) reached" in caplog.text

    @patch('src.core.retry_utils.time.sleep', return_value=None)
    def test_make_request_network_error(self, mock_sleep, caplog, scraper, mock_requests_get):
        network_exception = requests.exceptions.RequestException("Connection failed")
        mock_requests_get.side_effect = network_exception
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test network error")
            pytest.fail("DataAcquisitionError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.DataAcquisitionError), f"Expected DataAcquisitionError, got {type(e)}"
            assert isinstance(e.original_exception, requests.exceptions.RequestException)
            assert mock_requests_get.call_count == 4 
            assert "Max retries (3) reached" in caplog.text

    @patch('src.core.retry_utils.time.sleep', return_value=None)
    def test_make_request_json_decode_error(self, mock_sleep, caplog, scraper, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        json_decode_exception = ValueError("Invalid JSON")
        mock_response.json.side_effect = json_decode_exception
        mock_response.text = "<html><body>Error</body></html>"
        mock_requests_get.return_value = mock_response
        params = {"q": "test", "api_key": scraper.api_key}
        try:
            scraper._make_api_request(params, "test json error")
            pytest.fail("DataAcquisitionError not raised")
        except Exception as e:
            assert isinstance(e, core.exceptions.DataAcquisitionError), f"Expected DataAcquisitionError, got {type(e)}"
            assert isinstance(e.original_exception, ValueError)
            # Correct Assertion: Expect 4 calls due to retries
            assert mock_requests_get.call_count == 4 # 1 initial + 3 retries
            assert mock_response.json.call_count == 4 # 1 initial + 3 retries
            assert "Max retries (3) reached" in caplog.text

# --- TODO: Tests for test_api_connection ---
class TestLinkedInScraperTestApiConnection:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        # Needs API key
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_api_connection_success(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        mock_api_response = {"search_metadata": {"id": "123", "status": "Success"}}
        mock_make_request.return_value = mock_api_response

        result = scraper.test_api_connection()

        expected_params = {"engine": "google", "q": "Product Manager New York", "api_key": scraper.api_key, "num": "1"}
        mock_make_request.assert_called_once_with(expected_params, "SerpApi connection test (Google engine)")
        assert result == {"status": "success", "data": mock_api_response['search_metadata']}

    def test_api_connection_no_api_key(self, scraper_no_key, mocker):
        mock_make_request = mocker.patch.object(scraper_no_key, '_make_api_request')
        
        result = scraper_no_key.test_api_connection()
        
        mock_make_request.assert_not_called()
        assert result == {"status": "error", "message": "API key not configured."}

    def test_api_connection_api_error(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        error_message = "Simulated API failure"
        mock_make_request.side_effect = core.exceptions.DataAcquisitionError(error_message, source="SerpApi")

        result = scraper.test_api_connection()

        expected_params = {"engine": "google", "q": "Product Manager New York", "api_key": scraper.api_key, "num": "1"}
        mock_make_request.assert_called_once_with(expected_params, "SerpApi connection test (Google engine)")
        assert result["status"] == "error"
        assert error_message in result["message"]

    def test_api_connection_unexpected_structure(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        mock_api_response = {"unexpected_key": "some_data"} # Missing search_metadata
        mock_make_request.return_value = mock_api_response

        result = scraper.test_api_connection()

        assert result["status"] == "warning"
        assert "Unexpected response structure" in result["message"]
        assert result["data"] == mock_api_response

    def test_api_connection_unexpected_exception(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        error_message = "Completely unexpected error"
        mock_make_request.side_effect = Exception(error_message)

        result = scraper.test_api_connection()

        assert result["status"] == "error"
        assert f"Unexpected error: {error_message}" in result["message"]

# --- TODO: Tests for scrape_alumni_by_school --- 
class TestLinkedInScraperScrapeAlumni:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_scrape_alumni_no_api_key(self, scraper_no_key, mocker):
        mock_make_request = mocker.patch.object(scraper_no_key, '_make_api_request')
        result = scraper_no_key.scrape_alumni_by_school("Some University")
        assert result == []
        mock_make_request.assert_not_called()
        # Optionally check logger error

    def test_scrape_alumni_success(self, scraper, mocker):
        school_name = "Test University"
        mock_api_response = {"organic_results": [
            {"title": "John Doe - Test University", "link": "linkedin.com/in/johndoe", "snippet": "..."}
        ]}
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value=mock_api_response)
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        mock_parse_results.return_value = [{"lead_name": "John Doe"}] # Simulate parsed lead

        result = scraper.scrape_alumni_by_school(school_name, max_results=50)

        expected_query = f'"{school_name}" site:linkedin.com/in/'
        expected_params = {
            "engine": "google", "q": expected_query, "api_key": scraper.api_key,
            "num": "50", "gl": "us", "hl": "en"
        }
        mock_make_request.assert_called_once_with(expected_params, f"alumni search for '{school_name}'")
        mock_parse_results.assert_called_once_with(mock_api_response, source=f"Alumni Search: {school_name}")
        assert result == [{"lead_name": "John Doe"}]

    def test_scrape_alumni_max_results_capped(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value={})
        mocker.patch.object(scraper, '_parse_linkedin_results', return_value=[])
        
        scraper.scrape_alumni_by_school("Another Uni", max_results=200)
        
        call_args = mock_make_request.call_args[0][0] # Get the params dict from the call
        assert call_args['num'] == "100" # Should be capped at 100

    def test_scrape_alumni_api_error(self, scraper, mocker):
        school_name = "Error University"
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        mock_make_request.side_effect = core.exceptions.DataAcquisitionError("API failed")
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')

        result = scraper.scrape_alumni_by_school(school_name)

        assert result == []
        mock_parse_results.assert_not_called()
        # Optionally check logger error

    def test_scrape_alumni_parsing_error(self, scraper, mocker):
        school_name = "Parsing Error University"
        mock_api_response = {"organic_results": []} # Valid API response
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value=mock_api_response)
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        mock_parse_results.side_effect = Exception("Parsing failed") # Simulate error during parsing

        result = scraper.scrape_alumni_by_school(school_name)

        assert result == []
        mock_make_request.assert_called_once() # API call should happen
        mock_parse_results.assert_called_once() # Parsing should be attempted
        # Optionally check logger exception

# --- TODO: Tests for scrape_pms_by_location --- 
class TestLinkedInScraperScrapePMs:
    @pytest.fixture
    def mock_config_manager_with_pm_keywords(self, mock_config_manager_with_key):
        # Add specific PM keywords for this test class
        mock_config_manager_with_key.pm_keywords = ["Product Manager", "Technical Program Manager"]
        return mock_config_manager_with_key

    @pytest.fixture
    def scraper(self, mock_config_manager_with_pm_keywords):
        return LinkedInScraper(config_manager=mock_config_manager_with_pm_keywords)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_scrape_pms_no_api_key(self, scraper_no_key, mocker):
        mock_make_request = mocker.patch.object(scraper_no_key, '_make_api_request')
        result = scraper_no_key.scrape_pms_by_location("San Francisco")
        assert result == []
        mock_make_request.assert_not_called()
        # Optionally check logger error

    def test_scrape_pms_success_default_keywords(self, scraper, mocker):
        location = "New York City"
        mock_api_response = {"organic_results": [
            {"title": "Jane Smith - Product Manager at Google", "link": "linkedin.com/in/janesmith", "snippet": "..."}
        ]}
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value=mock_api_response)
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        mock_parse_results.return_value = [{"lead_name": "Jane Smith"}]

        result = scraper.scrape_pms_by_location(location, max_results=75)

        expected_keywords_str = '"Product Manager" OR "Technical Program Manager"' # From fixture
        expected_query = f'({expected_keywords_str}) "{location}" site:linkedin.com/in/'
        expected_params = {
            "engine": "google", "q": expected_query, "api_key": scraper.api_key,
            "num": "75", "gl": "us", "hl": "en"
        }
        mock_make_request.assert_called_once_with(expected_params, f"PM search in '{location}'")
        mock_parse_results.assert_called_once_with(mock_api_response, source=f"PM Search: {location}")
        assert result == [{"lead_name": "Jane Smith"}]

    def test_scrape_pms_success_custom_keywords(self, scraper, mocker):
        location = "Remote"
        custom_keywords = ["VP Product", "Growth PM"]
        mock_api_response = {"organic_results": []}
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value=mock_api_response)
        mocker.patch.object(scraper, '_parse_linkedin_results', return_value=[]) # Don't care about parsing here

        scraper.scrape_pms_by_location(location, keywords=custom_keywords)

        expected_keywords_str = '"VP Product" OR "Growth PM"'
        expected_query = f'({expected_keywords_str}) "{location}" site:linkedin.com/in/'
        expected_params = {
            "engine": "google", "q": expected_query, "api_key": scraper.api_key,
            "num": "100", "gl": "us", "hl": "en" # Default max_results = 100
        }
        mock_make_request.assert_called_once_with(expected_params, f"PM search in '{location}'")

    def test_scrape_pms_max_results_capped(self, scraper, mocker):
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value={})
        mocker.patch.object(scraper, '_parse_linkedin_results', return_value=[])
        
        scraper.scrape_pms_by_location("London", max_results=150)
        
        call_args = mock_make_request.call_args[0][0]
        assert call_args['num'] == "100" # Capped

    def test_scrape_pms_api_error(self, scraper, mocker):
        location = "Berlin"
        mock_make_request = mocker.patch.object(scraper, '_make_api_request')
        mock_make_request.side_effect = core.exceptions.DataAcquisitionError("API failed")
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')

        result = scraper.scrape_pms_by_location(location)

        assert result == []
        mock_parse_results.assert_not_called()

    def test_scrape_pms_parsing_error(self, scraper, mocker):
        location = "Tokyo"
        mock_api_response = {"organic_results": [{}]} # Valid API response
        mock_make_request = mocker.patch.object(scraper, '_make_api_request', return_value=mock_api_response)
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        mock_parse_results.side_effect = Exception("Parsing failed badly")

        result = scraper.scrape_pms_by_location(location)

        assert result == []
        mock_make_request.assert_called_once() 
        mock_parse_results.assert_called_once() 


# --- TODO: Tests for _parse_linkedin_results --- 
from datetime import datetime # Need datetime for date_added assertion

class TestLinkedInScraperParseResults:

    @pytest.fixture
    def mock_config_with_schools(self, mock_config_manager_no_key):
        # Use no_key fixture as API key isn't needed for parsing
        # Add target schools for testing alma_mater_match
        mock_config_manager_no_key.target_schools = ["Test University", "Tech Institute"]
        return mock_config_manager_no_key

    @pytest.fixture
    def scraper(self, mock_config_with_schools):
        return LinkedInScraper(config_manager=mock_config_with_schools)

    def test_parse_results_no_organic(self, scraper):
        data = {"search_metadata": {"status": "Success"}} # No organic_results key
        result = scraper._parse_linkedin_results(data, source="Test No Organic")
        assert result == []

    def test_parse_results_empty_organic(self, scraper):
        data = {"organic_results": []}
        result = scraper._parse_linkedin_results(data, source="Test Empty Organic")
        assert result == []

    def test_parse_results_invalid_item_no_link(self, scraper):
        data = {"organic_results": [
            {"title": "Valid Person", "link": "linkedin.com/in/valid"},
            {"title": "Invalid Person - No Link"}
        ]}
        result = scraper._parse_linkedin_results(data, source="Test Invalid Item")
        assert len(result) == 1
        assert result[0]["lead_name"] == "Valid Person"

    def test_parse_results_basic_extraction(self, scraper):
        data = {"organic_results": [
            {
                "title": "Alice Example - Software Engineer at Globex Corp",
                "link": "https://www.linkedin.com/in/aliceexample",
                "snippet": "Greater New York City Area · 500+ connections · Software Engineer at Globex Corp. Test University."
            }
        ]}
        result = scraper._parse_linkedin_results(data, source="Test Basic")
        
        assert len(result) == 1
        lead = result[0]
        assert lead["lead_name"] == "Alice Example"
        assert lead["linkedin_profile_url"] == "https://www.linkedin.com/in/aliceexample"
        assert lead["current_role"] == "Software Engineer"
        assert lead["company_name"] == "Globex Corp"
        assert lead["location"] == "Greater New York City Area" 
        assert "Test University" in lead["alma_mater_match"]
        assert lead["source_of_lead"] == "Test Basic"
        assert "date_added" in lead
        # Check date format loosely
        assert len(lead["date_added"]) > 10 
        assert lead["raw_snippet"] == data["organic_results"][0]["snippet"]

    def test_parse_results_different_title_formats(self, scraper):
        data = {"organic_results": [
            {"title": "Bob Simple | LinkedIn", "link": "linkedin.com/in/bob", "snippet": "Lead Dev at Startup Inc. Location: SF"},
            {"title": "Charlie Complex - VP Engineering - Tech Giant", "link": "linkedin.com/in/charlie", "snippet": "Tech Institute alum"}
        ]}
        result = scraper._parse_linkedin_results(data, source="Test Title Formats")
        
        assert len(result) == 2
        bob = next(l for l in result if l["lead_name"] == "Bob Simple")
        charlie = next(l for l in result if l["lead_name"] == "Charlie Complex")

        assert bob["current_role"] == "Lead Dev"
        assert bob["company_name"] == "Startup Inc"
        assert bob["location"] == "SF"

        assert charlie["current_role"] == "VP Engineering"
        assert charlie["company_name"] == "Tech Giant"
        assert "Tech Institute" in charlie["alma_mater_match"]

    def test_parse_results_no_role_company_in_title(self, scraper):
        data = {"organic_results": [
            {
                "title": "Diana Minimal", 
                "link": "linkedin.com/in/diana", 
                "snippet": "CEO at FutureWorks. Location: Remote · Test University"
            }
        ]}
        result = scraper._parse_linkedin_results(data, source="Test Minimal Title")
        assert len(result) == 1
        lead = result[0]
        assert lead["lead_name"] == "Diana Minimal"
        assert lead["current_role"] == "CEO"
        assert lead["company_name"] == "FutureWorks"
        assert lead["location"] == "Remote"
        assert "Test University" in lead["alma_mater_match"]

    def test_parse_results_no_location_in_snippet(self, scraper):
         data = {"organic_results": [
            {"title": "Eve NoLoc - Freelancer", "link": "linkedin.com/in/eve", "snippet": "Doing cool things."}
        ]}
         result = scraper._parse_linkedin_results(data, source="Test No Location")
         assert len(result) == 1
         assert result[0]["location"] == "" 

    def test_parse_multiple_schools(self, scraper):
         data = {"organic_results": [
            {"title": "Frank Multi - Analyst", "link": "linkedin.com/in/frank", "snippet": "Graduated from Test University and Tech Institute"}
        ]}
         result = scraper._parse_linkedin_results(data, source="Test Multi School")
         assert len(result) == 1
         assert "Test University" in result[0]["alma_mater_match"]
         assert "Tech Institute" in result[0]["alma_mater_match"]
         assert len(result[0]["alma_mater_match"]) == 2

    def test_parse_no_school_match(self, scraper):
        data = {"organic_results": [
            {"title": "Grace NoSchool", "link": "linkedin.com/in/grace", "snippet": "Went to Other University"}
        ]}
        result = scraper._parse_linkedin_results(data, source="Test No School")
        assert len(result) == 1
        assert result[0]["alma_mater_match"] == []
