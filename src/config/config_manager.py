import os
from dotenv import load_dotenv
import json
import logging

# Adjust path to import custom exceptions relative to src when run directly or as module
import sys
# Check if running as part of a package first (relevant for actual execution, not just testing)
# The try/except block handles different execution contexts more robustly than sys.path alone.
try:
    # If run as part of the 'src' package (e.g., pytest with pythonpath=src)
    from core.exceptions import ConfigError 
except ImportError:
    # If direct import fails (e.g., running config_manager.py directly for testing)
    # Fallback to path manipulation - less ideal but provides compatibility
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
    src_path = os.path.abspath(os.path.join(current_dir, '..')) # Path to src
    
    # Add src path to sys.path if not already present
    if src_path not in sys.path:
         sys.path.insert(0, src_path)
         
    try:
         from core.exceptions import ConfigError # Retry import now that src is potentially in path
    except ImportError as e:
         # Fallback if path adjustments fail - log error and use base Exception
         logging.error(f"Failed to import ConfigError via adjusted path: {e}")
         ConfigError = Exception # Use base Exception as fallback

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, env_file_path='.env'):
        """Loads configuration from environment variables and .env file."""
        
        # Ensure env_file_path exists before loading
        if not os.path.exists(env_file_path):
            logger.warning(f"Specified .env file not found at '{env_file_path}'. Relying on environment variables only.")
            # Optionally raise ConfigError if .env file is strictly required
            # raise ConfigError(f".env file not found at {env_file_path}", config_path=env_file_path)
        else:
             logger.info(f"Loading configuration from: {env_file_path}")
             load_dotenv(env_file_path)
        
        # LinkedIn search parameters
        self.target_schools = self._get_list_config('TARGET_SCHOOLS', ['Questrom', 'University School'])
        self.target_location = os.getenv('TARGET_LOCATION', 'New York City')
        self.pm_keywords = self._get_list_config('PM_KEYWORDS', ['Product Manager', 'Product Owner'])
        
        # API keys and credentials
        self.scraping_api_key = os.getenv('SCRAPING_API_KEY')
        if not self.scraping_api_key:
            logger.warning("SCRAPING_API_KEY is not set in the environment. LinkedIn scraping will not work.")
            # Optionally, raise ConfigError if this key is absolutely mandatory
            # raise ConfigError("SCRAPING_API_KEY is missing", config_path=env_file_path)
            
        self.lever_api_key = os.getenv('LEVER_API_KEY')
        
        # --- Notion Specific Config --- 
        # self.notion_token = os.getenv('NOTION_TOKEN')
        # self.notion_database_id = os.getenv('NOTION_DATABASE_ID') # ID of an *existing* database to use
        # self.notion_parent_page_id = os.getenv('NOTION_PARENT_PAGE_ID') # ID of page to create *new* database under
        # 
        # if not self.notion_token:
        #     logger.warning("NOTION_TOKEN is not set. Notion integration will be disabled.")
        # if not self.notion_database_id and not self.notion_parent_page_id:
        #      logger.warning("Neither NOTION_DATABASE_ID nor NOTION_PARENT_PAGE_ID is set. Notion database creation/export might fail or require manual setup.")
        # elif self.notion_database_id and self.notion_parent_page_id:
        #     logger.warning("Both NOTION_DATABASE_ID and NOTION_PARENT_PAGE_ID are set. The existing database ID will be preferred.")
            
        # Greenhouse config (can be complex)
        self.greenhouse_tokens_json_path = os.getenv('GREENHOUSE_TOKENS_JSON_PATH')
        self.greenhouse_board_tokens = self._load_greenhouse_tokens()

        # --- Database Config ---
        self.db_path = os.getenv('DB_PATH', 'sqlite:///leads.db')
        if self.db_path == 'sqlite:///leads.db':
            logger.warning("DB_PATH is not set, defaulting to 'sqlite:///leads.db' in the project root.")

        # Simple validation examples (can be expanded)
        if not self.target_location:
            logger.warning("TARGET_LOCATION is not set, defaulting to 'New York City'.")
            self.target_location = 'New York City' # Ensure default is set if env var was empty string

        logger.info("ConfigurationManager initialized.")

    def _get_list_config(self, env_var_name, default_value=None):
        """Helper to get a list from a comma-separated env var."""
        value_str = os.getenv(env_var_name)
        if value_str:
            # Strip whitespace from each item
            return [item.strip() for item in value_str.split(',') if item.strip()]
        return default_value if default_value is not None else []

    def _load_greenhouse_tokens(self):
        """Loads Greenhouse board tokens from a JSON file specified in env."""
        if not self.greenhouse_tokens_json_path:
            logger.info("GREENHOUSE_TOKENS_JSON_PATH not set, skipping Greenhouse token loading.")
            return {}
        
        try:
            # Try resolving path relative to env file location first, then relative to CWD
            env_dir = os.path.dirname(self.env_file_path) if hasattr(self, 'env_file_path') and os.path.dirname(self.env_file_path) else '.'
            potential_path = os.path.join(env_dir, self.greenhouse_tokens_json_path)
            
            actual_path = ""
            if os.path.exists(potential_path):
                 actual_path = potential_path
            elif os.path.exists(self.greenhouse_tokens_json_path):
                 actual_path = self.greenhouse_tokens_json_path # Assume relative to CWD if not near .env
            else:
                 logger.error(f"Greenhouse tokens JSON file not found at specified path: {self.greenhouse_tokens_json_path} (tried near .env and CWD)")
                 return {}

            logger.info(f"Loading Greenhouse tokens from: {actual_path}")
            with open(actual_path, 'r') as f:
                tokens = json.load(f)
                if not isinstance(tokens, dict):
                     logger.error(f"Greenhouse tokens file '{actual_path}' should contain a JSON object (dict).")
                     return {}
                return tokens
        except FileNotFoundError:
            logger.error(f"Greenhouse tokens JSON file not found: {actual_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from Greenhouse tokens file '{actual_path}': {e}")
            # Optionally raise ConfigError
            # raise ConfigError(f"Invalid JSON in Greenhouse tokens file", config_path=actual_path, original_exception=e)
            return {}
        except Exception as e:
            logger.exception(f"An unexpected error occurred loading Greenhouse tokens from '{actual_path}': {e}")
            return {}

# Example usage (for direct testing of this file)
if __name__ == '__main__':
    print("Testing ConfigManager...")
    # Create a dummy .env file for testing
    dummy_env_content = """
SCRAPING_API_KEY=test_scrape_key
TARGET_SCHOOLS= MIT , Harvard , Stanford 
TARGET_LOCATION=Boston
PM_KEYWORDS=Product Manager, Product Lead
# LEVER_API_KEY=
# NOTION_TOKEN=
# NOTION_PARENT_PAGE_ID=
# NOTION_DATABASE_ID= # Leave empty to test creation logic
GREENHOUSE_TOKENS_JSON_PATH=../scripts/sample_gh_tokens.json
"""
    dummy_env_path = ".env.test_config"
    with open(dummy_env_path, "w") as f:
        f.write(dummy_env_content)
        
    # Create a dummy greenhouse tokens file
    dummy_gh_path = "../scripts/sample_gh_tokens.json"
    os.makedirs(os.path.dirname(dummy_gh_path), exist_ok=True)
    with open(dummy_gh_path, "w") as f:
        json.dump({"board_a": "token123", "board_b": "token456"}, f)

    try:
        config = ConfigManager(env_file_path=dummy_env_path)
        print("\n--- Loaded Configuration ---")
        print(f"Scraping Key: {config.scraping_api_key}")
        print(f"Target Schools: {config.target_schools}")
        print(f"Target Location: {config.target_location}")
        print(f"PM Keywords: {config.pm_keywords}")
        print(f"Lever Key: {config.lever_api_key}") # Should be None
        print(f"Greenhouse Tokens Path: {config.greenhouse_tokens_json_path}")
        print(f"Greenhouse Tokens: {config.greenhouse_board_tokens}")
        
        # Test defaults if a var is missing
        # config_no_pm = ConfigManager(env_file_path='.env.no_pm') # requires creating another test file
        # print(f"\nDefault PM Keywords: {config_no_pm.pm_keywords}")
        
        # Basic assertions
        assert config.scraping_api_key == "test_scrape_key"
        assert config.target_schools == ["MIT", "Harvard", "Stanford"]
        assert config.lever_api_key is None
        assert config.greenhouse_board_tokens == {"board_a": "token123", "board_b": "token456"}
        print("\nConfigManager basic tests passed (including Notion vars).")
        
    except ConfigError as e:
        print(f"Caught expected ConfigError: {e}")
    except Exception as e:
        print(f"Caught unexpected error: {e}")
    finally:
        # Clean up dummy files
        if os.path.exists(dummy_env_path):
            os.remove(dummy_env_path)
        if os.path.exists(dummy_gh_path):
             try:
                 os.remove(dummy_gh_path)
                 # Try removing the directory if it might be empty
                 scripts_dir = os.path.dirname(dummy_gh_path)
                 if not os.listdir(scripts_dir):
                     os.rmdir(scripts_dir)
             except OSError as clean_e:
                 print(f"Warning: Could not clean up dummy files/dirs fully: {clean_e}") 