import os
import sys
import logging
import re
from typing import List, Dict, Any, Optional

# --- Robust Imports --- 
try:
    from core.exceptions import DataProcessingError
except ImportError:
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.abspath(os.path.join(current_dir, '..'))
    if src_path not in sys.path: sys.path.insert(0, src_path)
    try:
        from core.exceptions import DataProcessingError
    except ImportError as e:
        logging.error(f"Failed to import DataProcessingError for LeadProcessor: {e}")
        DataProcessingError = Exception # Fallback

try:
    from config.config_manager import ConfigManager
except ImportError:
    # Path should be adjusted by the first block if needed
    try:
        from config.config_manager import ConfigManager
    except ImportError as e:
        logging.critical(f"CRITICAL: Failed to import ConfigManager for LeadProcessor: {e}")
        raise RuntimeError(f"LeadProcessor cannot function without ConfigManager: {e}")

try:
    # Assuming data_cleaner is in the same data_processing directory
    from .data_cleaner import clean_lead_data, clean_company_data, normalize_location, normalize_whitespace, normalize_company_name
except ImportError:
    # Fallback if running script directly and relative import fails
    try:
        from data_processing.data_cleaner import clean_lead_data, clean_company_data, normalize_location, normalize_whitespace, normalize_company_name
    except ImportError as e:
         logging.error(f"Failed to import data_cleaner functions: {e}")
         # Define dummy functions if necessary
         def clean_lead_data(data): return data
         def clean_company_data(data): return data

try:
    from data_acquisition.company_scraper import CompanyScraper
except ImportError:
    # Path should be adjusted by the first block if needed
    try:
        from data_acquisition.company_scraper import CompanyScraper
    except ImportError as e:
        logging.error(f"Failed to import CompanyScraper for LeadProcessor: {e}")
        # Define dummy if needed
        class CompanyScraper:
            def __init__(self, *args, **kwargs): pass
            def find_company_linkedin_url(self, name): return None
            def extract_company_data_from_url(self, url): return None
# --- End Robust Imports ---

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class LeadProcessor:
    """Processes raw lead data: cleans, filters, and enriches it."""

    def __init__(self, config_manager: ConfigManager, company_scraper: Optional[CompanyScraper] = None):
        """
        Initializes the LeadProcessor.
        Args:
            config_manager: Configuration manager instance.
            company_scraper: Optional CompanyScraper instance for enrichment.
                             Can be initialized here or passed in.
        """
        self.config_manager = config_manager
        # Initialize scrapers/clients needed for enrichment, or expect them to be passed
        self.company_scraper = company_scraper if company_scraper else CompanyScraper(config_manager)
        # self.lever_client = LeverClient(config_manager)
        # self.greenhouse_client = GreenhouseClient(config_manager)
        
        # Filtering criteria (can be loaded from config)
        # Improved parsing for locations like "City, ST"
        raw_locations = self.config_manager.get_config("TARGET_LOCATIONS", "New York, NY").split(',')
        self.target_locations = []
        # Process in pairs (City, ST), stripping whitespace and lowercasing
        for i in range(0, len(raw_locations), 2):
            if i + 1 < len(raw_locations):
                 city = raw_locations[i].strip().lower()
                 state = raw_locations[i+1].strip().lower()
                 self.target_locations.append(f"{city}, {state}")
            else:
                 # Handle potential odd number of elements (e.g., trailing comma)
                 last_part = raw_locations[i].strip().lower()
                 if last_part: # Avoid adding empty strings
                      logger.warning(f"Found trailing location part '{last_part}' in TARGET_LOCATIONS config. Ignoring.")
                      # Or potentially add it if single-word locations are valid? 
                      # self.target_locations.append(last_part)
        
        self.target_keywords = [kw.strip().lower() for kw in self.config_manager.get_config("TARGET_KEYWORDS", "Product Manager, Program Manager").split(',')]
        self.seniority_keywords = [kw.strip().lower() for kw in self.config_manager.get_config("SENIORITY_KEYWORDS", "Senior, Lead, Principal, Head of, Director").split(',')]
        self.mid_level_keywords = [kw.strip().lower() for kw in self.config_manager.get_config("MID_LEVEL_KEYWORDS", "Product Manager, Program Manager").split(',')]
        # Add other criteria as needed

    # --- Filtering Methods (from previous tasks) ---
    def _is_pm_in_target_location(self, lead_data: Dict[str, Any]) -> bool:
        # ... (implementation from Task 12, assuming it cleans location first) ...
        raw_location = lead_data.get("location")
        raw_title = lead_data.get("current_role")
        
        # Add None checks before calling lower() or normalize functions
        location = normalize_location(raw_location.lower()) if raw_location else ""
        title = normalize_whitespace(raw_title.lower()) if raw_title else ""
        
        logger.debug(f"_is_pm_in_target_location Check: Input Title='{raw_title}', Input Location='{raw_location}' -> Normalized Title='{title}', Normalized Location='{location}'")
        logger.debug(f"_is_pm_in_target_location: self.target_locations = {self.target_locations}") # Log target_locations

        if not location or not title:
            logger.debug("--> FAIL (is_pm): Empty normalized title or location.")
            return False
        
        # location_match = any(target_loc in location for target_loc in self.target_locations)
        # Log individual comparisons for location_match
        location_match_found = False
        for i, target_loc in enumerate(self.target_locations):
            is_match = target_loc in location
            logger.debug(f"_is_pm_in_target_location: Location check {i}: '{target_loc}' in '{location}' -> {is_match}")
            if is_match:
                location_match_found = True
                break 
        location_match = location_match_found
        
        keyword_match = any(target_kw in title for target_kw in self.target_keywords) # Uses TARGET_KEYWORDS
        
        is_senior = any(senior_kw in title for senior_kw in self.seniority_keywords)
        is_mid_level = any(mid_kw in title for mid_kw in self.mid_level_keywords) and not is_senior # Uses MID_LEVEL_KEYWORDS
        seniority_match = is_mid_level # Filter needs this to be true

        logger.debug(f"--> Checks: location_match={location_match}, keyword_match={keyword_match}, is_senior={is_senior}, is_mid_level={is_mid_level}, seniority_match={seniority_match}")
        
        result = location_match and keyword_match and seniority_match
        logger.debug(f"--> Final Result: {result}")
        return result

    def filter_leads(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filters a list of leads based on predefined criteria."""
        filtered_leads = []
        for lead in leads:
            # Apply cleaning before filtering?
            cleaned = clean_lead_data(lead) # Clean first
            if self._is_pm_in_target_location(cleaned): # Filter based on cleaned data
                filtered_leads.append(cleaned) # Store the cleaned version if it passes
        logger.info(f"Filtered {len(leads)} leads down to {len(filtered_leads)} based on criteria.")
        return filtered_leads

    # --- Enrichment Methods (Subtask 8.3) ---
    
    def enrich_lead_with_company_data(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches a single lead dictionary with company information.
        Assumes lead_data has a 'company_name' field.
        Returns the lead_data dictionary, potentially updated with a 'company_details' key.
        """
        enriched_lead = lead_data.copy()
        company_name = enriched_lead.get("company_name")
        normalized_company_name = normalize_company_name(company_name)

        if not normalized_company_name:
            logger.debug(f"No company name found for lead: {lead_data.get('name')}")
            return enriched_lead # Return original if no company name

        logger.info(f"Attempting to enrich lead '{lead_data.get('name')}' with company data for '{normalized_company_name}'")
        
        # Find company LinkedIn URL
        company_url = self.company_scraper.find_company_linkedin_url(normalized_company_name)
        
        company_details = None
        if company_url:
            # Extract company data from URL (uses cache internally)
            company_details = self.company_scraper.extract_company_data_from_url(company_url)
        else:
            logger.warning(f"Could not find LinkedIn URL for company: {normalized_company_name}")
            # Optional: Try searching without site:linkedin.com as fallback?
        
        if company_details:
            # Clean the extracted company data
            cleaned_company_details = clean_company_data(company_details)
            enriched_lead["company_details"] = cleaned_company_details
            logger.info(f"Successfully enriched lead '{lead_data.get('name')}' with company data.")
        else:
            logger.warning(f"Failed to fetch or extract company details for: {normalized_company_name}")
            enriched_lead["company_details"] = None # Indicate that enrichment was attempted but failed
            
        return enriched_lead

    def enrich_leads(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enriches a list of leads with company information."""
        enriched_leads = []
        total = len(leads)
        for i, lead in enumerate(leads):
            logger.info(f"Enriching lead {i+1}/{total}...")
            enriched_lead = self.enrich_lead_with_company_data(lead)
            enriched_leads.append(enriched_lead)
            # Optional: Add a small delay between enrichment calls if needed
            # time.sleep(0.1) 
        return enriched_leads

    # --- Scoring Methods (Subtask 8.4) ---

    def score_lead(self, lead_data: Dict[str, Any]) -> int:
        """
        Calculates a score for a lead based on various factors.
        Assumes lead_data has already been cleaned and potentially enriched.
        """
        score = 0
        raw_title = lead_data.get("current_role")
        raw_location = lead_data.get("location")
        company_details = lead_data.get("company_details")

        # Ensure title and location are strings before proceeding
        title = raw_title.lower() if raw_title else ""
        location = raw_location.lower() if raw_location else ""

        # Score based on role match (using keywords defined in init)
        # Check if title is not empty before iterating
        if title and any(target_kw in title for target_kw in (self.target_keywords or [])):
            score += 5 # Base points for core role match
            # Check again if title is not empty for nested checks
            if title and any(mid_kw in title for mid_kw in (self.mid_level_keywords or [])):
                 # Check if it's NOT senior to qualify for mid-level points
                 # Check title again here!
                 is_senior = any(senior_kw in title for senior_kw in (self.seniority_keywords or [])) if title else False
                 if not is_senior:
                     score += 3 # Additional points for desired mid-level (non-senior) match
            # elif title and any(senior_kw in title for senior_kw in self.seniority_keywords):
                 # score += 1 # Optional: Small points even for senior roles?
                 
        # Score based on location match
        # Check if location is not empty before iterating
        if location and any(target_loc in location for target_loc in (self.target_locations or [])):
            score += 4

        # Score based on successful company enrichment
        if company_details and isinstance(company_details, dict):
            score += 2 # Points for having company info
            # Optional: Add points based on company details like size or industry?
            # if company_details.get("size"):
            #     # Logic based on size, e.g., points for certain ranges
            #     score += 1 
            # if company_details.get("industry"):
            #     # Logic based on industry keywords
            #     score += 1
                
        # Add other scoring factors: mutual connections, specific company names, etc.
        # if lead_data.get("mutual_connections"): # Assuming this field exists
        #     try:
        #        connection_count = int(lead_data["mutual_connections"])
        #        score += min(connection_count, 3) # Add points for connections, capped
        #     except ValueError:
        #         pass # Ignore if not a number

        logger.debug(f"Calculated score {score} for lead '{lead_data.get('name')}'")
        return score

    # --- Full Processing Pipeline ---
    
    def process_and_filter_leads(self, raw_leads: List[Dict[str, Any]], sort_by_score: bool = True) -> List[Dict[str, Any]]:
        """
        Applies cleaning, enrichment, and filtering to a list of raw leads.
        """
        logger.info(f"Starting processing for {len(raw_leads)} raw leads.")
        
        # 1. Clean raw lead data (applies basic normalization)
        # Note: clean_lead_data currently also normalizes company_name if present
        cleaned_leads = [clean_lead_data(lead) for lead in raw_leads]
        logger.info("Step 1/4: Cleaning complete.")

        # 2. Enrich leads with company data
        enriched_leads = self.enrich_leads(cleaned_leads)
        logger.info("Step 2/4: Enrichment complete.")
        
        # 3. Filter based on criteria (uses cleaned/enriched data)
        # Note: _is_pm_in_target_location uses fields like 'location' and 'current_role' 
        # which should exist in the enriched_lead dictionaries.
        final_leads = self.filter_leads(enriched_leads) # filter_leads applies its own cleaning check currently
        logger.info("Step 3/4: Filtering complete.")

        # 4. Score the filtered leads
        scored_leads = []
        for lead in final_leads:
            # Create a copy to avoid mutating the original dict
            lead_copy = lead.copy() 
            lead_copy['score'] = self.score_lead(lead_copy) # Score the copy
            scored_leads.append(lead_copy) # Append the scored copy
        logger.info("Step 4/4: Scoring complete.")

        # 5. Optionally sort by score (descending)
        if sort_by_score:
            scored_leads.sort(key=lambda x: x.get('score', 0), reverse=True)
            logger.info("Sorted leads by score (descending).")
            
        logger.info(f"Finished processing. Final lead count: {len(scored_leads)}")
        return scored_leads


# Example Usage (requires setting up config, scrapers)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Dummy data for testing
    raw_lead_list = [
        {'name': ' Alice Smith ', 'current_role': 'Senior Product Manager', 'company_name': 'Tech Innovations Inc.', 'location': ' New York, NY ', 'email': 'alice@example.com'},
        {'name': 'Bob Johnson', 'current_role': 'Product Manager', 'company_name': ' Biz Solutions LLC ', 'location': 'San Francisco, CA'},
        {'name': 'Charlie Brown', 'current_role': 'Marketing Manager', 'company_name': 'Creative Co.', 'location': 'New York, NY'}, # Wrong role
        {'name': 'Diana Prince', 'current_role': 'Product Manager', 'company_name': 'Global Corp', 'location': ' London, UK ' } # Wrong location
    ]

    # Setup (requires .env with SCRAPING_API_KEY)
    try:
        config = ConfigManager(env_file_path="../../.env")
        company_scraper_instance = CompanyScraper(config)
    except FileNotFoundError:
        print("Error: .env file not found. Enrichment will likely fail.")
        config = ConfigManager()
        company_scraper_instance = None # Will cause issues if enrichment runs
    except Exception as e:
        print(f"Error setting up components: {e}")
        config = ConfigManager()
        company_scraper_instance = None

    if not company_scraper_instance:
        print("Company Scraper not initialized. Cannot run full processor test.")
    else:
        processor = LeadProcessor(config_manager=config, company_scraper=company_scraper_instance)
        
        print("\n--- Processing Leads ---")
        processed_leads = processor.process_and_filter_leads(raw_lead_list)
        
        print(f"\n--- Final Processed & Filtered Leads ({len(processed_leads)}) ---")
        for lead in processed_leads:
            print(lead) 