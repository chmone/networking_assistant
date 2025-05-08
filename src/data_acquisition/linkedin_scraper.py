import os
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
import logging
import requests
from core.exceptions import ApiAuthError, ApiLimitError, DataAcquisitionError
import datetime

logger = logging.getLogger(__name__)

# --- Start of robust import for ConfigManager ---
try:
    # This is the primary import path when src is on pythonpath (e.g., during pytest)
    from config.config_manager import ConfigManager
except ImportError:
    # Fallback logic for other execution contexts (e.g., running the script directly)
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level from data_acquisition to reach src/
    src_path = os.path.abspath(os.path.join(current_dir, '..')) 
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        # Retry the import now that src/ should be on the path
        from config.config_manager import ConfigManager
    except ImportError as e_inner:
        # If it still fails, log and re-raise a more informative error or a custom one
        logging.error(f"Critical: Could not import ConfigManager from {src_path} or directly. Error: {e_inner}")
        raise RuntimeError(f"LinkedInScraper requires ConfigManager, which could not be imported: {e_inner}")
# --- End of robust import for ConfigManager ---

# --- Start of robust import for retry_utils ---
try:
    from core.retry_utils import retry_with_backoff
except ImportError:
    import sys # Already imported but good for clarity in block
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.abspath(os.path.join(current_dir, '..')) # Path to src/
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        from core.retry_utils import retry_with_backoff
    except ImportError as e_retry:
        logging.warning(f"Could not import retry_with_backoff for LinkedInScraper: {e_retry}. Retries will not be available.")
        # Define a dummy decorator if retry_with_backoff is critical or used extensively
        def retry_with_backoff(*args, **kwargs): # Dummy decorator
            def decorator(func):
                return func
            return decorator
class LinkedInScraper:
    def __init__(self, config_manager: ConfigManager = None):
        """
        Initializes the LinkedInScraper with a ConfigManager.
        If no ConfigManager is provided, it attempts to create one.
        """
        if config_manager is None:
            # Assuming .env is in the project root, and this script is in src/data_acquisition
            # The path to .env needs to be relative to where ConfigManager is called from,
            # or an absolute path. For simplicity, ConfigManager defaults to '.env' in CWD.
            # If running this file directly for testing, CWD might be src/data_acquisition.
            # If run from project root (e.g. main.py), CWD is project root.
            # For robustness, one might pass an explicit path or ensure CWD.
            # For now, relying on ConfigManager's default or hoping it's run from root.
            # A better approach for module-level ConfigManager instantiation:
            # project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            # env_path = os.path.join(project_root, '.env')
            # self.config = ConfigManager(env_file_path=env_path)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root_env = os.path.abspath(os.path.join(current_dir, '..', '..')) 
            env_path = os.path.join(project_root_env, '.env')
            if not os.path.exists(env_path):
                logger.warning(f".env file not found at {env_path} for LinkedInScraper, using defaults or expecting env vars.")
            self.config = ConfigManager(env_file_path=env_path)
        else:
            self.config = config_manager
            
        self.api_key = self.config.scraping_api_key
        self.base_url = "https://serpapi.com/search.json" # SerpApi endpoint
        logger.info("LinkedInScraper initialized.")

        if not self.api_key:
            logger.warning("SCRAPING_API_KEY not found in configuration. SerpApi calls will fail.")
            # Consider raising an error if API key is absolutely essential for the class to function
            # raise ValueError("SCRAPING_API_KEY is required for LinkedInScraper")

    @retry_with_backoff(retries=3, initial_delay=2, backoff_factor=2)
    def _make_api_request(self, params: dict, request_description: str):
        """Makes the actual HTTP GET request to SerpApi and handles basic response codes."""
        logger.debug(f"Making API request for {request_description} with params: {params}")
        response = None # Initialize response here to make it available in ValueError's except block
        try:
            response = requests.get(self.base_url, params=params, timeout=20)
            
            # Let raise_for_status() handle all HTTP error codes first.
            # The specific error handling (ApiAuthError, ApiLimitError)
            # will be done in the `except requests.exceptions.HTTPError` block.
            response.raise_for_status() 

            return response.json()

        except requests.exceptions.HTTPError as http_err:
            # Ensure response is available for logging, even if error occurred before response.json()
            current_response = http_err.response if http_err.response is not None else response
            status_code = current_response.status_code if current_response else 'N/A'
            
            if status_code == 401 or status_code == 403:
                logger.error(f"Authentication error for {request_description}. Status: {status_code}. Check API Key.")
                raise ApiAuthError(f"Authentication failed for {request_description}", source="SerpApi", original_exception=http_err)
            elif status_code == 429:
                 # Directly raise ApiLimitError. The decorator will catch and retry this.
                 logger.error(f"API rate limit error encountered for {request_description} (Status: {status_code}). Will attempt retry.")
                 raise ApiLimitError(f"API rate limit error for {request_description}", source="SerpApi", original_exception=http_err)

            # For any other HTTPError (400, 500, etc.)
            logger.error(f"HTTPError during {request_description} (Status: {status_code}): {http_err}")
            raise DataAcquisitionError(f"HTTP error during {request_description}", source="SerpApi", original_exception=http_err)
        
        except requests.exceptions.RequestException as req_err: 
            logger.error(f"RequestException (network/timeout) during {request_description}: {req_err}")
            raise DataAcquisitionError(f"Network or request error during {request_description}", source="SerpApi", original_exception=req_err)
        
        except ValueError as json_decode_err: 
            # Ensure response is available for logging if json decoding fails
            response_text_snippet = response.text[:200] if response and hasattr(response, 'text') else 'N/A'
            logger.error(f"Failed to decode JSON response for {request_description}: {json_decode_err}. Response text: {response_text_snippet}")
            raise DataAcquisitionError(f"Invalid JSON response for {request_description}", source="SerpApi", original_exception=json_decode_err)

        except Exception as e: 
            # This is a catch-all for truly unexpected errors.
            logger.exception(f"Unexpected error in _make_api_request for {request_description}: {e}")
            raise DataAcquisitionError(f"Unexpected error in API request for {request_description}", source="SerpApi", original_exception=e)

    def test_api_connection(self, test_query="Product Manager New York"):
        if not self.api_key:
            logger.error("Cannot test API connection: SCRAPING_API_KEY is not configured.")
            # Consider raising ConfigError here
            return {"status": "error", "message": "API key not configured."}
        
        params = {"engine": "google", "q": test_query, "api_key": self.api_key, "num": "1"}
        request_desc = "SerpApi connection test (Google engine)"
        logger.info(f"Attempting {request_desc}...")
        try:
            # Using _make_api_request which has retry logic
            data = self._make_api_request(params, request_desc)
            # A successful response from SerpApi usually has a 'search_metadata' field
            if data and isinstance(data, dict) and 'search_metadata' in data:
                logger.info(f"{request_desc} successful. Search ID: {data['search_metadata'].get('id')}")
                return {"status": "success", "data": data['search_metadata']}
            else:
                logger.warning(f"{request_desc} returned unexpected data structure: {str(data)[:200]}")
                return {"status": "warning", "message": "Unexpected response structure from API.", "data": data}
        except DataAcquisitionError as e:
            logger.error(f"{request_desc} failed after retries: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e: # Catch any other unexpected errors during this specific test method
            logger.exception(f"Unexpected error during {request_desc}: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def scrape_alumni_by_school(self, school_name, max_results=100):
        if not self.api_key: 
            msg = "SCRAPING_API_KEY not configured for LinkedInScraper, cannot scrape alumni."
            logger.error(msg)
            # raise ConfigError(msg) # Or raise ConfigError for stricter handling
            return []
        
        query = f'"{school_name}" site:linkedin.com/in/'
        params = {
            "engine": "google", "q": query, "api_key": self.api_key,
            "num": str(max_results) if max_results <= 100 else "100",
            "gl": "us", "hl": "en"
        }
        request_desc = f"alumni search for '{school_name}'"
        logger.info(f"Preparing for {request_desc}")
        try:
            data = self._make_api_request(params, request_desc)
            logger.info(f"Successfully received and parsed response for {request_desc}")
            return self._parse_linkedin_results(data, source=f"Alumni Search: {school_name}")
        except DataAcquisitionError as dae:
            logger.error(f"Data acquisition failed for {request_desc} after retries: {dae}")
            return []
        except Exception as e: # Catch other unexpected errors during parsing or flow
            logger.exception(f"Unexpected error processing {request_desc}: {e}")
            return []

    def scrape_pms_by_location(self, location="New York City", keywords=None, max_results=100):
        if not self.api_key: 
            msg = "SCRAPING_API_KEY not configured for LinkedInScraper, cannot scrape PMs."
            logger.error(msg)
            # raise ConfigError(msg)
            return []

        if keywords is None: keywords = self.config.pm_keywords
        keyword_string = ' OR '.join([f'"{k}"' for k in keywords])
        query = f'({keyword_string}) "{location}" site:linkedin.com/in/'
        params = {
            "engine": "google", "q": query, "api_key": self.api_key,
            "num": str(max_results) if max_results <= 100 else "100",
            "gl": "us", "hl": "en"
        }
        request_desc = f"PM search in '{location}'"
        logger.info(f"Preparing for {request_desc}")
        try:
            data = self._make_api_request(params, request_desc)
            logger.info(f"Successfully received and parsed response for {request_desc}")
            return self._parse_linkedin_results(data, source=f"PM Search: {location}")
        except DataAcquisitionError as dae:
            logger.error(f"Data acquisition failed for {request_desc} after retries: {dae}")
            return []
        except Exception as e: 
            logger.exception(f"Unexpected error processing {request_desc}: {e}")
            return []

    def _parse_linkedin_results(self, data, source):
        """
        Parses the organic_results from SerpApi Google Search JSON 
        to extract potential LinkedIn lead information.
        """
        leads = []
        organic_results = data.get("organic_results", []) 
        
        if not organic_results:
             logger.warning(f"No organic results found in the SerpApi response for source: {source}")
             if data.get("search_metadata", {}).get("status", "").lower() == "error":
                 logger.error(f"SerpApi search error in metadata: {data['search_metadata'].get('error')}")
             elif data.get("search_information", {}).get("organic_results_state") == "Fully empty":
                 logger.info(f"SerpApi reported fully empty results for source: {source}")
             return leads

        for result in organic_results:
            title = result.get("title", "")
            link = result.get("link", "")
            snippet = result.get("snippet", "")
            
            # Basic check if it looks like a LinkedIn profile result
            if not link or "linkedin.com/in/" not in link:
                continue 

            # --- Attempt to extract structured data --- 
            # Name is often the first part of the title before '-' or '|'
            if ' - ' in title:
                name_parts = title.split(' - ', 1)
            elif ' | ' in title:
                name_parts = title.split(' | ', 1)
            else:
                name_parts = [title] # Assume entire title is the name if no clear separator
            
            lead_name = name_parts[0].strip()
            title_remainder = name_parts[1].strip() if len(name_parts) > 1 else ""

            # Role and Company might be in the title remainder or snippet
            # This requires more sophisticated parsing, making educated guesses here
            current_role = ""
            company_name = ""
            location_val = ""
            
            # Try finding role/company in title remainder
            if " at " in title_remainder.lower():
                role_company_parts = title_remainder.split(' at ', 1)
                current_role = role_company_parts[0].strip()
                company_name = role_company_parts[1].strip()
            elif " - " in title_remainder: # Try splitting by " - " if " at " not found
                role_company_parts = title_remainder.rsplit(' - ', 1) # Split by the last hyphen
                current_role = role_company_parts[0].strip()
                if len(role_company_parts) > 1:
                    company_name = role_company_parts[1].strip()
                else: # Only a role was found in title_remainder
                    company_name = ""
            else:
                 # If not in title or only a role in title, maybe the first part of the snippet?
                 if snippet:
                     # Simplistic: assume first sentence or part before a common delimiter might contain role/company
                     # This is highly heuristic and likely needs refinement
                     first_sentence = snippet.split('.')[0]
                     if " at " in first_sentence.lower():
                         role_company_parts = first_sentence.split(' at ', 1)
                         current_role = role_company_parts[0].strip()
                         company_name = role_company_parts[1].strip()
                     else:
                         # Last resort: if title_remainder had something but wasn't parsable above, use it as role
                         # and company will remain empty unless found in snippet
                        if not current_role: # Only if not already set from title_remainder variants
                            current_role = title_remainder or ""

            # Location might be mentioned in the snippet
            location_val = "" # EXPLICITLY Reset location for each result item
            if snippet:
                if "Location:" in snippet:
                     loc_parts = snippet.split("Location:", 1)
                     if len(loc_parts) > 1:
                         # Take first part after "Location:", trim potential extra details
                         location_val = loc_parts[1].split('\n')[0].split(' · ')[0].strip()
                # IMPORTANT: Use 'elif' to ensure only ONE block sets the location
                elif ' · ' in snippet:
                    # Assume location is before the first '·' if "Location:" isn't present
                    potential_loc = snippet.split(' · ', 1)[0].strip()
                    # Basic sanity check: does it look like a location?
                    # Avoid things like "500+ connections" or "Software Engineer at..."
                    if 'connection' not in potential_loc.lower() and \
                       ' at ' not in potential_loc.lower() and \
                       len(potential_loc) < 50: # Arbitrary length limit
                        location_val = potential_loc
                    # If the sanity check fails, location_val remains ""

            # Alma mater match - requires comparing snippet/title against config.target_schools
            alma_mater_match = []
            search_text = (title + " " + snippet).lower()
            for school in self.config.target_schools:
                if school.lower() in search_text:
                    alma_mater_match.append(school)
            
            # Basic data validation (ensure name and link are present)
            if not lead_name or not link:
                continue

            lead = {
                "lead_name": lead_name,
                "linkedin_profile_url": link,
                "current_role": current_role,
                "company_name": company_name,
                "location": location_val,
                "alma_mater_match": alma_mater_match, # List of matched schools
                "source_of_lead": source,
                "date_added": datetime.datetime.now().isoformat(),
                "raw_snippet": snippet # Keep raw snippet for potential reprocessing
            }
            leads.append(lead)
            
        logger.info(f"Parsed {len(leads)} potential leads from source: {source}")
        return leads

# Removed __main__ block, testing should be done via test_linkedin_scraper.py 