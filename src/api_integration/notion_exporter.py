import os
import sys
import logging
from datetime import datetime # Ensure datetime is imported
import time # Import time for potential delays

# Adjust path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try importing from src, adjusting based on execution context
if __package__:
    from ..config.config_manager import ConfigManager
    from .notion_client import NotionClient # Assumes notion_client is in the same directory
    from ..core.exceptions import ConfigError, DataAcquisitionError, OutputGenerationError, DataProcessingError, ApiAuthError, ApiLimitError
else:
    # Assume running from root or src is in PYTHONPATH
    try:
        from src.config.config_manager import ConfigManager
        from src.api_integration.notion_client import NotionClient
        from src.core.exceptions import ConfigError, DataAcquisitionError, OutputGenerationError, DataProcessingError, ApiAuthError, ApiLimitError
    except ImportError as e:
        logging.critical(f"Failed to import necessary modules for NotionExporter: {e}")
        raise

logger = logging.getLogger(__name__)

class NotionExporter:
    """Handles exporting leads to a Notion database, including DB creation."""

    DATABASE_TITLE = "Networking & Job Leads (Generated)"

    def __init__(self, config_manager: ConfigManager = None, notion_client: NotionClient = None):
        """Initializes the exporter with config and an optional NotionClient."""
        if config_manager is None:
            logger.info("No ConfigManager passed to NotionExporter, creating default.")
            self.config = ConfigManager()
        else:
            self.config = config_manager

        if notion_client is None:
            logger.info("No NotionClient passed to NotionExporter, creating default.")
            # This will raise ConfigError if NOTION_TOKEN is missing
            try:
                 self.client = NotionClient(config_manager=self.config)
            except ConfigError as e:
                 logger.error(f"Cannot initialize NotionExporter: {e}")
                 raise
        else:
            self.client = notion_client

        self.database_id = self.config.notion_database_id
        self.parent_page_id = self.config.notion_parent_page_id
        self._ensure_database_exists()
        logger.info(f"NotionExporter initialized. Using Database ID: {self.database_id}")

    def _get_database_schema(self):
        """Defines the target schema for the Notion database."""
        # Define property types and options
        # Colors match the task details example
        status_options = [
            {"name": "New", "color": "blue"},
            {"name": "To Contact", "color": "yellow"},
            {"name": "Contacted", "color": "orange"},
            {"name": "Responded", "color": "green"},
            {"name": "Meeting Scheduled", "color": "purple"},
            {"name": "Met", "color": "pink"},
            {"name": "No Response", "color": "gray"},
            {"name": "Not Interested", "color": "red"}
        ]
        
        # Generate school options dynamically from config if needed, or keep static
        # For dynamic options, we might need to update the DB properties if config changes
        school_options = [
             {"name": school, "color": "default"} # Use default color or cycle through available ones
             for school in sorted(list(set(self.config.target_schools))) # Get unique sorted schools
        ] if self.config.target_schools else [] 
        # Add a placeholder if no schools configured? Or omit the property?
        # if not school_options: school_options.append({"name": "N/A", "color": "default"})

        schema = {
            "Name": {"title": {}},
            "LinkedIn URL": {"url": {}},
            "Current Role": {"rich_text": {}},
            "Company": {"rich_text": {}},
            "Location": {"rich_text": {}},
            "Schools": {"multi_select": {"options": school_options}},
            "Source": {"rich_text": {}},
            "Status": {"select": {"options": status_options}},
            # Optional fields from Task 7 example, using rich_text for flexibility
            "Company Size": {"rich_text": {}}, 
            "Company Focus": {"rich_text": {}}, 
            "Open Roles URL": {"url": {}}, # Changed from Open Roles to be more specific 
            "Date Added": {"date": {}},
            "Notes": {"rich_text": {}}
        }
        return schema

    def _ensure_database_exists(self):
        """
        Checks if the database ID is set. If not, tries to create the database.
        Updates self.database_id if creation is successful.
        Raises errors if creation fails or prerequisites are missing.
        """
        if self.database_id:
            logger.info(f"Using existing Notion Database ID: {self.database_id}")
            # Optional: Could add a check here to verify the database exists and has the expected schema
            # try:
            #     db_info = self.client._make_request('GET', f'/databases/{self.database_id}')
            #     logger.info(f"Successfully retrieved existing database '{db_info.get('title', [{}])[0].get('plain_text')}'")
            #     # Add schema validation logic here if needed
            # except DataAcquisitionError as e:
            #     logger.error(f"Failed to verify existing database {self.database_id}: {e}")
            #     raise OutputGenerationError(f"Failed to access configured Notion Database ID {self.database_id}", original_exception=e)
            return

        logger.info("No existing NOTION_DATABASE_ID found in config.")
        
        if not self.parent_page_id:
            msg = "NOTION_DATABASE_ID is not set, and NOTION_PARENT_PAGE_ID is required to create a new database, but it's also missing."
            logger.error(msg)
            raise ConfigError(msg)
        
        logger.info(f"Attempting to create a new Notion database under Parent Page ID: {self.parent_page_id}")
        
        db_payload = {
            "parent": {"type": "page_id", "page_id": self.parent_page_id},
            "title": [{
                "type": "text",
                "text": {"content": self.DATABASE_TITLE}
            }],
            "properties": self._get_database_schema()
            # We can add icon/cover later if desired
            # "icon": { "type": "emoji", "emoji": "👤" }
        }
        
        try:
            created_db_info = self.client.create_database(db_payload)
            if created_db_info and 'id' in created_db_info:
                new_db_id = created_db_info['id']
                logger.info(f"Successfully created new Notion database '{self.DATABASE_TITLE}' with ID: {new_db_id}")
                self.database_id = new_db_id
                # IMPORTANT: User needs to update their .env file or config with this new ID 
                # if they want to use it directly next time without specifying the parent page.
                print(f"\n*** ACTION REQUIRED ***")
                print(f"Notion database created successfully.")
                print(f"To use this database directly in the future, update your .env file with:")
                print(f"NOTION_DATABASE_ID={new_db_id}\n")
            else:
                msg = f"Failed to create Notion database. API response did not contain an ID. Response: {created_db_info}"
                logger.error(msg)
                raise OutputGenerationError(msg)
                
        except (DataAcquisitionError, ApiAuthError, ApiLimitError) as e:
            msg = f"Failed to create Notion database due to API error: {e}"
            logger.error(msg)
            raise OutputGenerationError(msg, original_exception=e) from e
        except Exception as e:
            msg = f"An unexpected error occurred during Notion database creation: {e}"
            logger.exception(msg)
            raise OutputGenerationError(msg, original_exception=e) from e

    def _format_lead_for_notion(self, lead: dict) -> dict:
        """Formats a lead dictionary into the payload for creating a Notion page."""
        properties = {}

        # --- Map lead fields to Notion properties --- 
        
        # Title property (Name)
        if lead.get('lead_name'):
            properties["Name"] = {"title": [{"text": {"content": lead['lead_name']}}]}
        else:
            properties["Name"] = {"title": [{"text": {"content": "Unknown Lead Name"}}]} # Default if name is missing

        # URL property (LinkedIn URL)
        if lead.get('linkedin_profile_url'):
            properties["LinkedIn URL"] = {"url": lead['linkedin_profile_url']}
        
        # Rich Text properties
        for key, prop_name in [
            ('current_role', 'Current Role'),
            ('company_name', 'Company'),
            ('location', 'Location'),
            ('source_of_lead', 'Source'),
            ('company_size', 'Company Size'), # Assuming these optional fields might exist
            ('company_product_focus', 'Company Focus'),
            ('notes', 'Notes') # If we add notes later
        ]:
            if lead.get(key):
                properties[prop_name] = {"rich_text": [{"text": {"content": str(lead[key])}}]}
                
        # Multi-select property (Schools)
        schools = lead.get('alma_mater_match', [])
        if isinstance(schools, str): # Ensure it's a list
            schools = [schools] if schools else []
        if schools:
            # Ensure options exist in the schema or handle gracefully
            # For simplicity, we assume schema generation included known schools.
            # Notion API might error if an option doesn't exist; alternatively, create options on the fly (more complex).
            valid_school_options = []
            db_schema = self._get_database_schema() # Get current schema def
            allowed_school_names = [opt['name'] for opt in db_schema.get("Schools", {}).get("multi_select", {}).get("options", [])]
            for school in schools:
                 if school in allowed_school_names:
                      valid_school_options.append({"name": school})
                 else:
                      logger.warning(f"School '{school}' for lead '{lead.get('lead_name')}' not found in DB schema options. Skipping.")
            if valid_school_options:
                 properties["Schools"] = {"multi_select": valid_school_options}
        
        # Select property (Status) - Default to 'New'
        properties["Status"] = {"select": {"name": "New"}}
        
        # Date property (Date Added)
        date_added_str = lead.get('date_added')
        if date_added_str: 
            try:
                # Ensure it's just the date part for Notion date property if it includes time
                date_obj = datetime.fromisoformat(date_added_str.split('T')[0])
                properties["Date Added"] = {"date": {"start": date_obj.strftime('%Y-%m-%d')}}
            except ValueError:
                logger.warning(f"Could not parse date_added '{date_added_str}' for lead '{lead.get('lead_name')}'. Skipping date property.")
        else:
            # Add current date if missing
            properties["Date Added"] = {"date": {"start": datetime.now().strftime('%Y-%m-%d')}}
            
        # URL property (Open Roles URL) - Assuming lead dict might have 'open_roles_url' key
        if lead.get('open_roles_url'):
             properties["Open Roles URL"] = {"url": lead['open_roles_url']}
             
        # Construct the final payload for the create_page API call
        page_payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }
        return page_payload

    def _check_if_lead_exists(self, lead: dict) -> str | None:
        """
        Queries the Notion database to check if a lead with the same LinkedIn URL already exists.
        Returns the existing page ID if found, otherwise None.
        Uses the 'LinkedIn URL' property for matching.
        """
        linkedin_url = lead.get('linkedin_profile_url')
        if not self.database_id or not linkedin_url:
            # Cannot check without DB ID or URL
            return None 

        logger.debug(f"Checking for existing lead with URL: {linkedin_url} in DB {self.database_id}")
        
        # Notion API filter for exact URL match on the 'LinkedIn URL' property
        # Ensure the property name "LinkedIn URL" matches your schema exactly.
        filter_payload = {
            "property": "LinkedIn URL",
            "url": {
                "equals": linkedin_url
            }
        }
        
        try:
            # Query the database
            # Note: Querying might also need retry logic, but it's handled by the client's _make_request
            results = self.client.query_database(self.database_id, filter_payload=filter_payload, page_size=1)
            
            if results and results.get('results'):
                existing_page_id = results['results'][0]['id']
                logger.info(f"Duplicate lead found: URL {linkedin_url} already exists with Page ID {existing_page_id}")
                return existing_page_id
            else:
                logger.debug(f"No existing lead found for URL: {linkedin_url}")
                return None
        except (DataAcquisitionError, Exception) as e:
            # Log error but don't stop the whole export; proceed as if not found
            logger.error(f"Error checking for duplicate lead ({linkedin_url}): {e}. Assuming lead does not exist.")
            return None

    def export_lead_to_notion(self, lead: dict, check_duplicate=True):
        """
        Formats a single lead and creates a new page in the Notion database.
        Optionally checks for duplicates based on LinkedIn URL before creating.
        Returns the ID of the created/existing page or raises an error.
        """
        if not self.database_id:
            raise OutputGenerationError("Cannot export lead: Notion Database ID is not configured or available.")
        if not isinstance(lead, dict):
             raise DataProcessingError(f"Invalid lead data format: Expected dict, got {type(lead)}")

        # --- Duplicate Check (Subtask 7.4) ---
        if check_duplicate:
            existing_page_id = self._check_if_lead_exists(lead)
            if existing_page_id:
                 # Optional: Could update the existing page here if needed
                 # logger.info(f"Updating existing page {existing_page_id} for lead '{lead.get('lead_name')}'...")
                 # update_payload = self._format_lead_for_notion(lead)['properties'] # Get properties part
                 # try:
                 #     self.client.update_page_properties(existing_page_id, update_payload)
                 # except Exception as update_e:
                 #     logger.error(f"Failed to update existing page {existing_page_id}: {update_e}")
                 return existing_page_id # Return existing ID, indicating skipped creation
        # --- End Duplicate Check ---

        logger.debug(f"Formatting lead '{lead.get('lead_name')}' for Notion export.")
        page_payload = self._format_lead_for_notion(lead)
        
        logger.info(f"Creating Notion page for lead '{lead.get('lead_name')}' in DB {self.database_id}...")
        try:
            created_page_info = self.client.create_page(page_payload)
            if created_page_info and 'id' in created_page_info:
                page_id = created_page_info['id']
                logger.info(f"Successfully created Notion page for lead '{lead.get('lead_name')}' with Page ID: {page_id}")
                return page_id
            else:
                 logger.error(f"Notion page creation API call succeeded but response lacked an ID. Response: {created_page_info}")
                 raise OutputGenerationError(f"Notion page creation response missing ID for lead {lead.get('lead_name')}")
        except (DataAcquisitionError, ApiAuthError, ApiLimitError) as e:
            logger.error(f"Failed to create Notion page for lead '{lead.get('lead_name')}': {e}")
            raise OutputGenerationError(f"Failed to export lead '{lead.get('lead_name')}' to Notion", original_exception=e) from e
        except Exception as e:
            logger.exception(f"Unexpected error creating Notion page for lead '{lead.get('lead_name')}': {e}")
            raise OutputGenerationError(f"Unexpected error exporting lead '{lead.get('lead_name')}' to Notion", original_exception=e) from e

    def export_leads_to_notion(self, leads: list, check_duplicates=True):
        """
        Exports multiple leads to the Notion database, handling individual errors
        and optionally checking for duplicates.
        Returns a list of results (success/failure/skipped status for each lead).
        """
        if not self.database_id:
             logger.error("Cannot export to Notion: Database ID is not available.")
             return [] 
             
        results = []
        total_leads = len(leads)
        success_count = 0
        skipped_count = 0
        logger.info(f"Starting batch export of {total_leads} leads to Notion DB {self.database_id} (Check Duplicates: {check_duplicates})...")
        
        for i, lead in enumerate(leads):
            lead_name = lead.get('lead_name', f'Unknown Lead #{i+1}')
            try:
                # Pass check_duplicate flag to single export method
                page_id_or_existing_id = self.export_lead_to_notion(lead, check_duplicate=check_duplicates)
                
                # Determine status based on whether it returned an ID from creation or duplicate check
                # A simple check: If the lead has the *same* linkedin URL as used in the check, 
                # and the ID returned matches an *existing* one found by the check, it was a duplicate.
                # This distinction is slightly tricky without modifying _check_if_lead_exists further.
                # Let's simplify: if check_duplicates was True and an ID was returned without error, 
                # it either succeeded or was skipped. We need a better way to know which.
                
                # Modification: _check_if_lead_exists returns ID if found, None otherwise.
                # export_lead_to_notion now returns existing ID if check finds one.
                # So, we need to call the check *before* export_lead_to_notion in the loop.
                
                existing_page_id = None
                if check_duplicates:
                     existing_page_id = self._check_if_lead_exists(lead)
                
                if existing_page_id:
                     logger.info(f"Skipping duplicate lead: {lead_name} (Page ID: {existing_page_id})")
                     results.append({"lead_name": lead_name, "page_id": existing_page_id, "status": "skipped_duplicate"})
                     skipped_count += 1
                else:
                    # If no duplicate, proceed to create (don't need to check again inside)
                    page_id = self.export_lead_to_notion(lead, check_duplicate=False)
                    results.append({"lead_name": lead_name, "page_id": page_id, "status": "success"})
                    success_count += 1
                    # Optional delay
                    time.sleep(0.3) # Add a small delay to be nice to the API

            except (OutputGenerationError, DataProcessingError, Exception) as e:
                logger.error(f"Failed to export lead {i+1}/{total_leads} ('{lead_name}') to Notion: {e}")
                results.append({"lead_name": lead_name, "error": str(e), "status": "failed"})
        
        logger.info(f"Batch Notion export finished. Success: {success_count}, Skipped (Duplicate): {skipped_count}, Failed: {total_leads - success_count - skipped_count}/{total_leads} leads.")
        failed_count = total_leads - success_count - skipped_count
        if failed_count > 0:
             logger.warning(f"{failed_count} leads failed to export to Notion. See logs for details.")
             
        return results

# Example Usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    print("Testing NotionExporter...")
    
    # Assumes .env in project root with NOTION_TOKEN and NOTION_PARENT_PAGE_ID (for creation)
    # OR NOTION_TOKEN and NOTION_DATABASE_ID (for using existing)
    try:
        # Test Case 1: Create new DB (Ensure NOTION_DATABASE_ID is commented out/deleted in .env)
        print("\n--- Testing DB Creation (Requires NOTION_PARENT_PAGE_ID) ---")
        config_create = ConfigManager() # Reload config
        if config_create.notion_parent_page_id and not config_create.notion_database_id:
            try:
                 exporter_create = NotionExporter(config_manager=config_create)
                 print(f"Exporter initialized, using Database ID: {exporter_create.database_id}")
                 print("(Manual verification needed in Notion if DB was created)")
            except (ConfigError, OutputGenerationError, ApiAuthError, ApiLimitError) as e:
                 print(f"Exporter initialization failed during creation test: {e}")
        else:
            print("Skipping DB creation test: NOTION_PARENT_PAGE_ID not set or NOTION_DATABASE_ID is set.")
            
        # Test Case 2: Use existing DB (Requires NOTION_DATABASE_ID)
        print("\n--- Testing with Existing DB ID (Requires NOTION_DATABASE_ID) ---")
        config_existing = ConfigManager() # Reload
        if config_existing.notion_database_id:
             try:
                 exporter_existing = NotionExporter(config_manager=config_existing)
                 print(f"Exporter initialized with existing Database ID: {exporter_existing.database_id}")
                 # Add a call to export_leads here later to test further
             except (ConfigError, OutputGenerationError, ApiAuthError, ApiLimitError) as e:
                  print(f"Exporter initialization failed for existing DB test: {e}")
        else:
            print("Skipping existing DB test: NOTION_DATABASE_ID not set.")
            
    except ConfigError as e:
         print(f"Config Error during setup: {e}")
    except Exception as e:
         print(f"Unexpected error during testing: {e}")

    print("\nNotionExporter tests finished.") 