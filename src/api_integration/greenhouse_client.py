import logging
import requests
import time
from typing import List, Dict, Any, Optional

# Assuming config_manager.py is in src/config/
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(current_dir, '..')))
try:
    from config.config_manager import ConfigManager
except ImportError:
    logging.error("Failed to import ConfigManager from config.config_manager. Attempting fallback.")
    src_path = os.path.abspath(os.path.join(current_dir, '..'))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        from config.config_manager import ConfigManager
    except ImportError:
        logging.critical("Critical: ConfigManager could not be imported. GreenhouseClient will be impaired.")
        class ConfigManager: # Dummy
            def __init__(self, *args, **kwargs): pass
            def get_config(self, key, default=None): return default

logger = logging.getLogger(__name__)

DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS = 3600 * 6 # 6 hours
GREENHOUSE_API_BASE_URL_V1 = "https://boards-api.greenhouse.io/v1/boards" # For public job boards
# Note: Some companies might use a different base URL or structure if using embedded jobs feeds.
# e.g., https://api.greenhouse.io/v1/boards/{board_token}/embed/jobs

class GreenhouseClient:
    """Client for fetching job postings from the Greenhouse API."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_expiry_seconds = self.config_manager.get_config(
            "GREENHOUSE_CACHE_EXPIRY_SECONDS", 
            DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS
        )
        try:
            self.cache_expiry_seconds = int(self.cache_expiry_seconds)
        except ValueError:
            logger.warning(f"Invalid GREENHOUSE_CACHE_EXPIRY_SECONDS. Using default: {DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS}s")
            self.cache_expiry_seconds = DEFAULT_GREENHOUSE_CACHE_EXPIRY_SECONDS

    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        if "timestamp" not in cache_entry or "data" not in cache_entry:
            return False
        return (time.time() - cache_entry["timestamp"]) < self.cache_expiry_seconds

    def clear_cache(self, board_token: Optional[str] = None):
        cache_key_prefix = board_token if board_token else ""
        if board_token:
            # Need to remove all keys starting with this board_token prefix due to keyword variations
            keys_to_delete = [k for k in self.cache if k.startswith(board_token)]
            for k_del in keys_to_delete:
                del self.cache[k_del]
            if keys_to_delete:
                logger.info(f"Cleared Greenhouse cache for board token {board_token}.")
            else:
                logger.info(f"No cache entries found for Greenhouse board token {board_token} to clear.")
        else:
            self.cache.clear()
            logger.info("Cleared all Greenhouse cache.")

    def get_postings(self, board_token: str, role_keywords: Optional[List[str]] = None, content: bool = True) -> List[Dict[str, Any]]:
        """
        Fetches job postings for a given Greenhouse board token.
        Optionally filters by role keywords in the job title/content.
        Args:
            board_token: The company's Greenhouse board token (usually their name or a variation).
            role_keywords: Optional list of keywords to filter job titles/content.
            content: Boolean, whether to fetch full job content (description). Defaults to True.
                     Setting to False fetches only a list of jobs with minimal details.
        """
        if not board_token:
            logger.error("Greenhouse board token is required.")
            return []

        cache_key = f"{board_token}_{'_'.join(sorted(role_keywords)) if role_keywords else ''}_{content}"
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
            logger.info(f"Returning cached Greenhouse postings for {board_token} (keywords: {role_keywords}, content: {content})")
            return self.cache[cache_key]["data"]

        # Endpoint for all jobs on a board (summary)
        # To get full description for each, you might need to call /jobs/{job_id}?questions=true as well if content=True
        # Or, some boards provide everything in the /jobs endpoint if ?content=true is supported or by default.
        # Let's try with ?content=true first.
        api_url = f"{GREENHOUSE_API_BASE_URL_V1}/{board_token}/jobs?content=true" if content else f"{GREENHOUSE_API_BASE_URL_V1}/{board_token}/jobs"
        logger.info(f"Fetching Greenhouse postings from: {api_url}")

        try:
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Greenhouse postings for {board_token}: {e}")
            return []
        except ValueError as e: # Includes JSONDecodeError
            logger.error(f"Error decoding JSON from Greenhouse API for {board_token}: {e}")
            return []

        # The response structure is typically {"jobs": [...]} for the list endpoint
        postings_data = response_data.get("jobs", [])
        if not isinstance(postings_data, list):
            logger.error(f"Greenhouse API for {board_token} did not return a list of jobs in the 'jobs' key. Data: {response_data}")
            return []

        parsed_postings = []
        for post in postings_data:
            if not isinstance(post, dict):
                logger.warning(f"Skipping non-dictionary item in Greenhouse postings: {post}")
                continue

            title = post.get("title", "")
            job_id = post.get("id")
            absolute_url = post.get("absolute_url", "")
            location_name = post.get("location", {}).get("name") if isinstance(post.get("location"), dict) else post.get("location", "")
            job_content_html = post.get("content", "") # Full HTML content if content=true was used
            
            # Basic plain text conversion from HTML, can be improved with BeautifulSoup
            description_snippet = job_content_html[:500].strip() + "..." if job_content_html else ""
            # A more robust way to get plain text:
            # from bs4 import BeautifulSoup
            # if job_content_html:
            #     soup = BeautifulSoup(job_content_html, "html.parser")
            #     description_snippet = soup.get_text(separator=' ', strip=True)[:250] + "..."
            # else:
            #     description_snippet = ""

            # Filter by role keywords
            if role_keywords:
                match = False
                text_to_search = title + " " + (job_content_html if job_content_html else "")
                for keyword in role_keywords:
                    if keyword.lower() in text_to_search.lower():
                        match = True
                        break
                if not match:
                    continue
            
            parsed_postings.append({
                "job_id": job_id,
                "job_title": title,
                "company_name": board_token, # The board_token often represents the company
                "job_location": location_name,
                "job_url": absolute_url,
                "job_description_snippet": description_snippet,
                "source_api": "Greenhouse"
            })
        
        logger.info(f"Successfully fetched and parsed {len(parsed_postings)} Greenhouse postings for {board_token}.")
        
        self.cache[cache_key] = {
            "timestamp": time.time(),
            "data": parsed_postings
        }
        logger.debug(f"Stored Greenhouse postings in cache for {cache_key}")
        
        return parsed_postings

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Find a public Greenhouse board token for testing (e.g., from a company's career page URL)
    # Example: For Greenhouse Software itself, it's "greenhouse"
    test_board_token = "greenhouse" 
    # test_board_token = ""

    if not test_board_token:
        print("Please set a test_board_token in the script to run the GreenhouseClient test.")
    else:
        config = ConfigManager() # Dummy config, Greenhouse client doesn't use it much beyond cache settings
        client = GreenhouseClient(config_manager=config)
        
        print(f"\n--- Fetching jobs for Greenhouse board: {test_board_token} (with content) ---")
        jobs = client.get_postings(test_board_token, role_keywords=["Engineer", "Product"], content=True)
        if jobs:
            print(f"Found {len(jobs)} jobs:")
            for job in jobs[:3]:
                print(f"  Title: {job['job_title']}, Location: {job['job_location']}, URL: {job['job_url']}")
        else:
            print(f"No jobs found for {test_board_token} with specified keywords.")

        # Test caching
        print(f"\n--- Fetching jobs for Greenhouse board: {test_board_token} again (should be cached) ---")
        cached_jobs = client.get_postings(test_board_token, role_keywords=["Engineer", "Product"], content=True)
        if cached_jobs:
            print(f"Found {len(cached_jobs)} cached jobs.")
            assert len(jobs) == len(cached_jobs), "Cached job count mismatch!"

        client.clear_cache(test_board_token) 