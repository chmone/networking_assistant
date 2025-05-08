import logging
import requests
import time
from typing import List, Dict, Any, Optional

# Assuming config_manager.py is in src/config/
# Adjust path if necessary, or ensure calling code handles PYTHONPATH
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
        logging.critical("Critical: ConfigManager could not be imported. LeverClient will be impaired.")
        class ConfigManager: # Dummy for basic functionality if import fails
            def __init__(self, *args, **kwargs): pass
            def get_config(self, key, default=None): return default

logger = logging.getLogger(__name__)

DEFAULT_LEVER_CACHE_EXPIRY_SECONDS = 3600 * 6 # 6 hours
LEVER_API_BASE_URL = "https://api.lever.co/v0/postings"

class LeverClient:
    """Client for fetching job postings from the Lever API."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        # Lever API typically doesn't require an API key for public postings
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_expiry_seconds = self.config_manager.get_config(
            "LEVER_CACHE_EXPIRY_SECONDS", 
            DEFAULT_LEVER_CACHE_EXPIRY_SECONDS
        )
        try:
            self.cache_expiry_seconds = int(self.cache_expiry_seconds)
        except ValueError:
            logger.warning(f"Invalid LEVER_CACHE_EXPIRY_SECONDS. Using default: {DEFAULT_LEVER_CACHE_EXPIRY_SECONDS}s")
            self.cache_expiry_seconds = DEFAULT_LEVER_CACHE_EXPIRY_SECONDS

    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        if "timestamp" not in cache_entry or "data" not in cache_entry:
            return False
        return (time.time() - cache_entry["timestamp"]) < self.cache_expiry_seconds

    def clear_cache(self, company_lever_id: Optional[str] = None):
        if company_lever_id:
            if company_lever_id in self.cache:
                del self.cache[company_lever_id]
                logger.info(f"Cleared Lever cache for {company_lever_id}.")
            else:
                logger.info(f"No cache entry found for Lever ID {company_lever_id} to clear.")
        else:
            self.cache.clear()
            logger.info("Cleared all Lever cache.")

    def get_postings(self, company_lever_id: str, role_keywords: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Fetches job postings for a given Lever company ID.
        Optionally filters by role keywords in the job title/text.
        """
        if not company_lever_id:
            logger.error("Company Lever ID is required.")
            return []

        # Check cache
        cache_key = f"{company_lever_id}_{'_'.join(sorted(role_keywords)) if role_keywords else ''}"
        if cache_key in self.cache and self._is_cache_valid(self.cache[cache_key]):
            logger.info(f"Returning cached Lever postings for {company_lever_id} (keywords: {role_keywords})")
            return self.cache[cache_key]["data"]

        api_url = f"{LEVER_API_BASE_URL}/{company_lever_id}"
        logger.info(f"Fetching Lever postings from: {api_url}")

        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            postings_data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Lever postings for {company_lever_id}: {e}")
            return []
        except ValueError as e: # Includes JSONDecodeError
            logger.error(f"Error decoding JSON from Lever API for {company_lever_id}: {e}")
            return []

        parsed_postings = []
        for post in postings_data:
            if not isinstance(post, dict): # Ensure post is a dictionary
                logger.warning(f"Skipping non-dictionary item in Lever postings: {post}")
                continue

            title = post.get("text", "")
            categories = post.get("categories", {})
            location = categories.get("location", "")
            commitment = categories.get("commitment", "") # e.g., Full-time
            hosted_url = post.get("hostedUrl", "")
            description_snippet = post.get("descriptionPlain", "")[:250] + "..." if post.get("descriptionPlain") else ""

            # Filter by role keywords if provided
            if role_keywords:
                match = False
                for keyword in role_keywords:
                    if keyword.lower() in title.lower() or keyword.lower() in post.get("descriptionPlain", "").lower():
                        match = True
                        break
                if not match:
                    continue
            
            parsed_postings.append({
                "job_title": title,
                "company_name": company_lever_id, # Or try to get from another field if available
                "job_location": location,
                "commitment": commitment,
                "job_url": hosted_url,
                "job_description_snippet": description_snippet,
                "source_api": "Lever"
            })
        
        logger.info(f"Successfully fetched and parsed {len(parsed_postings)} Lever postings for {company_lever_id}.")
        
        # Store in cache
        self.cache[cache_key] = {
            "timestamp": time.time(),
            "data": parsed_postings
        }
        logger.debug(f"Stored Lever postings in cache for {cache_key}")
        
        return parsed_postings

# For direct testing:
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # You might need to find a public Lever company ID for testing, e.g., "lever"
    # Some companies list this on their careers page or it can be found in network requests.
    test_company_lever_id = "lever" # Lever's own job board ID
    # test_company_lever_id = ""

    if not test_company_lever_id:
        print("Please set a test_company_lever_id in the script to run the LeverClient test.")
    else:
        try:
            # ConfigManager might not be strictly needed if API key isn't used for Lever
            # but good to keep consistent structure.
            config = ConfigManager(env_file_path="../../.env") 
        except FileNotFoundError:
            print("Warning: .env file not found. Using default ConfigManager.")
            config = ConfigManager()

        client = LeverClient(config_manager=config)
        
        print(f"\n--- Fetching jobs for Lever ID: {test_company_lever_id} ---")
        jobs = client.get_postings(test_company_lever_id, role_keywords=["Engineer", "Product"])
        if jobs:
            print(f"Found {len(jobs)} jobs:")
            for job in jobs[:3]: # Print first 3
                print(f"  Title: {job['job_title']}, Location: {job['job_location']}, URL: {job['job_url']}")
        else:
            print(f"No jobs found for {test_company_lever_id} with specified keywords.")

        # Test caching
        print(f"\n--- Fetching jobs for Lever ID: {test_company_lever_id} again (should be cached) ---")
        cached_jobs = client.get_postings(test_company_lever_id, role_keywords=["Engineer", "Product"])
        if cached_jobs:
            print(f"Found {len(cached_jobs)} cached jobs.")
            assert len(jobs) == len(cached_jobs), "Cached job count mismatch!"
        else:
            print("No cached jobs found.")

        client.clear_cache(test_company_lever_id)
        print("Cache cleared for test company.") 