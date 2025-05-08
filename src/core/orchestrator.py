import logging
import time
import random # Import the random module
from typing import List, Dict, Any, Optional

# Core component imports
from config.config_manager import ConfigManager
from database.db_manager import DatabaseManager
from database import db_utils, models
from data_acquisition.linkedin_scraper import LinkedInScraper
from data_acquisition.company_scraper import CompanyScraper
from api_integration.lever_client import LeverClient
from api_integration.greenhouse_client import GreenhouseClient
from data_processing.lead_processor import LeadProcessor
from data_processing.data_cleaner import clean_job_posting_data, normalize_company_name # Import job cleaning function

logger = logging.getLogger(__name__)

class Orchestrator:
    """Coordinates the entire data acquisition, processing, and storage workflow."""

    def __init__(self, config_path: str = "../../.env"):
        """Initialize all necessary components."""
        logger.info("Initializing Orchestrator...")
        try:
            self.config_manager = ConfigManager(env_file_path=config_path)
            self.db_manager = DatabaseManager(config=self.config_manager)
            # Ensure database schema is initialized
            self.db_manager.initialize_database()
            
            # Initialize data acquisition components
            self.linkedin_scraper = LinkedInScraper(config_manager=self.config_manager)
            self.company_scraper = CompanyScraper(config_manager=self.config_manager)
            self.lever_client = LeverClient(config_manager=self.config_manager)
            self.greenhouse_client = GreenhouseClient(config_manager=self.config_manager)
            
            # Initialize processing component
            self.lead_processor = LeadProcessor(config_manager=self.config_manager, company_scraper=self.company_scraper)
            
            logger.info("Orchestrator initialized successfully.")
            
        except FileNotFoundError:
            logger.critical(f"CRITICAL ERROR: Configuration file not found at {config_path}. Orchestrator cannot proceed.")
            # Depending on desired behavior, could raise or exit
            raise
        except Exception as e:
            logger.exception(f"Failed to initialize orchestrator components: {e}")
            raise # Re-raise critical initialization errors
            
    def run_linkedin_workflow(self, search_queries: Optional[List[Dict[str, Any]]] = None):
        """
        Runs the workflow specifically for acquiring leads from LinkedIn.
        1. Scrapes LinkedIn based on search queries.
        2. Processes (cleans, enriches, filters, scores) the leads.
        3. Stores the processed leads in the database.
        Args:
            search_queries: A list of dictionaries, each specifying search params 
                            like {'keywords': 'Product Manager', 'location': 'New York City'}.
                            If None, uses defaults from config.
        """
        logger.info("Starting LinkedIn Data Acquisition Workflow...")
        
        if search_queries is None:
            # Load default queries from config or define them here
            # Example: Search for PMs in target location AND alumni from target schools
            keywords = self.config_manager.get_config("TARGET_KEYWORDS", "Product Manager").split(',')
            location = self.config_manager.get_config("TARGET_LOCATIONS", "New York, NY").split(',')[0] # Use first location
            schools = self.config_manager.get_config("TARGET_SCHOOLS", "Questrom,University School").split(',')
            
            search_queries = []
            # Query for PMs in location
            for kw in keywords:
                 search_queries.append({"keywords": kw.strip(), "location": location.strip()})
            # Query for Alumni (no location specified for alumni search?)
            # The current LinkedIn scraper might need adjustment to search by school effectively.
            # For now, let's focus on the keyword/location search from config.
            logger.info(f"Using default search queries based on config: {search_queries}")

        # --- 1. Scraping --- 
        raw_leads = []
        total_queries = len(search_queries)
        logger.info(f"Executing {total_queries} LinkedIn search queries...")
        for i, query in enumerate(search_queries):
            keywords = query.get('keywords')
            location = query.get('location')
            logger.info(f"Running LinkedIn query {i+1}/{total_queries}: {query}")
            if keywords and location:
                 try:
                     # CORRECTION: Call the correct method on the scraper instance
                     scraped = self.linkedin_scraper.scrape_pms_by_location(keywords=keywords, location=location)
                     logger.info(f"Scraped {len(scraped)} raw leads for query: {query}")
                     raw_leads.extend(scraped)
                     time.sleep(random.uniform(2, 5)) # Delay between searches
                 except Exception as e:
                     logger.error(f"Error during LinkedIn scraping for query {query}: {e}")
            else:
                logger.warning(f"Skipping invalid search query: {query}")
        
        if not raw_leads:
            logger.warning("LinkedIn scraping yielded no raw leads. Workflow ending.")
            return
        logger.info(f"Total raw leads scraped: {len(raw_leads)}")

        # --- 2. Processing (Clean, Enrich, Filter, Score) --- 
        logger.info("Processing scraped leads...")
        try:
            processed_leads = self.lead_processor.process_and_filter_leads(raw_leads)
        except Exception as e:
            logger.exception(f"Error during lead processing: {e}")
            return # Stop workflow if processing fails
        
        if not processed_leads:
            logger.warning("Lead processing resulted in zero qualified leads. Workflow ending.")
            return
        logger.info(f"Processing complete. {len(processed_leads)} qualified leads found.")

        # --- 3. Storage --- 
        logger.info(f"Storing processed leads into database...")
        leads_added = 0
        leads_updated = 0
        leads_failed = 0
        total_processed = len(processed_leads)
        
        with self.db_manager.managed_session() as db_session:
            for i, lead_data in enumerate(processed_leads):
                logger.debug(f"Saving lead {i+1}/{total_processed}: '{lead_data.get('name')}'")
                try:
                    company_details = lead_data.pop('company_details', None)
                    lead_score = lead_data.pop('score', 0)
                    # Potentially add score as a field if Lead model supports it, or handle separately
                    
                    # --- Handle Company --- 
                    company_obj = None
                    if company_details and company_details.get('name'):
                        # Check if company exists
                        existing_company = db_utils.get_entities(db_session, models.Company, filters={'name': company_details['name']}, limit=1)
                        if existing_company:
                            company_obj = existing_company[0]
                            # Optionally update existing company details here? 
                            # db_utils.update_entity(db_session, models.Company, company_obj.id, company_details)
                        else:
                            # Create new company
                            company_obj = db_utils.create_entity(db_session, models.Company, company_details)
                    
                    # --- Handle Lead --- 
                    lead_db_data = {
                        'name': lead_data.get('name'),
                        'email': lead_data.get('email'),
                        'phone': lead_data.get('phone'),
                        # Map status if needed, assuming lead_data has a compatible status or default
                        'status': models.LeadStatus.NEW, # Default to NEW 
                        'source': lead_data.get('source', 'LinkedIn Workflow'),
                        'notes': lead_data.get('notes'),
                        'company_id': company_obj.id if company_obj else None
                        # Add other fields from lead_data that map to models.Lead
                        # e.g., 'linkedin_profile_url' if available and model has it
                    }
                    
                    # Check if lead exists (e.g., by email or profile URL if available/unique)
                    existing_lead = None
                    if lead_db_data.get('email'): # Use email as potential unique identifier
                         existing_lead = db_utils.get_entities(db_session, models.Lead, filters={'email': lead_db_data['email']}, limit=1)
                    # Add check for linkedin_profile_url if that's unique in your model
                    
                    if existing_lead:
                        # Update existing lead
                        updated = db_utils.update_entity(db_session, models.Lead, existing_lead[0].id, lead_db_data)
                        if updated:
                            leads_updated += 1
                        else:
                            leads_failed += 1 # Update failed
                    else:
                        # Create new lead
                        created = db_utils.create_entity(db_session, models.Lead, lead_db_data)
                        if created:
                            leads_added += 1
                        else:
                            leads_failed += 1 # Create failed
                
                except Exception as e:
                    logger.error(f"Error saving lead '{lead_data.get('name')}' to database: {e}")
                    leads_failed += 1
                    # No rollback here, managed_session handles it if exception bubbles up
                    # But consider finer-grained error handling if needed
                time.sleep(random.uniform(1, 3))

        logger.info(f"Database storage complete. Added: {leads_added}, Updated: {leads_updated}, Failed: {leads_failed}")
        logger.info("LinkedIn Data Acquisition Workflow Finished.")

    # Placeholder for other workflows (Company Info, Job Boards)
    def run_job_board_workflow(self, sources: List[str] = ['lever', 'greenhouse'], role_keywords: Optional[List[str]] = None):
        """
        Fetches job postings from specified sources (Lever, Greenhouse) 
        for companies defined in config mappings.
        Stores the postings in the database, linked to companies.
        Args:
            sources: List of sources to check (e.g., ['lever', 'greenhouse']).
            role_keywords: Optional list of keywords to filter jobs by.
        """
        logger.info(f"Starting Job Board Workflow for sources: {sources}...")
        
        # Load company mappings from config (e.g., LEVER_COMPANY_MAP = "CompanyName1:lever_id1,CompanyName2:lever_id2")
        lever_map_str = self.config_manager.get_config("LEVER_COMPANY_MAP", "")
        greenhouse_map_str = self.config_manager.get_config("GREENHOUSE_COMPANY_MAP", "")
        
        company_targets: Dict[str, Dict[str, str]] = {"lever": {}, "greenhouse": {}}
        try:
            for item in lever_map_str.split(','):
                if ':' in item:
                    name, lever_id = item.split(':', 1)
                    if name.strip() and lever_id.strip():
                        company_targets["lever"][name.strip()] = lever_id.strip()
            for item in greenhouse_map_str.split(','):
                if ':' in item:
                    name, board_token = item.split(':', 1)
                    if name.strip() and board_token.strip():
                        company_targets["greenhouse"][name.strip()] = board_token.strip()
        except Exception as e:
            logger.error(f"Error parsing company-job board mappings from config: {e}")

        if not any(company_targets.values()):
            logger.warning("No company mappings found in config (LEVER_COMPANY_MAP, GREENHOUSE_COMPANY_MAP). Cannot fetch job postings.")
            return

        if role_keywords is None:
            role_keywords = [kw.strip() for kw in self.config_manager.get_config("TARGET_KEYWORDS", "Product Manager").split(',')]
            logger.info(f"Using default role keywords for job boards: {role_keywords}")

        jobs_added = 0
        jobs_updated = 0 # Placeholder if update logic is added
        jobs_failed = 0

        with self.db_manager.managed_session() as db_session:
            # Fetch and store for Lever
            if "lever" in sources and company_targets["lever"]:
                logger.info(f"Processing Lever for companies: {list(company_targets['lever'].keys())}")
                for company_name, lever_id in company_targets["lever"].items():
                    try:
                        # Find corresponding company in DB (using normalized name?)
                        normalized_name = normalize_company_name(company_name)
                        db_company = db_utils.get_entities(db_session, models.Company, filters={'name': normalized_name}, limit=1)
                        company_obj = db_company[0] if db_company else None
                        if not company_obj:
                            logger.warning(f"Company '{company_name}' (normalized: '{normalized_name}') not found in DB. Skipping Lever job fetch.")
                            continue
                            
                        logger.info(f"Fetching Lever jobs for {company_name} (ID: {lever_id}) with keywords: {role_keywords}")
                        postings = self.lever_client.get_postings(lever_id, role_keywords=role_keywords)
                        logger.info(f"Found {len(postings)} relevant postings.")
                        
                        for job_data in postings:
                            cleaned_job = clean_job_posting_data(job_data)
                            job_url = cleaned_job.get('job_url')
                            if not job_url: continue # Skip if no URL
                            
                            # Check if job posting already exists for this company by URL
                            existing_job = db_utils.get_entities(
                                db_session, models.JobPosting, 
                                filters={'job_url': job_url, 'company_id': company_obj.id}, 
                                limit=1
                            )
                            
                            if not existing_job:
                                job_db_data = {
                                    'title': cleaned_job.get('job_title'),
                                    'description': cleaned_job.get('job_description_snippet'),
                                    'location': cleaned_job.get('job_location'),
                                    'job_type': None, # Lever API might not provide this directly in standard format
                                    'status': 'Open', # Assume open unless API says otherwise
                                    'company_id': company_obj.id,
                                    'job_url': job_url, 
                                    # Add other relevant fields from cleaned_job
                                }
                                created = db_utils.create_entity(db_session, models.JobPosting, job_db_data)
                                if created:
                                    jobs_added += 1
                                else:
                                    jobs_failed += 1
                            # else: Optionally update existing job details?

                    except Exception as e:
                        logger.error(f"Error processing Lever jobs for {company_name}: {e}")
                        jobs_failed += 1 # Count company-level failure
                    time.sleep(random.uniform(1, 3))

            # Fetch and store for Greenhouse
            if "greenhouse" in sources and company_targets["greenhouse"]:
                logger.info(f"Processing Greenhouse for companies: {list(company_targets['greenhouse'].keys())}")
                total_companies_gh = len(company_targets["greenhouse"])
                for i, (company_name, board_token) in enumerate(company_targets["greenhouse"].items()):
                    logger.info(f"Processing Greenhouse company {i+1}/{total_companies_gh}: {company_name}")
                    try:
                        normalized_name = normalize_company_name(company_name)
                        db_company = db_utils.get_entities(db_session, models.Company, filters={'name': normalized_name}, limit=1)
                        company_obj = db_company[0] if db_company else None
                        if not company_obj:
                            logger.warning(f"Company '{company_name}' (normalized: '{normalized_name}') not found in DB. Skipping Greenhouse job fetch.")
                            continue

                        logger.info(f"Fetching Greenhouse jobs for {company_name} (Token: {board_token}) with keywords: {role_keywords}")
                        postings = self.greenhouse_client.get_postings(board_token, role_keywords=role_keywords, content=True)
                        logger.info(f"Found {len(postings)} relevant postings.")

                        for job_data in postings:
                            cleaned_job = clean_job_posting_data(job_data)
                            job_url = cleaned_job.get('job_url')
                            if not job_url: continue

                            existing_job = db_utils.get_entities(
                                db_session, models.JobPosting, 
                                filters={'job_url': job_url, 'company_id': company_obj.id}, 
                                limit=1
                            )
                            
                            if not existing_job:
                                job_db_data = {
                                    'title': cleaned_job.get('job_title'),
                                    'description': cleaned_job.get('job_description_snippet'),
                                    'location': cleaned_job.get('job_location'),
                                    'job_type': None, # Greenhouse API might not standardize this easily
                                    'status': 'Open',
                                    'company_id': company_obj.id,
                                    'job_url': job_url,
                                }
                                created = db_utils.create_entity(db_session, models.JobPosting, job_db_data)
                                if created:
                                    jobs_added += 1
                                else:
                                    jobs_failed += 1
                    
                    except Exception as e:
                        logger.error(f"Error processing Greenhouse jobs for {company_name}: {e}")
                        jobs_failed += 1
                    time.sleep(random.uniform(1, 3))

        logger.info(f"Job Board Workflow finished. Jobs Added: {jobs_added}, Jobs Failed: {jobs_failed}")
        # logger.warning("Job Board Workflow not fully implemented yet.")
        # pass

    def run_full_workflow(self):
        logger.info("Starting Full Data Acquisition Workflow...")
        self.run_linkedin_workflow() # Add default or specific queries if needed
        self.run_job_board_workflow() # Add specific sources/companies if needed
        # Add company enrichment workflow if separate
        logger.info("Full Data Acquisition Workflow Finished.")

# Example of how to run the orchestrator
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    logger.info("Running Orchestrator Main...")
    
    # Ensure .env is in the project root (one level up from src/)
    env_file = os.path.abspath(os.path.join(current_dir, '..', '..', '.env'))
    
    try:
        orchestrator = Orchestrator(config_path=env_file)
        # Run a specific workflow
        orchestrator.run_linkedin_workflow()
        # orchestrator.run_full_workflow()
    except FileNotFoundError:
        logger.error(f"Ensure your .env configuration file exists at: {env_file}")
    except Exception as e:
        logger.exception("An error occurred during orchestrator execution.") 