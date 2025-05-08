import logging
import time
import random
import requests
import json
import serpapi # Use the main package import
from typing import Optional, Dict, Any

# Assuming config_manager.py is in src/config/
# Adjust path if necessary, or ensure calling code handles PYTHONPATH
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(current_dir, '..')))
try:
    from config.config_manager import ConfigManager
except ImportError:
    # Fallback for cases where the script is run in a different context or structure
    # This might indicate a need to better manage PYTHONPATH in the execution environment
    logging.error("Failed to import ConfigManager from config.config_manager. Attempting fallback.")
    # Add parent of current_dir (src) to sys.path if not already there
    src_path = os.path.abspath(os.path.join(current_dir, '..'))
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        from config.config_manager import ConfigManager # Try again relative to src
    except ImportError:
        logging.critical("Critical: ConfigManager could not be imported. CompanyScraper will not function.")
        # Define a dummy ConfigManager to prevent outright crashing if tests or other modules import this
        class ConfigManager:
            def __init__(self, *args, **kwargs):
                self.scraping_api_key = None
                logging.warning("Using dummy ConfigManager for CompanyScraper due to import failure.")
            def get_config(self, key, default=None):
                if key == "SCRAPING_API_KEY":
                    return self.scraping_api_key
                return default

logger = logging.getLogger(__name__)

# Define a default cache expiry for company data
DEFAULT_COMPANY_CACHE_EXPIRY_SECONDS = 3600 * 24 # 24 hours

class CompanyScraper:
    """Scrapes company information using external APIs like SerpApi."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.api_key = self.config.scraping_api_key
        if not self.api_key:
             logger.warning("SCRAPING_API_KEY not found for CompanyScraper. Company info scraping will likely fail.")
        # Initialize the client once if using the Client pattern
        self.client = serpapi.Client(api_key=self.api_key) if self.api_key else None

        # Initialize cache and expiry
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_expiry_seconds = self.config.get_config(
            "COMPANY_CACHE_EXPIRY_SECONDS",
            DEFAULT_COMPANY_CACHE_EXPIRY_SECONDS
        )
        try:
            self.cache_expiry_seconds = int(self.cache_expiry_seconds)
        except (ValueError, TypeError):
            logger.warning(f"Invalid COMPANY_CACHE_EXPIRY_SECONDS. Using default: {DEFAULT_COMPANY_CACHE_EXPIRY_SECONDS}s")
            self.cache_expiry_seconds = DEFAULT_COMPANY_CACHE_EXPIRY_SECONDS

    def get_company_info(self, company_name: str):
        """Fetches company information using SerpApi Google Search."""
        if not self.client:
             logger.error("SerpApi client not initialized due to missing API key. Cannot get company info.")
             return None
        
        logger.info(f"Searching for company info for: {company_name}")
        # Parameters for a Google search focused on the company
        params = {
            "engine": "google",
            "q": f'{company_name} company profile overview linkedin', # Query aiming for official site/LinkedIn/knowledge graph
            "gl": "us",
            "hl": "en",
            # api_key is handled by the client instance now
        }
        
        try:
            # Use the client instance to perform the search
            results = self.client.search(params) 
            logger.debug(f"SerpApi raw results for {company_name}: {json.dumps(results, indent=2)}")
            # TODO: Parse the results dictionary (knowledge graph, organic results) 
            # to extract relevant company details (website, description, industry, size, location)
            # This parsing logic needs to be implemented based on SerpApi's response structure.
            parsed_info = self._parse_company_results(results)
            return parsed_info
            
        except Exception as e:
            # Catching serpapi specific exceptions might be better if available
            # e.g., except serpapi.SerpApiException as serp_e:
            logger.exception(f"Error fetching company info for '{company_name}' from SerpApi: {e}")
            return None

    def _parse_company_results(self, results: dict):
        """Parses SerpApi results to extract company details. (Placeholder)"""
        # Placeholder implementation - needs logic based on actual SerpApi response fields
        logger.debug("Parsing SerpApi company results...")
        company_info = {}
        
        # Example: Try to get info from Knowledge Graph
        knowledge_graph = results.get('knowledge_graph', {})
        if knowledge_graph:
            company_info['name'] = knowledge_graph.get('title')
            company_info['description'] = knowledge_graph.get('description')
            # Extract other fields like website, industry if available in knowledge_graph structure
            header_info = knowledge_graph.get('header_images', [{}])[0] # Check header for website link maybe?
            if header_info.get('source') and 'http' in header_info.get('source'):
                company_info['website'] = header_info.get('source')
            # Add more parsing logic here...
            
        # Example: Fallback or supplement with top organic result
        if not company_info.get('website'):
            organic_results = results.get('organic_results', [])
            if organic_results:
                 top_result = organic_results[0]
                 # Check if the top result link seems like a company website
                 link = top_result.get('link')
                 # Very basic check - improve this heuristic
                 if link and ('linkedin.com' not in link) and ('wikipedia.org' not in link):
                     company_info['website'] = link
                 if not company_info.get('name'): # Use title if KG didn't provide name
                     company_info['name'] = top_result.get('title', '').split('-')[0].strip() 
                 if not company_info.get('description'):
                     company_info['description'] = top_result.get('snippet')
        
        # Ensure name is populated if possible
        if not company_info.get('name'):
             company_info['name'] = results.get('search_parameters', {}).get('q', 'Unknown').split(' company profile')[0]

        logger.info(f"Parsed company info: {company_info}")                
        return company_info if company_info.get('name') else None # Return None if essential info (like name) couldn't be parsed

    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Checks if a cache entry is still valid based on its timestamp."""
        if "timestamp" not in cache_entry or "data" not in cache_entry:
            return False
        return (time.time() - cache_entry["timestamp"]) < self.cache_expiry_seconds

    def clear_cache(self):
        """Clears the in-memory cache."""
        self.cache.clear()
        logger.info("Company scraper cache cleared.")

    def _make_serpapi_request(self, query: str, num_results: int = 3) -> Optional[Dict[str, Any]]:
        """Makes a request to SerpApi Google Search."""
        if not self.api_key:
            logger.error("SerpApi key not available. Cannot make request.")
            return None
        
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": str(num_results), # Number of results to return
        }
        try:
            search = serpapi.Client(api_key=self.api_key)
            results = search.search(params)
            
            if results.get("error"):
                logger.error(f"SerpApi Error: {results.get('error')}")
                return None
            if "organic_results" not in results or not results["organic_results"]:
                logger.warning(f"No organic results found for query: {query}")
                return None
                
            return results
        except Exception as e:
            logger.exception(f"Exception during SerpApi request for query '{query}': {e}")
            return None

    def find_company_linkedin_url(self, company_name: str) -> Optional[str]:
        """
        Tries to find the LinkedIn company page URL for a given company name.
        Uses Google search with site:linkedin.com/company.
        """
        query = f'{company_name} site:linkedin.com/company'
        logger.info(f"Searching for LinkedIn company page for: {company_name} with query: '{query}'")
        
        results_data = self._make_serpapi_request(query, num_results=3)
        
        if not results_data or "organic_results" not in results_data:
            logger.warning(f"No results from SerpApi for company LinkedIn URL search: {company_name}")
            return None

        for result in results_data["organic_results"]:
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            # Basic check to ensure it looks like a LinkedIn company page and matches the company name
            if "linkedin.com/company/" in link and company_name.lower() in title:
                logger.info(f"Found potential LinkedIn URL for {company_name}: {result.get('link')}")
                return result.get("link") # Return the original link with case preserved
        
        logger.warning(f"Could not confidently identify LinkedIn company URL for: {company_name} from search results.")
        return None

    def extract_company_data_from_url(self, company_linkedin_url: str) -> Optional[Dict[str, Any]]:
        """Extracts data from a given LinkedIn company page URL using Google Search on that URL."""
        logger.info(f"Attempting to extract company data for LinkedIn URL: {company_linkedin_url}")

        # Check cache first
        if company_linkedin_url in self.cache and self._is_cache_valid(self.cache[company_linkedin_url]):
            logger.info(f"Returning cached data for {company_linkedin_url}")
            return self.cache[company_linkedin_url]["data"]
        
        # Use the company_linkedin_url as the query for Google Search
        # This might yield a knowledge graph or rich snippets with company info
        results_data = self._make_serpapi_request(query=company_linkedin_url, num_results=1)
        
        if not results_data:
            logger.warning(f"No SerpApi results for query: {company_linkedin_url}")
            return None

        extracted_info = {
            "linkedin_url": company_linkedin_url,
            "name": None,
            "description": None,
            "industry": None,
            "size": None, # Employee count
            "location": None, # Headquarters
            "website": None
        }

        # Attempt to parse knowledge graph first, as it's often structured
        if "knowledge_graph" in results_data:
            kg = results_data["knowledge_graph"]
            logger.debug(f"Knowledge graph found for {company_linkedin_url}: {kg}")
            extracted_info["name"] = kg.get("title")
            extracted_info["description"] = kg.get("description")
            
            # Extract specific attributes if available in knowledge graph
            # These keys can vary greatly based on Google's KG structure
            if kg.get("type") and "organization" in kg.get("type").lower():
                extracted_info["industry"] = kg.get("industry") or kg.get("type") # Fallback to type if industry not specific
            
            extracted_info["website"] = kg.get("website")

            # Extracting size (employee count) and location from KG can be tricky
            # as keys are not standardized. We might look for specific patterns in description or attributes.
            # For now, these might remain None from KG if not directly available under common keys.
            # Example: Look for patterns if specific fields like 'Headquarters' or 'Employees' exist in KG attributes
            # attributes = kg.get("attributes") # This key might not exist or structure varies
            # if attributes:
            #     extracted_info["location"] = attributes.get("Headquarters")
            #     extracted_info["size"] = attributes.get("Employees")

        # If KG didn't provide enough, or no KG, check organic results snippets
        # (especially the first one, which should be the LinkedIn page itself)
        if not extracted_info["name"] and "organic_results" in results_data and results_data["organic_results"]:
            first_result = results_data["organic_results"][0]
            extracted_info["name"] = first_result.get("title") # Often includes company name
            if not extracted_info["description"]:
                extracted_info["description"] = first_result.get("snippet")
            # Website might also be in the displayed_link or link of the first result if it is the company site itself
            if not extracted_info["website"] and "linkedin.com" not in first_result.get("link", ""):
                 extracted_info["website"] = first_result.get("link")
        
        # Basic normalization/cleaning (can be expanded)
        if extracted_info["name"] and " - LinkedIn" in extracted_info["name"]:
            extracted_info["name"] = extracted_info["name"].replace(" - LinkedIn", "").strip()
        if extracted_info["name"] and " | LinkedIn" in extracted_info["name"]:
            extracted_info["name"] = extracted_info["name"].split(" | LinkedIn")[0].strip()

        # Further parsing from description/snippet for industry, size, location if not found in KG
        # This would require more complex NLP or regex and is prone to errors.
        # For now, we rely on KG and basic snippet parsing.
        # Example (very basic regex for employee count, needs refinement):
        # if extracted_info["description"] and not extracted_info["size"]:
        #     import re
        #     match = re.search(r'(\d[\d,]*\+?)\s+employees', extracted_info["description"], re.IGNORECASE)
        #     if match:
        #         extracted_info["size"] = match.group(1)

        logger.info(f"Extracted company info for {company_linkedin_url}: {extracted_info}")
        
        # Store in cache
        if extracted_info: # Only cache if we got some data
            self.cache[company_linkedin_url] = {
                "timestamp": time.time(),
                "data": extracted_info
            }
            logger.debug(f"Stored data in cache for {company_linkedin_url}")
            
        return extracted_info

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # This test requires a .env file in the project root with SCRAPING_API_KEY
    # Create a dummy .env for testing if it doesn't exist or you want isolated testing
    if not os.path.exists("../../.env"):
        print("Warning: ../../.env file not found. Create one with SCRAPING_API_KEY for this test to run fully.")
        # Example of creating a dummy for local test runs:
        # with open("../../.env", "w") as f:
        #     f.write("SCRAPING_API_KEY=YOUR_SERPAPI_KEY_HERE\n") # Replace with a real key for testing
        #     f.write("DB_PATH=sqlite:///test_company_scraper.db\n")

    try:
        config = ConfigManager(env_file_path="../../.env") # Adjust path to .env as needed from src/data_acquisition
    except FileNotFoundError:
        print("Error: .env file not found at expected location for ConfigManager. Please create it.")
        config = ConfigManager() # Initialize with defaults if file not found

    scraper = CompanyScraper(config_manager=config)

    if not scraper.api_key:
        print("SerpApi key not configured. Skipping API call tests.")
    else:
        test_companies = ["OpenAI", "Microsoft", "NonExistent Company XYZ123"]
        for company_name in test_companies:
            print(f"\n--- Testing company: {company_name} ---")
            url = scraper.find_company_linkedin_url(company_name)
            if url:
                print(f"Found URL: {url}")
                data = scraper.extract_company_data_from_url(url)
                if data:
                    print(f"Extracted data: {data}")
                
                # Test caching
                print(f"Attempting to extract data for {company_name} again (should be cached)...")
                data_cached = scraper.extract_company_data_from_url(url)
                if data_cached:
                    print(f"Cached data: {data_cached}")
                    assert data == data_cached, "Cached data does not match original!"
                else:
                    print(f"Failed to get cached data for {company_name}")
                    
            else:
                print(f"Could not find LinkedIn URL for {company_name}.")
            time.sleep(random.uniform(1, 2)) # Be respectful with test API calls 