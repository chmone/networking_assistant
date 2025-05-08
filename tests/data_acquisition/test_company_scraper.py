import pytest
from unittest.mock import MagicMock, patch, call
import serpapi # Import for exception mocking if needed
import time # Import time for cache tests

# Correct path adjustment assuming tests/data_acquisition
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Corrected import for CompanyScraper
from src.data_acquisition.company_scraper import CompanyScraper 
from src.config.config_manager import ConfigManager # For spec

# --- Fixtures --- 

@pytest.fixture
def mock_config_manager_with_key():
    mock = MagicMock(spec=ConfigManager)
    mock.scraping_api_key = "test_api_key"
    # Explicitly mock get_config method
    mock.get_config = MagicMock(side_effect=lambda key, default=None: default if key != "SCRAPING_API_KEY" else "test_api_key")
    return mock

@pytest.fixture
def mock_config_manager_no_key():
    mock = MagicMock(spec=ConfigManager)
    mock.scraping_api_key = None
    # Explicitly mock get_config method
    mock.get_config = MagicMock(side_effect=lambda key, default=None: default if key != "SCRAPING_API_KEY" else None)
    return mock

@pytest.fixture
def mock_serpapi_client(mocker):
    # Patch the serpapi.Client class within the correct module context
    mock_client_instance = MagicMock()
    mocker.patch('src.data_acquisition.company_scraper.serpapi.Client', return_value=mock_client_instance)
    return mock_client_instance

# --- Test Class --- 

class TestCompanyScraperInitialization:
    def test_init_with_api_key(self, mock_config_manager_with_key, mocker):
        # Patch the client creation during init within correct module
        mock_client_constructor = mocker.patch('src.data_acquisition.company_scraper.serpapi.Client')
        
        scraper = CompanyScraper(config_manager=mock_config_manager_with_key)
        
        assert scraper.api_key == "test_api_key"
        mock_client_constructor.assert_called_once_with(api_key="test_api_key")
        assert scraper.client is mock_client_constructor.return_value

    def test_init_without_api_key(self, mock_config_manager_no_key, mocker):
        # Patch the client creation during init within correct module
        mock_client_constructor = mocker.patch('src.data_acquisition.company_scraper.serpapi.Client')

        scraper = CompanyScraper(config_manager=mock_config_manager_no_key)
        
        assert scraper.api_key is None
        mock_client_constructor.assert_not_called()
        assert scraper.client is None

class TestCompanyScraperGetCompanyInfo:

    def test_get_company_info_no_api_key(self, mock_config_manager_no_key):
        scraper = CompanyScraper(config_manager=mock_config_manager_no_key)
        result = scraper.get_company_info("Test Company")
        assert result is None

    def test_get_company_info_success(self, mock_config_manager_with_key, mock_serpapi_client, mocker):
        scraper = CompanyScraper(config_manager=mock_config_manager_with_key)
        company_name = "Globex Corporation"
        mock_api_results = {"knowledge_graph": {"title": company_name}, "organic_results": []}
        mock_serpapi_client.search.return_value = mock_api_results
        
        mock_parse = mocker.patch.object(scraper, '_parse_company_results')
        mock_parse.return_value = {"name": company_name, "website": "globex.com"}

        result = scraper.get_company_info(company_name)

        expected_params = {
            "engine": "google",
            "q": f'{company_name} company profile overview linkedin',
            "gl": "us",
            "hl": "en",
        }
        mock_serpapi_client.search.assert_called_once_with(expected_params)
        mock_parse.assert_called_once_with(mock_api_results)
        assert result == {"name": company_name, "website": "globex.com"}

    def test_get_company_info_api_exception(self, mock_config_manager_with_key, mock_serpapi_client):
        scraper = CompanyScraper(config_manager=mock_config_manager_with_key)
        company_name = "ErrorProne Inc"
        mock_serpapi_client.search.side_effect = Exception("SerpApi Down")

        result = scraper.get_company_info(company_name)
        
        assert result is None

class TestCompanyScraperParseCompanyResults:
    @pytest.fixture
    def scraper(self, mock_config_manager_no_key):
        return CompanyScraper(config_manager=mock_config_manager_no_key)

    def test_parse_results_with_knowledge_graph(self, scraper):
        mock_results = {
            "search_parameters": {"q": "Test KG Inc company profile overview linkedin"},
            "knowledge_graph": {
                "title": "Test KG Inc",
                "description": "A company from KG.",
                "header_images": [{"source": "http://testkg.com"}]
            },
            "organic_results": []
        }
        parsed = scraper._parse_company_results(mock_results)
        assert parsed['name'] == "Test KG Inc"
        assert parsed['description'] == "A company from KG."
        assert parsed['website'] == "http://testkg.com"

    def test_parse_results_with_organic_only(self, scraper):
        mock_results = {
            "search_parameters": {"q": "Organic Co company profile overview linkedin"},
            "organic_results": [
                {"title": "Organic Co - Official Site", "link": "http://organicco.com", "snippet": "The official website for Organic Co."},
                {"title": "Organic Co | LinkedIn", "link": "https://linkedin.com/company/organicco", "snippet": "..."}
            ]
        }
        parsed = scraper._parse_company_results(mock_results)
        assert parsed['name'] == "Organic Co"
        assert parsed['website'] == "http://organicco.com"
        assert parsed['description'] == "The official website for Organic Co."

    def test_parse_results_fallback_name_from_query(self, scraper):
        mock_results = {
             "search_parameters": {"q": "Minimal Co company profile overview linkedin"},
             "organic_results": [ {"title": "Some Random Page Title", "link": "http://random.com", "snippet": "..."} ]
        }
        parsed = scraper._parse_company_results(mock_results)
        assert parsed['name'] == "Some Random Page Title"
        assert parsed['website'] == "http://random.com"

    def test_parse_results_no_useful_info(self, scraper):
        mock_results = {
            "search_parameters": {"q": "Obscure Entity company profile overview linkedin"},
            "organic_results": []
        }
        parsed = scraper._parse_company_results(mock_results)
        assert parsed['name'] == "Obscure Entity"
        assert parsed is not None
        assert parsed.get('website') is None
        assert parsed.get('description') is None

# --- TODO: Tests for _make_serpapi_request --- 
class TestCompanyScraperMakeSerpApiRequest:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        # Need API key for this method
        return CompanyScraper(config_manager=mock_config_manager_with_key)

    def test_make_request_success(self, scraper, mock_serpapi_client):
        query = "test query"
        num = 5
        mock_response = {"organic_results": [{"title": "Result 1"}] }
        mock_serpapi_client.search.return_value = mock_response
        
        results = scraper._make_serpapi_request(query, num_results=num)
        
        expected_params = {
            "engine": "google",
            "q": query,
            "api_key": scraper.api_key, # Should use the key from init
            "num": str(num),
        }
        # Corrected Assertion: Assert on the mock method provided by the fixture
        mock_serpapi_client.search.assert_called_once_with(expected_params)
        assert results == mock_response

    def test_make_request_no_api_key(self, mock_config_manager_no_key):
        scraper = CompanyScraper(config_manager=mock_config_manager_no_key)
        results = scraper._make_serpapi_request("query")
        assert results is None
        # Assert scraper.client.search was not called because scraper.client is None
        assert scraper.client is None 

    def test_make_request_api_error_response(self, scraper, mock_serpapi_client):
        mock_serpapi_client.search.return_value = {"error": "API limit reached"}
        results = scraper._make_serpapi_request("query")
        assert results is None
        # Optionally check logger error
        
    def test_make_request_no_organic_results(self, scraper, mock_serpapi_client):
        mock_serpapi_client.search.return_value = {"search_information": {}} # No organic_results key
        results = scraper._make_serpapi_request("query")
        assert results is None
        # Optionally check logger warning

    def test_make_request_exception(self, scraper, mock_serpapi_client):
        mock_serpapi_client.search.side_effect = Exception("Connection error")
        results = scraper._make_serpapi_request("query")
        assert results is None
        # Optionally check logger exception

# --- TODO: Tests for find_company_linkedin_url --- 
class TestCompanyScraperFindCompanyLinkedinUrl:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        return CompanyScraper(config_manager=mock_config_manager_with_key)

    def test_find_linkedin_success(self, scraper, mocker):
        company_name = "Acme Corp"
        expected_url = "https://linkedin.com/company/acmecorp"
        mock_results = {"organic_results": [
            {"title": "Acme Corp | LinkedIn", "link": expected_url},
            {"title": "Acme Corp - Wikipedia", "link": "wiki/acme"}
        ]}
        mocker.patch.object(scraper, '_make_serpapi_request', return_value=mock_results)
        
        url = scraper.find_company_linkedin_url(company_name)
        
        scraper._make_serpapi_request.assert_called_once_with(f'{company_name} site:linkedin.com/company', num_results=3)
        assert url == expected_url

    def test_find_linkedin_no_match(self, scraper, mocker):
        company_name = "No LinkedIn Co"
        mock_results = {"organic_results": [
            {"title": "NLC - Official Site", "link": "nlc.com"},
            {"title": "News about NLC", "link": "news.com/nlc"}
        ]}
        mocker.patch.object(scraper, '_make_serpapi_request', return_value=mock_results)
        
        url = scraper.find_company_linkedin_url(company_name)
        assert url is None

    def test_find_linkedin_api_error(self, scraper, mocker):
        company_name = "API Error Co"
        mocker.patch.object(scraper, '_make_serpapi_request', return_value=None)
        
        url = scraper.find_company_linkedin_url(company_name)
        assert url is None

# --- TODO: Tests for extract_company_data_from_url (including cache) --- 
class TestCompanyScraperExtractCompanyData:
    @pytest.fixture
    def scraper(self, mock_config_manager_with_key):
        scraper = CompanyScraper(config_manager=mock_config_manager_with_key)
        scraper.cache = {} # Ensure clean cache
        return scraper

    def test_extract_data_cache_hit(self, scraper, mocker):
        url = "https://linkedin.com/company/cachedco"
        cached_data = {"name": "Cached Co", "linkedin_url": url}
        # Corrected: Use time.time()
        scraper.cache[url] = {"timestamp": time.time() - 10, "data": cached_data} 
        mock_make_request = mocker.patch.object(scraper, '_make_serpapi_request')

        result = scraper.extract_company_data_from_url(url)

        assert result == cached_data
        mock_make_request.assert_not_called()

    def test_extract_data_cache_expired(self, scraper, mocker):
        url = "https://linkedin.com/company/expiredco"
        cached_data = {"name": "Expired Co", "linkedin_url": url}
        scraper.cache_expiry_seconds = 1 # Short expiry
        # Corrected: Use time.time()
        scraper.cache[url] = {"timestamp": time.time() - 10, "data": cached_data} 
        
        mock_api_result = {"knowledge_graph": {"title": "Expired Co Fresh"}} # New data from API
        mock_make_request = mocker.patch.object(scraper, '_make_serpapi_request', return_value=mock_api_result)

        result = scraper.extract_company_data_from_url(url)

        mock_make_request.assert_called_once_with(query=url, num_results=1)
        assert result is not None
        assert result['name'] == "Expired Co Fresh"
        assert scraper.cache[url]["data"] == result # Check cache updated

    def test_extract_data_success_kg(self, scraper, mocker):
        url = "https://linkedin.com/company/kgco"
        mock_api_result = {"knowledge_graph": {
            "title": "KG Co",
            "description": "KG Desc",
            "website": "kg.com",
            "type": "Technology Company (organization)", # Used as industry fallback
            # Assume size and location are not directly in KG here
        }}
        mock_make_request = mocker.patch.object(scraper, '_make_serpapi_request', return_value=mock_api_result)

        result = scraper.extract_company_data_from_url(url)

        assert result['linkedin_url'] == url
        assert result['name'] == "KG Co"
        assert result['description'] == "KG Desc"
        assert result['website'] == "kg.com"
        assert result['industry'] == "Technology Company (organization)"
        assert result['size'] is None
        assert result['location'] is None

    def test_extract_data_success_organic_fallback(self, scraper, mocker):
        url = "https://linkedin.com/company/organicco"
        mock_api_result = {"organic_results": [
            {"title": "Organic Co Name", "snippet": "Organic Desc", "link": "organic.com"}
        ]}
        mock_make_request = mocker.patch.object(scraper, '_make_serpapi_request', return_value=mock_api_result)

        result = scraper.extract_company_data_from_url(url)

        assert result['name'] == "Organic Co Name"
        assert result['description'] == "Organic Desc"
        assert result['website'] == "organic.com"

    def test_extract_data_api_error(self, scraper, mocker):
        url = "https://linkedin.com/company/errorco"
        mock_make_request = mocker.patch.object(scraper, '_make_serpapi_request', return_value=None)
        
        result = scraper.extract_company_data_from_url(url)
        assert result is None
