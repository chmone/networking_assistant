import os
import sys
import requests
import logging

# Adjust path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try importing from src, adjusting based on execution context
if __package__:
    from ..config.config_manager import ConfigManager
    from ..core.exceptions import ConfigError, DataAcquisitionError, ApiAuthError, ApiLimitError
    from ..core.retry_utils import retry_with_backoff
else:
    # Assume running from root or src is in PYTHONPATH
    try:
        from src.config.config_manager import ConfigManager
        from src.core.exceptions import ConfigError, DataAcquisitionError, ApiAuthError, ApiLimitError
        from src.core.retry_utils import retry_with_backoff
    except ImportError as e:
        logging.critical(f"Failed to import necessary modules for NotionClient: {e}")
        raise

logger = logging.getLogger(__name__)

class NotionClient:
    """Client for interacting with the Notion API."""

    DEFAULT_NOTION_VERSION = "2022-06-28"
    BASE_URL = "https://api.notion.com/v1"

    def __init__(self, config_manager: ConfigManager = None):
        """Initializes the Notion Client with authentication details."""
        if config_manager is None:
             # If no config manager passed, create one (assumes .env is findable)
            logger.info("No ConfigManager passed to NotionClient, creating default.")
            self.config = ConfigManager()
        else:
            self.config = config_manager

        self.token = self.config.notion_token
        self.notion_version = os.getenv('NOTION_API_VERSION', self.DEFAULT_NOTION_VERSION)
        
        if not self.token:
            logger.error("NOTION_TOKEN is not configured. NotionClient cannot authenticate.")
            # Raise ConfigError immediately if token is essential for any client function
            raise ConfigError("NOTION_TOKEN is required for NotionClient but not found in configuration.")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.notion_version
        }
        logger.info(f"NotionClient initialized. Using Notion API version: {self.notion_version}")

    @retry_with_backoff(retries=3, initial_delay=1, backoff_factor=2)
    def _make_request(self, method: str, endpoint: str, **kwargs):
        """
        Makes an authenticated request to the Notion API with retry logic.
        Handles common errors and raises specific custom exceptions.

        :param method: HTTP method (e.g., 'GET', 'POST', 'PATCH').
        :param endpoint: API endpoint path (e.g., '/databases', '/pages').
        :param kwargs: Additional arguments to pass to requests.request (e.g., json, params).
        :return: The JSON response from the API.
        :raises ApiAuthError: If authentication fails (401).
        :raises ApiLimitError: If rate limit is hit (429) after retries.
        :raises DataAcquisitionError: For other HTTP errors or request issues after retries.
        """
        url = f"{self.BASE_URL}{endpoint}"
        request_desc = f"Notion API {method} {endpoint}"
        logger.debug(f"Making request: {request_desc} with args: {kwargs}")
        
        try:
            response = requests.request(method, url, headers=self.headers, timeout=20, **kwargs)

            # Check specific non-retryable or critical errors first
            if response.status_code == 401:
                 logger.error(f"Notion API Authentication Error (401) for {request_desc}. Check your NOTION_TOKEN.")
                 raise ApiAuthError(f"Notion authentication failed (401)", source="Notion API", original_exception=requests.exceptions.HTTPError(response=response))
            if response.status_code == 403:
                 logger.error(f"Notion API Forbidden Error (403) for {request_desc}. Check token permissions or request.")
                 # Often permissions related, treat as auth error for now
                 raise ApiAuthError(f"Notion API forbidden (403), check permissions", source="Notion API", original_exception=requests.exceptions.HTTPError(response=response))
            if response.status_code == 404:
                 logger.warning(f"Notion API Not Found (404) for {request_desc}. Endpoint or resource may not exist.")
                 # Let raise_for_status handle this, but log warning
                 response.raise_for_status() 
            
            # Check for other client/server errors AFTER retry decorator has handled 429/5xx
            if response.status_code >= 400:
                 logger.error(f"Notion API Error ({response.status_code}) for {request_desc}: {response.text[:500]}")
                 response.raise_for_status() # Raise HTTPError to be potentially caught by decorator or below

            # Handle potential empty response for methods like DELETE
            if response.status_code == 204 or not response.content:
                 logger.debug(f"{request_desc} completed with status {response.status_code} and no content.")
                 return None # Or return an empty dict/True based on expected outcome

            # Attempt to parse JSON for successful responses with content
            return response.json()

        except requests.exceptions.HTTPError as http_err:
            # If decorator re-raises HTTPError after retries (e.g., for 429 or 5xx)
            if http_err.response is not None:
                if http_err.response.status_code == 429:
                    raise ApiLimitError(f"Notion API rate limit persisted after retries for {request_desc}", source="Notion API", original_exception=http_err) from http_err
            # General HTTP error 
            logger.error(f"Persistent HTTPError for {request_desc} after retries (if any): {http_err} - Status: {http_err.response.status_code if http_err.response else 'N/A'}")
            raise DataAcquisitionError(f"Notion API HTTP error for {request_desc}", source="Notion API", original_exception=http_err) from http_err
        
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Persistent RequestException for {request_desc} after retries: {req_err}")
            raise DataAcquisitionError(f"Notion API network/request error for {request_desc}", source="Notion API", original_exception=req_err) from req_err
        
        except ValueError as json_err: # Catch JSONDecodeError specifically
             logger.error(f"Failed to decode JSON response for {request_desc}: {json_err}. Response text: {response.text[:200] if hasattr(response, 'text') else 'N/A'}")
             raise DataAcquisitionError(f"Invalid JSON response from Notion API for {request_desc}", source="Notion API", original_exception=json_err) from json_err

        except Exception as e:
            logger.exception(f"Unexpected error during {request_desc}: {e}")
            raise DataAcquisitionError(f"Unexpected error interacting with Notion API for {request_desc}", source="Notion API", original_exception=e) from e

    # --- Basic API Interaction Methods (Examples) ---
    # These provide a cleaner interface than calling _make_request directly
    
    def get_page(self, page_id: str):
        """Retrieves a Notion page by its ID."""
        return self._make_request('GET', f'/pages/{page_id}')

    def create_page(self, data: dict):
        """Creates a new Notion page."""
        return self._make_request('POST', '/pages', json=data)

    def update_page_properties(self, page_id: str, properties: dict):
        """Updates properties of an existing Notion page."""
        payload = {"properties": properties}
        return self._make_request('PATCH', f'/pages/{page_id}', json=payload)
        
    def query_database(self, database_id: str, filter_payload: dict = None, sorts: list = None, start_cursor: str = None, page_size: int = None):
        """Queries a Notion database with optional filters, sorts, and pagination."""
        payload = {}
        if filter_payload is not None:
            payload['filter'] = filter_payload
        if sorts is not None:
            payload['sorts'] = sorts
        if start_cursor is not None:
            payload['start_cursor'] = start_cursor
        if page_size is not None:
            payload['page_size'] = page_size
            
        # POST request is used for querying databases in Notion API
        return self._make_request('POST', f'/databases/{database_id}/query', json=payload if payload else None)
        
    def create_database(self, data: dict):
         """Creates a new Notion database."""
         return self._make_request('POST', '/databases', json=data)

    # Add other methods as needed (e.g., retrieve_database, update_block, append_block_children)

# Example Usage (for testing the client itself)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG) # Enable debug for testing
    print("Testing NotionClient...")
    
    # This assumes you have a valid NOTION_TOKEN and potentially a test page/db ID 
    # in your .env file in the project root when running this directly.
    try:
        client = NotionClient() # Uses default ConfigManager, expects .env
        print("NotionClient initialized.")
        
        # --- Test basic request (requires a known valid page ID in your Notion)
        # Replace 'YOUR_TEST_PAGE_ID' with an actual page ID accessible by your token
        test_page_id = os.getenv('NOTION_TEST_PAGE_ID') 
        if test_page_id:
            print(f"\n--- Attempting to retrieve test page: {test_page_id} ---")
            try:
                page_data = client.get_page(test_page_id)
                if page_data:
                    print(f"Successfully retrieved page. Title (if available): {page_data.get('properties', {}).get('title', {}).get('title', [{}])[0].get('plain_text', 'N/A')}")
                else:
                    print("Retrieved page data was empty or None.")
            except DataAcquisitionError as e:
                print(f"Failed to retrieve page: {e}")
        else:
            print("\nSkipping get_page test: NOTION_TEST_PAGE_ID not set in environment.")

        # --- Add more tests as needed for other methods like create_page, query_database etc. ---
        # These would require careful setup (e.g., parent page ID for creation, db ID for query)
        print("\nNotionClient basic tests completed (manual check needed for results).")
        
    except ConfigError as e:
        print(f"Configuration Error during client init: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during testing: {e}") 