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
import json
import serpapi
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions

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
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.api_key = self.config_manager.get_config("SERPAPI_API_KEY")
        if not self.api_key:
            logger.warning("SERPAPI_API_KEY not found in configuration. SerpApi-based scraping will fail.")
        
        # Initialize the SerpApi client if we have an API key
        self.serpapi_client = serpapi.Client(api_key=self.api_key) if self.api_key else None
        if self.api_key and not self.serpapi_client: # Should not happen if key exists, but good check
            logger.error("Failed to initialize SerpApi client even with API key.")

        # Selenium WebDriver setup
        self.driver = None # Initialize driver as None
        # We might want to set up the driver on demand or explicitly call a setup method
        # For now, let's assume it might be set up when user profile scraping is initiated.

    def _setup_driver(self):
        """Initializes and configures the Selenium WebDriver."""
        if self.driver:
            logger.info("WebDriver already initialized.")
            return

        try:
            logger.info("Setting up Selenium WebDriver for Chrome...")
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")  # Run headless
            chrome_options.add_argument("--no-sandbox") # Bypass OS security model, required for some environments
            chrome_options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
            chrome_options.add_argument("--disable-gpu") # Applicable to windows os only
            chrome_options.add_argument("user-agent=" + self.config_manager.get_config("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"))
            
            # Use webdriver-manager to automatically download and manage ChromeDriver
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Selenium WebDriver for Chrome initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Selenium WebDriver: {e}", exc_info=True)
            self.driver = None # Ensure driver is None if setup fails
            # Optionally re-raise or handle more gracefully depending on requirements

    def close_driver(self):
        """Closes the Selenium WebDriver if it's active."""
        if self.driver:
            try:
                logger.info("Closing Selenium WebDriver.")
                self.driver.quit()
                self.driver = None
                logger.info("Selenium WebDriver closed successfully.")
            except Exception as e:
                logger.error(f"Error closing Selenium WebDriver: {e}", exc_info=True)
                # Driver might be in an unusable state, still set to None
                self.driver = None

    @retry_with_backoff(retries=3, initial_delay=2, backoff_factor=2)
    def _make_serpapi_search(self, params: dict, request_description: str):
        """Makes a search request using the new serpapi.Client and handles basic response codes/errors."""
        if not self.serpapi_client:
            msg = f"SerpApi client not initialized (likely missing API key). Cannot perform {request_description}."
            logger.error(msg)
            raise ApiAuthError(msg, source="SerpApi")

        logger.debug(f"Making SerpApi search for {request_description} with params: {params}")
        
        if 'engine' not in params:
            params['engine'] = 'google' 
            logger.warning(f"'engine' not specified for SerpApi search: {request_description}. Defaulting to 'google'.")

        try:
            results = self.serpapi_client.search(params)
            
            if "error" in results:
                error_message = results["error"]
                logger.error(f"SerpApi returned an error for {request_description}: {error_message}")
                if "Authorization invalid" in error_message or "API key is invalid" in error_message:
                    raise ApiAuthError(f"SerpApi Authentication Error: {error_message}", source="SerpApi")
                elif "rate limit" in error_message.lower():
                    raise ApiLimitError(f"SerpApi Rate Limit Error: {error_message}", source="SerpApi")
                # For other errors reported by SerpApi in the 'error' field
                raise DataAcquisitionError(f"SerpApi Error: {error_message}", source="SerpApi") 
            
            return results

        except (ApiAuthError, ApiLimitError, DataAcquisitionError) as specific_err:
            # If one of our custom exceptions was raised above, just re-raise it
            # This ensures the retry decorator sees the specific exception type.
            logger.error(f"Specific data acquisition error for {request_description}: {specific_err}") # Log it here if needed
            raise

        except serpapi.SerpApiError as serp_err: 
            logger.error(f"SerpApi library error during {request_description}: {serp_err}")
            err_str = str(serp_err).lower()
            if "invalid api key" in err_str or "authorization" in err_str:
                 raise ApiAuthError(f"SerpApi Auth/Config Error: {serp_err}", source="SerpApi", original_exception=serp_err)
            elif "rate limit" in err_str:
                 raise ApiLimitError(f"SerpApi Rate Limit Error: {serp_err}", source="SerpApi", original_exception=serp_err)
            # For other SerpApiError instances that don't map to Auth or Limit
            raise DataAcquisitionError(f"SerpApi library error during {request_description}", source="SerpApi", original_exception=serp_err)
        
        except requests.exceptions.RequestException as req_err: 
            logger.error(f"Network/RequestException during {request_description} via SerpApi client: {req_err}")
            # This is typically a retryable scenario if it's transient.
            # DataAcquisitionError might be too generic if retry logic needs to distinguish it.
            # However, for now, keeping it as DataAcquisitionError.
            raise DataAcquisitionError(f"Network or request error during {request_description}", source="SerpApi", original_exception=req_err)

        except Exception as e: 
            # This final catch-all is for truly unexpected errors.
            # It should NOT catch ApiAuthError, ApiLimitError, or DataAcquisitionError already handled.
            logger.exception(f"Unexpected error in _make_serpapi_search for {request_description}: {e}")
            raise DataAcquisitionError(f"Unexpected error in SerpApi search for {request_description}", source="SerpApi", original_exception=e)

    def test_api_connection(self, test_query="Product Manager New York"):
        if not self.serpapi_client: # Check if client was initialized
            logger.error("Cannot test API connection: SerpApi client not initialized (API key likely missing).")
            return {"status": "error", "message": "SerpApi client not initialized."}
        
        params = {"engine": "google", "q": test_query, "num": "1"} # api_key is handled by client
        request_desc = "SerpApi connection test (Google engine)"
        logger.info(f"Attempting {request_desc}...")
        try:
            data = self._make_serpapi_search(params, request_desc)
            if data and isinstance(data, dict) and 'search_metadata' in data:
                logger.info(f"{request_desc} successful. Search ID: {data['search_metadata'].get('id')}")
                return {"status": "success", "data": data['search_metadata']}
            else: # Should be caught by error handling in _make_serpapi_search if 'error' key exists
                logger.warning(f"{request_desc} returned unexpected data structure or was caught as error: {str(data)[:200]}")
                return {"status": "warning", "message": "Unexpected response structure or error from API.", "data": data}
        except DataAcquisitionError as e:
            logger.error(f"{request_desc} failed after retries: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e: 
            logger.exception(f"Unexpected error during {request_desc}: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def scrape_alumni_by_school(self, school_name, max_results=100):
        if not self.serpapi_client: 
            msg = "SerpApi client not initialized. Cannot scrape alumni."
            logger.error(msg)
            return []
        
        query = f'"{school_name}" site:linkedin.com/in/'
        params = {
            "engine": "google", "q": query,
            "num": str(max_results) if max_results <= 100 else "100", # SerpApi typically caps at 100 for 'num'
            "gl": "us", "hl": "en"
        } # api_key is handled by client
        request_desc = f"alumni search for '{school_name}'"
        logger.info(f"Preparing for {request_desc}")
        try:
            data = self._make_serpapi_search(params, request_desc)
            logger.info(f"Successfully received and parsed response for {request_desc}")
            return self._parse_linkedin_results(data, source=f"Alumni Search: {school_name}")
        except DataAcquisitionError as dae:
            logger.error(f"Data acquisition failed for {request_desc} after retries: {dae}")
            return []
        except Exception as e: 
            logger.exception(f"Unexpected error processing {request_desc}: {e}")
            return []

    def scrape_pms_by_location(self, location="New York City", keywords=None, max_results=100):
        if not self.serpapi_client:
            msg = "SerpApi client not initialized. Cannot scrape PMs."
            logger.error(msg)
            return []

        if keywords is None: keywords = self.config_manager.get_config("PM_KEYWORDS", [])
        keyword_string = ' OR '.join([f'"{k}"' for k in keywords])
        query = f'({keyword_string}) "{location}" site:linkedin.com/in/'
        params = {
            "engine": "google", "q": query,
            "num": str(max_results) if max_results <= 100 else "100",
            "gl": "us", "hl": "en"
        } # api_key is handled by client
        request_desc = f"PM search in '{location}'"
        logger.info(f"Preparing for {request_desc}")
        try:
            data = self._make_serpapi_search(params, request_desc)
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
            elif " - " in title_remainder: 
                role_company_parts = title_remainder.rsplit(' - ', 1) 
                current_role = role_company_parts[0].strip()
                if len(role_company_parts) > 1:
                    company_name = role_company_parts[1].strip()
                else: 
                    company_name = ""
            else:
                 if snippet:
                     first_sentence = snippet.split('.')[0]
                     if " at " in first_sentence.lower():
                         role_company_parts = first_sentence.split(' at ', 1)
                         current_role = role_company_parts[0].strip()
                         company_name = role_company_parts[1].strip()
                     else:
                        if not current_role: 
                            current_role = title_remainder or ""

            location_val = "" 
            if snippet:
                # Try specific "Location:" marker first
                if "Location:" in snippet:
                     loc_parts = snippet.split("Location:", 1)
                     if len(loc_parts) > 1:
                         location_val = loc_parts[1].split('\n')[0].split(' · ')[0].strip()
                
                # If not found, try parsing based on common patterns like "Company | Location."
                # This is heuristic and might need refinement.
                if not location_val and company_name and "|" in snippet: 
                    # Look for "Company Name | Location" like pattern
                    # Example: "Innovate Inc. | New York."
                    company_snippet_part = snippet.split(company_name, 1)
                    if len(company_snippet_part) > 1:
                        after_company = company_snippet_part[1].strip()
                        if after_company.startswith("|"):
                            potential_loc_part = after_company[1:].split('.', 1)[0].split('·', 1)[0].strip()
                            if potential_loc_part and len(potential_loc_part) < 50: # Basic sanity check
                                location_val = potential_loc_part
                
                # If still not found, try the ' · ' delimiter as a fallback
                if not location_val and ' · ' in snippet:
                    potential_loc = snippet.split(' · ', 1)[0].strip()
                    if 'connection' not in potential_loc.lower() and \
                       ' at ' not in potential_loc.lower() and \
                       len(potential_loc) < 50: 
                        location_val = potential_loc

            # Alma mater match - requires comparing snippet/title against config.target_schools
            alma_mater_match = []
            search_text = (title + " " + snippet).lower()
            for school in self.config_manager.get_config("TARGET_SCHOOLS", []):
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

    def scrape_user_profile_details(self, linkedin_url: str):
        """
        (Placeholder) Scrapes detailed information from a specific user's LinkedIn profile URL.
        This will be implemented using Selenium.
        """
        logger.info(f"Attempting to scrape profile details for: {linkedin_url} (Currently a stub)")
        
        # Ensure driver is set up before trying to use it
        if not self.driver:
            self._setup_driver()
        
        if not self.driver: # If setup failed
            logger.error("WebDriver not available. Cannot scrape user profile.")
            return {
                "error": "WebDriver initialization failed.",
                "linkedin_url": linkedin_url,
                "details_stub": "Failed to initialize Selenium WebDriver."
            }

        # --- Placeholder for actual Selenium scraping logic --- 
        # Example: self.driver.get(linkedin_url)
        #         # ... find elements, extract data ...
        # For now, just return a stub indicating it was called
        # --- End Placeholder ---

        # Important: Decide if driver should be closed here or managed externally
        # For now, let's assume it's managed externally or closed after a batch of operations.
        # self.close_driver() 

        return {
            "linkedin_url": linkedin_url,
            "full_name": "John Doe (Stub)",
            "headline": "Software Engineer at Innovate Corp (Stub)",
            "experience": [
                {"title": "Senior Developer", "company": "Tech Solutions (Stub)", "duration": "2 years"}
            ],
            "education": [
                {"institution": "State University (Stub)", "degree": "B.S. Computer Science"}
            ],
            "skills": ["Python", "Selenium", "FastAPI (Stub)"]
        }

# Removed __main__ block, testing should be done via test_linkedin_scraper.py 