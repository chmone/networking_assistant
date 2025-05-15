import pytest
import requests
from unittest.mock import MagicMock, patch, call
import re # Import re
import logging

# Path adjustment
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.data_acquisition.linkedin_scraper import LinkedInScraper, ChromeDriverManager, webdriver, ChromeService, ChromeOptions
from src.config.config_manager import ConfigManager # For spec
# Use module import for exceptions
import core.exceptions 
import serpapi # For mocking serpapi.Client and SerpApiError

# --- Fixtures --- 

@pytest.fixture
def mock_config_manager_with_key():
    mock = MagicMock(spec=ConfigManager)
    # Mock get_config for SERPAPI_API_KEY and USER_AGENT
    def get_config_side_effect(key, default=None):
        if key == 'SERPAPI_API_KEY':
            return "test_serpapi_key"
        elif key == 'USER_AGENT':
            return "test_user_agent"
        elif key == 'PM_KEYWORDS':
            return ["Product Manager", "PM"]
        elif key == 'TARGET_SCHOOLS':
            return ["Test University", "Another School"]
        return default
    mock.get_config = MagicMock(side_effect=get_config_side_effect)
    # Keep direct attribute for older tests if they haven't been updated yet, though ideally they should use get_config
    mock.scraping_api_key = "test_serpapi_key" 
    return mock

@pytest.fixture
def mock_config_manager_no_key():
    mock = MagicMock(spec=ConfigManager)
    def get_config_side_effect(key, default=None):
        if key == 'SERPAPI_API_KEY':
            return None
        elif key == 'USER_AGENT':
            return "test_user_agent_no_key"
        elif key == 'PM_KEYWORDS':
            return ["Product Manager", "PM"]
        elif key == 'TARGET_SCHOOLS':
            return ["Test University", "Another School"]
        return default
    mock.get_config = MagicMock(side_effect=get_config_side_effect)
    mock.scraping_api_key = None
    return mock

@pytest.fixture
def mock_serpapi_client(mocker):
    # This will mock the serpapi.Client class itself
    mock_client_class = mocker.patch('src.data_acquisition.linkedin_scraper.serpapi.Client')
    # When LinkedInScraper creates an instance, it will get this mock_client_instance
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance
    return mock_client_instance # Return the instance for asserting calls

# --- Test Class --- 

class TestLinkedInScraperInitialization:
    def test_init_with_api_key_and_client(self, mock_config_manager_with_key, mocker):
        # Patch serpapi.Client specifically for this test to see it being called
        mock_client_constructor = mocker.patch('src.data_acquisition.linkedin_scraper.serpapi.Client')
        mock_client_instance = MagicMock()
        mock_client_constructor.return_value = mock_client_instance

        scraper = LinkedInScraper(config_manager=mock_config_manager_with_key)
        
        assert scraper.api_key == "test_serpapi_key"
        mock_client_constructor.assert_called_once_with(api_key="test_serpapi_key")
        assert scraper.serpapi_client is mock_client_instance

    def test_init_without_api_key_no_client(self, mock_config_manager_no_key, caplog, mocker):
        mock_client_constructor = mocker.patch('src.data_acquisition.linkedin_scraper.serpapi.Client')
        
        scraper = LinkedInScraper(config_manager=mock_config_manager_no_key)
        
        assert scraper.api_key is None
        mock_client_constructor.assert_not_called() # Client should not be initialized
        assert scraper.serpapi_client is None
        assert "SERPAPI_API_KEY not found in configuration" in caplog.text

    def test_init_webdriver_attributes(self, mock_config_manager_with_key):
        scraper = LinkedInScraper(config_manager=mock_config_manager_with_key)
        assert scraper.driver is None


class TestLinkedInScraperMakeSerpApiSearch: # Renamed from TestLinkedInScraperMakeApiRequest
    @pytest.fixture
    def scraper_with_client(self, mock_config_manager_with_key, mock_serpapi_client):
        # mock_serpapi_client fixture already patches serpapi.Client construction
        # So, LinkedInScraper will get the mocked client instance.
        scraper = LinkedInScraper(config_manager=mock_config_manager_with_key)
        # The mock_serpapi_client fixture ensures scraper.serpapi_client is the MagicMock instance
        return scraper, mock_serpapi_client # Return client for assertions

    @pytest.fixture
    def scraper_no_client(self, mock_config_manager_no_key):
        # This will initialize LinkedInScraper with no API key, so serpapi_client will be None
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_make_search_success(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        expected_results = {"search_metadata": {"status": "success"}}
        client_mock.search.return_value = expected_results # Mock the search method of the client instance
        
        params = {"q": "test", "engine": "google"} # engine is now important
        result = scraper._make_serpapi_search(params, "test success")
        
        client_mock.search.assert_called_once_with(params)
        assert result == expected_results

    def test_make_search_api_error_in_response(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        error_response = {"error": "Something went wrong on SerpApi side."}
        client_mock.search.return_value = error_response
        
        params = {"q": "test_api_error", "engine": "google"}
        with pytest.raises(core.exceptions.DataAcquisitionError, match="SerpApi Error: Something went wrong"):
            scraper._make_serpapi_search(params, "test api error in response")
        assert client_mock.search.call_count == 4
        client_mock.search.assert_any_call(params)

    def test_make_search_api_auth_error_in_response(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        auth_error_response = {"error": "Authorization invalid for this request."}
        client_mock.search.return_value = auth_error_response
        params = {"q": "test_auth_error", "engine": "google"}
        with pytest.raises(core.exceptions.ApiAuthError, match="SerpApi Authentication Error: Authorization invalid"):
            scraper._make_serpapi_search(params, "test auth error in response")

    def test_make_search_api_limit_error_in_response(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        limit_error_response = {"error": "Your account has reached its monthly rate limit."}
        client_mock.search.return_value = limit_error_response
        params = {"q": "test_limit_error", "engine": "google"}
        with pytest.raises(core.exceptions.ApiLimitError, match="SerpApi Rate Limit Error: Your account has reached its monthly rate limit"):
            scraper._make_serpapi_search(params, "test limit error in response")

    def test_make_search_serpapi_library_error(self, scraper_with_client, mocker):
        scraper, client_mock = scraper_with_client
        # Mock serpapi.SerpApiError for this specific test
        # Need to import `serpapi` in the test file to reference serpapi.SerpApiError
        client_mock.search.side_effect = serpapi.SerpApiError("Library-level SerpApi issue")
        
        params = {"q": "test_library_error", "engine": "google"}
        with pytest.raises(core.exceptions.DataAcquisitionError, match="SerpApi library error during test library error"):
            scraper._make_serpapi_search(params, "test library error")
        assert client_mock.search.call_count == 4
        client_mock.search.assert_any_call(params)

    def test_make_search_serpapi_library_auth_error(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        client_mock.search.side_effect = serpapi.SerpApiError("Invalid API key.") # Example auth error message
        params = {"q": "lib_auth_err", "engine": "google"}
        with pytest.raises(core.exceptions.ApiAuthError, match="SerpApi Auth/Config Error: Invalid API key."):
            scraper._make_serpapi_search(params, "test serpapi lib auth error")
    
    def test_make_search_serpapi_library_limit_error(self, scraper_with_client):
        scraper, client_mock = scraper_with_client
        client_mock.search.side_effect = serpapi.SerpApiError("Monthly rate limit reached.") # Example limit message
        params = {"q": "lib_limit_err", "engine": "google"}
        with pytest.raises(core.exceptions.ApiLimitError, match="SerpApi Rate Limit Error: Monthly rate limit reached."):
            scraper._make_serpapi_search(params, "test serpapi lib limit error")

    def test_make_search_no_client_initialized(self, scraper_no_client):
        params = {"q": "test_no_client", "engine": "google"}
        with pytest.raises(core.exceptions.ApiAuthError, match="SerpApi client not initialized"):
            scraper_no_client._make_serpapi_search(params, "test no client")

    def test_make_search_defaults_engine_to_google(self, scraper_with_client, caplog):
        scraper, client_mock = scraper_with_client
        expected_results = {"search_metadata": {"status": "success"}}
        client_mock.search.return_value = expected_results
        
        params_no_engine = {"q": "test_no_engine"}
        scraper._make_serpapi_search(params_no_engine, "test no engine default")
        
        # Assert that the call to client_mock.search included 'engine': 'google'
        args, _ = client_mock.search.call_args
        assert args[0]['engine'] == 'google'
        assert "'engine' not specified for SerpApi search: test no engine default. Defaulting to 'google'." in caplog.text

# --- TestLinkedInScraperTestApiConnection --- (Needs to use the new search method)
class TestLinkedInScraperTestApiConnection:
    # scraper fixtures will now use the mocked client if mock_serpapi_client is active
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key, mock_serpapi_client): 
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_api_connection_success(self, scraper, mocker):
        # scraper.serpapi_client is already the mock_serpapi_client instance
        mock_search_response = {"search_metadata": {"id": "test_search_id", "status": "Success"}}
        scraper.serpapi_client.search.return_value = mock_search_response # Mock the search method

        result = scraper.test_api_connection("Test Query")
        
        expected_params = {"engine": "google", "q": "Test Query", "num": "1"}
        scraper.serpapi_client.search.assert_called_once_with(expected_params)
        assert result == {"status": "success", "data": mock_search_response['search_metadata']}

    def test_api_connection_no_api_key_no_client(self, scraper_no_key, caplog):
        # scraper_no_key.serpapi_client will be None
        result = scraper_no_key.test_api_connection()
        assert result == {"status": "error", "message": "SerpApi client not initialized."}
        assert "SerpApi client not initialized" in caplog.text

    def test_api_connection_api_error_response(self, scraper, mocker):
        scraper.serpapi_client.search.return_value = {"error": "API side error during test."}
        result = scraper.test_api_connection("Test Error Query")
        # The error from _make_serpapi_search will be caught by test_api_connection's own try-except
        assert result["status"] == "error"
        assert "SerpApi Error: API side error during test." in result["message"]

    def test_api_connection_serpapi_lib_exception(self, scraper, mocker):
        scraper.serpapi_client.search.side_effect = serpapi.SerpApiError("Test SerpApiLib Exception")
        result = scraper.test_api_connection("Test Lib Exc Query")
        assert result["status"] == "error"
        assert "SerpApi library error during SerpApi connection test" in result["message"]
        assert "Test SerpApiLib Exception" in result["message"] # Check original exception text is there


# --- TestLinkedInScraperScrapeAlumni & TestLinkedInScraperScrapePMs ---
# These need to be updated to mock _make_serpapi_search or ensure serpapi_client.search is mocked correctly

class TestLinkedInScraperScrapeAlumni:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key, mock_serpapi_client):
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)
    
    def test_scrape_alumni_no_api_key_no_client(self, scraper_no_key, caplog):
        # _make_serpapi_search will not be called as client is None
        results = scraper_no_key.scrape_alumni_by_school("Test School")
        assert results == []
        assert "SerpApi client not initialized. Cannot scrape alumni." in caplog.text

    def test_scrape_alumni_success(self, scraper, mocker):
        # scraper.serpapi_client.search will be called by _make_serpapi_search
        mock_api_response = {"organic_results": [{"title": "Alumni 1"}]}
        scraper.serpapi_client.search.return_value = mock_api_response # Mock client's search
        
        # We can still mock _parse_linkedin_results if we want to isolate its testing
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        expected_parsed_leads = [{"name": "Alumni 1 Lead"}]
        mock_parse_results.return_value = expected_parsed_leads

        results = scraper.scrape_alumni_by_school("Test University", max_results=50)

        expected_query = '"Test University" site:linkedin.com/in/'
        expected_params = {
            "engine": "google", "q": expected_query,
            "num": "50", "gl": "us", "hl": "en"
        } # No api_key here as client handles it
        scraper.serpapi_client.search.assert_called_once_with(expected_params)
        mock_parse_results.assert_called_once_with(mock_api_response, source="Alumni Search: Test University")
        assert results == expected_parsed_leads

    def test_scrape_alumni_data_acquisition_error(self, scraper, mocker):
        scraper.serpapi_client.search.side_effect = core.exceptions.DataAcquisitionError("Simulated API failure")
        # Patch _parse_linkedin_results as it won't be called if _make_serpapi_search fails
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')

        results = scraper.scrape_alumni_by_school("Fail School")
        assert results == []
        mock_parse_results.assert_not_called()
        # Check logs for "Data acquisition failed..."


class TestLinkedInScraperScrapePMs:
    @pytest.fixture
    def mock_config_for_pm_tests(self, mock_config_manager_with_key):
        return mock_config_manager_with_key

    @pytest.fixture
    def scraper(self, mock_config_for_pm_tests, mock_serpapi_client):
        return LinkedInScraper(config_manager=mock_config_for_pm_tests)

    @pytest.fixture
    def scraper_no_key(self, mock_config_manager_no_key):
        return LinkedInScraper(config_manager=mock_config_manager_no_key)

    def test_scrape_pms_no_api_key_no_client(self, scraper_no_key, caplog):
        results = scraper_no_key.scrape_pms_by_location("Test Location")
        assert results == []
        assert "SerpApi client not initialized. Cannot scrape PMs." in caplog.text

    def test_scrape_pms_success_default_keywords(self, scraper, mocker):
        mock_api_response = {"organic_results": [{"title": "PM 1"}]}
        scraper.serpapi_client.search.return_value = mock_api_response
        
        mock_parse_results = mocker.patch.object(scraper, '_parse_linkedin_results')
        expected_parsed_leads = [{"name": "PM 1 Lead"}]
        mock_parse_results.return_value = expected_parsed_leads

        keyword_string = '"Product Manager" OR "PM"' # From mock_config
        expected_query = f'({keyword_string}) "Test Location" site:linkedin.com/in/'
        
        results = scraper.scrape_pms_by_location("Test Location", max_results=30)

        expected_params = {
            "engine": "google", "q": expected_query,
            "num": "30", "gl": "us", "hl": "en"
        }
        scraper.serpapi_client.search.assert_called_once_with(expected_params)
        mock_parse_results.assert_called_once_with(mock_api_response, source="PM Search: Test Location")
        assert results == expected_parsed_leads

# TestLinkedInScraperParseResults should be largely unaffected as it doesn't make API calls directly
# ... (TestLinkedInScraperParseResults remains the same) ...

# TestLinkedInScraperWebDriver and TestLinkedInScraperScrapeUserProfileDetailsWebDriver
# are also unaffected by SerpApi client changes as they test Selenium parts.
# ... (WebDriver tests remain the same) ...

class TestLinkedInScraperParseResults:
    @pytest.fixture 
    def mock_config_for_parsing_tests(self, mock_config_manager_no_key):
        return mock_config_manager_no_key
        
    @pytest.fixture
    def scraper(self, mock_config_for_parsing_tests): 
        return LinkedInScraper(config_manager=mock_config_for_parsing_tests)

    def test_parse_results_basic_extraction(self, scraper):
        data = {
            "organic_results": [
                {
                    "title": "Jane Doe - Product Manager at Innovate Inc.",
                    "link": "https://www.linkedin.com/in/janedoe",
                    "snippet": "Innovate Inc. | New York. Test University Alumnus. Skills: Agile, Product Strategy."
                }
            ]
        }
        leads = scraper._parse_linkedin_results(data, "Test Source")
        assert len(leads) == 1
        lead = leads[0]
        assert lead["lead_name"] == "Jane Doe"
        assert lead["linkedin_profile_url"] == "https://www.linkedin.com/in/janedoe"
        assert lead["current_role"] == "Product Manager"
        assert lead["company_name"] == "Innovate Inc."
        assert lead["location"] == "New York" 
        assert "Test University" in lead["alma_mater_match"]

# WebDriver tests should be fine.
class TestLinkedInScraperWebDriver:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @patch('src.data_acquisition.linkedin_scraper.ChromeDriverManager')
    @patch('src.data_acquisition.linkedin_scraper.webdriver.Chrome')
    @patch('src.data_acquisition.linkedin_scraper.ChromeService')
    def test_setup_driver_success(self, mock_chrome_service, mock_webdriver_chrome, mock_chrome_driver_manager, scraper, caplog):
        # Set log level for the specific logger used in the scraper module
        caplog.set_level(logging.INFO, logger="src.data_acquisition.linkedin_scraper")

        mock_driver_manager_instance = MagicMock()
        mock_chrome_driver_manager.return_value = mock_driver_manager_instance
        mock_driver_manager_instance.install.return_value = "path/to/chromedriver"

        mock_service_instance = MagicMock()
        mock_chrome_service.return_value = mock_service_instance
        
        mock_chrome_instance = MagicMock()
        mock_webdriver_chrome.return_value = mock_chrome_instance

        scraper._setup_driver()

        mock_chrome_driver_manager.assert_called_once()
        mock_driver_manager_instance.install.assert_called_once()
        mock_chrome_service.assert_called_once_with("path/to/chromedriver")
        
        args, kwargs = mock_webdriver_chrome.call_args
        assert 'service' in kwargs
        assert kwargs['service'] is mock_service_instance
        assert 'options' in kwargs
        passed_options = kwargs['options']
        assert any("--headless" in arg for arg in passed_options.arguments)
        assert any("user-agent=test_user_agent" in arg for arg in passed_options.arguments)
        
        assert scraper.driver is mock_chrome_instance
        assert "Selenium WebDriver for Chrome initialized successfully" in caplog.text

    @patch('src.data_acquisition.linkedin_scraper.ChromeDriverManager')
    def test_setup_driver_install_fails(self, mock_chrome_driver_manager, scraper, caplog):
        mock_chrome_driver_manager.return_value.install.side_effect = Exception("Install failed")
        scraper._setup_driver()
        assert scraper.driver is None
        assert "Error initializing Selenium WebDriver: Install failed" in caplog.text

    @patch('src.data_acquisition.linkedin_scraper.ChromeDriverManager')
    @patch('src.data_acquisition.linkedin_scraper.webdriver.Chrome')
    def test_setup_driver_chrome_init_fails(self, mock_webdriver_chrome, mock_chrome_driver_manager, scraper, caplog):
        mock_chrome_driver_manager.return_value.install.return_value = "path/to/chromedriver"
        mock_webdriver_chrome.side_effect = Exception("Chrome init failed")
        scraper._setup_driver()
        assert scraper.driver is None
        assert "Error initializing Selenium WebDriver: Chrome init failed" in caplog.text

    def test_setup_driver_already_initialized(self, scraper, caplog):
        # Set log level for the specific logger used in the scraper module
        caplog.set_level(logging.INFO, logger="src.data_acquisition.linkedin_scraper")

        scraper.driver = MagicMock()
        scraper._setup_driver()
        assert "WebDriver already initialized" in caplog.text
        # scraper.driver.assert_not_called() # This line might cause issues if driver is a MagicMock itself, its methods are not being re-init

    def test_close_driver_success(self, scraper, caplog):
        caplog.set_level(logging.INFO, logger="src.data_acquisition.linkedin_scraper") # Also add for this test
        mock_driver_instance = MagicMock()
        scraper.driver = mock_driver_instance
        
        scraper.close_driver()
        
        mock_driver_instance.quit.assert_called_once() # Assert on the original mock instance
        assert scraper.driver is None
        assert "Selenium WebDriver closed successfully" in caplog.text

    def test_close_driver_quit_fails(self, scraper, caplog):
        mock_driver_instance = MagicMock()
        mock_driver_instance.quit.side_effect = Exception("Quit failed")
        scraper.driver = mock_driver_instance
        scraper.close_driver()
        assert scraper.driver is None
        assert "Error closing Selenium WebDriver: Quit failed" in caplog.text

    def test_close_driver_no_driver(self, scraper, caplog):
        scraper.driver = None
        scraper.close_driver()
        assert "Closing Selenium WebDriver" not in caplog.text

class TestLinkedInScraperScrapeUserProfileDetailsWebDriver:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        return LinkedInScraper(config_manager=mock_config_manager_with_key)

    @patch.object(LinkedInScraper, '_setup_driver')
    def test_scrape_details_calls_setup_driver_if_none(self, mock_setup_driver, scraper):
        scraper.driver = None
        # print(f"DEBUG test: scraper.driver BEFORE patch: {scraper.driver}") # DEBUG REMOVED
        
        # The mock_driver_attr was part of the problem, remove the `with` block that patched scraper.driver
        # We want the scrape_user_profile_details method to see the scraper.driver as None initially.

        # Define a side effect for mock_setup_driver if we need to simulate it setting the driver
        # For this test, we primarily care that it was called.
        # If later parts of scrape_user_profile_details depended on self.driver being set by _setup_driver,
        # we would need mock_setup_driver's side_effect to set scraper.driver.
        mock_created_driver = MagicMock() # A mock for the driver that _setup_driver would create
        def side_effect_for_setup_driver():
            # print("DEBUG test: side_effect_for_setup_driver CALLED") # DEBUG
            scraper.driver = mock_created_driver # Simulate _setup_driver setting the driver instance
            # print(f"DEBUG test: scraper.driver AFTER side_effect assignment: {scraper.driver}") # DEBUG

        mock_setup_driver.side_effect = side_effect_for_setup_driver
        
        scraper.scrape_user_profile_details("http://linkedin.com/in/test")
        
        # print(f"DEBUG test: mock_setup_driver call count: {mock_setup_driver.call_count}") # DEBUG REMOVED
        mock_setup_driver.assert_called_once()

    @patch.object(LinkedInScraper, '_setup_driver')
    def test_scrape_details_returns_error_if_setup_fails(self, mock_setup_driver, scraper, caplog):
        def failing_setup():
            scraper.driver = None 
        mock_setup_driver.side_effect = failing_setup
        result = scraper.scrape_user_profile_details("http://linkedin.com/in/test")
        mock_setup_driver.assert_called_once()
        assert result["error"] == "WebDriver initialization failed."
        assert "WebDriver not available. Cannot scrape user profile." in caplog.text

    @patch.object(LinkedInScraper, '_setup_driver') 
    def test_scrape_details_success_stub_behavior(self, mock_setup_driver, scraper):
        mock_actual_driver = MagicMock()
        def successful_setup():
            scraper.driver = mock_actual_driver 
        mock_setup_driver.side_effect = successful_setup
        test_url = "http://linkedin.com/in/testprofile"
        result = scraper.scrape_user_profile_details(test_url)
        mock_setup_driver.assert_called_once()
        assert result["linkedin_url"] == test_url
        assert result["full_name"] == "John Doe (Stub)"
        mock_actual_driver.get.assert_not_called()
