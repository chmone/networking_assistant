import argparse
import logging
import os
import sys # Import sys for exit
from datetime import datetime

# --- Project Module Imports ---
# Ensure src directory is in path for running main.py from root
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from config.config_manager import ConfigManager
from data_acquisition.linkedin_scraper import LinkedInScraper
from data_processing.lead_processor import LeadProcessor
from output_generation.text_exporter import TextFileExporter
# Import other exporters like NotionExporter when implemented
# Import custom exceptions
from core.exceptions import PersonalResearchAgentError, ConfigError, DataAcquisitionError, DataProcessingError, OutputGenerationError

# --- Basic Logging Setup --- 
# Create logs directory if it doesn't exist
log_dir = "logs"
try:
    os.makedirs(log_dir, exist_ok=True)
except OSError as e:
    print(f"Warning: Could not create logs directory '{log_dir}': {e}")
    log_dir = "." # Fallback

log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO, # Default level, can be overridden by args
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler() # Also print to console
    ]
)
logger = logging.getLogger(__name__) # Get root logger or specific app logger

# --- Argument Parsing (Subtask 6.1) --- 
def parse_arguments():
    """Parses command line arguments for the application."""
    parser = argparse.ArgumentParser(description='Personal Research Agent for Job and Networking Leads')
    
    parser.add_argument(
        '--config', 
        type=str, 
        default='.env', 
        help='Path to the environment configuration file (default: .env in CWD).'
    )
    parser.add_argument(
        '--output-txt', 
        type=str, 
        default=None, 
        help='Optional: Filename for the text export. If not provided, a timestamped name will be generated.'
    )
    # Add arguments for Notion/Other exports later if needed
    # parser.add_argument('--export-notion', action='store_true', help='Export leads to Notion database.')
    
    parser.add_argument(
        '-v', '--verbose', 
        action='store_true', 
        help='Enable verbose logging (DEBUG level).'
    )

    args = parser.parse_args()
    return args

# --- Main Application Logic (Subtask 6.2 - Core Orchestration) --- 
def run_application(args):
    """Orchestrates the main application workflow.""" 
    logger.info("Application starting...")
    logger.info(f"Arguments received: {args}")

    config = None # Initialize config to None
    try:
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG) 
            logger.debug("Verbose logging enabled.")

        # --- Configuration Loading ---
        logger.info(f"Loading configuration from: {args.config}")
        config = ConfigManager(env_file_path=args.config)
        logger.info("Configuration loaded successfully.")
        # Note: ConfigError might be raised here if ConfigManager is modified to do so

        # --- Component Initialization ---
        logger.debug("Initializing components...")
        scraper = LinkedInScraper(config)
        processor = LeadProcessor(config)
        exporter_txt = TextFileExporter()
        logger.debug("Components initialized.")

        # --- Data Acquisition ---
        logger.info("Starting data acquisition...")
        all_leads = []
        if config.target_schools:
            for school in config.target_schools:
                logger.info(f"Scraping alumni from: {school}")
                # scrape_alumni_by_school catches its own DataAcquisitionError and returns []
                # It doesn't raise it further up by default, but could be changed.
                school_leads = scraper.scrape_alumni_by_school(school)
                logger.info(f"Found {len(school_leads)} potential leads from {school}")
                all_leads.extend(school_leads)
        else:
             logger.warning("No target schools defined in configuration.")

        # Scrape PMs in target location
        if config.target_location and config.pm_keywords:
            logger.info(f"Scraping PMs in: {config.target_location}")
            pm_leads = scraper.scrape_pms_by_location(config.target_location, config.pm_keywords)
            logger.info(f"Found {len(pm_leads)} potential PM leads in {config.target_location}")
            all_leads.extend(pm_leads)
        else:
             logger.warning("Target location or PM keywords not defined; skipping PM search.")
        logger.info(f"Data acquisition complete. Total potential leads found: {len(all_leads)}")

        # --- Data Processing ---
        logger.info(f"Starting data processing for {len(all_leads)} leads...")
        # These methods now raise DataProcessingError on internal failure
        normalized_leads = processor.normalize_lead_data(all_leads)
        filtered_leads = processor.filter_leads(normalized_leads)
        logger.info(f"Data processing complete. {len(filtered_leads)} leads after filtering and normalization.")

        # --- Output Generation ---
        logger.info("Starting output generation...")
        if filtered_leads:
            # Text Export - This method now raises OutputGenerationError on failure
            # output_file = exporter_txt.export_leads_to_txt(filtered_leads, args.output_txt)
            # logger.info(f"Text export successful: {output_file}")
            # Add other export calls here
            logger.info("Output generation step. Currently no primary output defined. Database integration pending.")
        else:
            logger.info("No filtered leads to export.")
        logger.info("Output generation complete.")

    # --- Custom Exception Handling ---
    except ConfigError as e:
        logger.critical(f"Configuration Error: {e}", exc_info=True)
        sys.exit(2) # Specific exit code for config errors
    except DataAcquisitionError as e:
        # Includes ApiLimitError, ApiAuthError, etc.
        logger.critical(f"Data Acquisition Error: {e}", exc_info=True)
        sys.exit(3) # Specific exit code for data acquisition errors
    except DataProcessingError as e:
        logger.critical(f"Data Processing Error: {e}", exc_info=True)
        sys.exit(4) # Specific exit code for processing errors
    except OutputGenerationError as e:
        logger.critical(f"Output Generation Error: {e}", exc_info=True)
        sys.exit(5) # Specific exit code for output errors
    except PersonalResearchAgentError as e:
        # Catch any other app-specific error that wasn't more specific
        logger.critical(f"Application Error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        # Catch any truly unexpected errors
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Application finished successfully.")

# --- Entry Point --- 
if __name__ == "__main__":
    # Logger is configured at the top level now
    try:
        arguments = parse_arguments()
        run_application(arguments)
    except Exception as e:
        # This catches errors during arg parsing or unexpected issues before run_application starts
        logger.critical(f"An unexpected error occurred at the top level: {e}", exc_info=True)
        sys.exit(1) 