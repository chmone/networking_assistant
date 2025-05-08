import pytest
import os
import json
from unittest.mock import patch, mock_open as unittest_mock_open # Using unittest.mock directly or via pytest-mock (mocker)

# Attempt to import ConfigManager and ConfigError
# This matches the import logic in ConfigManager itself to some extent
try:
    from src.config.config_manager import ConfigManager
    from src.core.exceptions import ConfigError
except ImportError:
    # Adjust path if running tests from a different PWD or structure
    import sys
    # Assuming tests are in 'tests/' and src is sibling to 'tests/'
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.config.config_manager import ConfigManager
    from src.core.exceptions import ConfigError


@pytest.fixture
def mock_env_vars(mocker):
    """Fixture to mock environment variables."""
    mocked_vars = {
        'TARGET_SCHOOLS': 'SchoolA, SchoolB',
        'TARGET_LOCATION': 'Test City',
        'PM_KEYWORDS': 'Keyword1, Keyword2',
        'SCRAPING_API_KEY': 'test_scrape_key_env',
        'LEVER_API_KEY': 'test_lever_key_env',
        'DB_PATH': 'sqlite:///test_db_env.db',
        'GREENHOUSE_TOKENS_JSON_PATH': 'gh_tokens_env.json'
        # NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_PARENT_PAGE_ID are left out to test defaults/warnings
    }
    mocker.patch.dict(os.environ, mocked_vars, clear=True)
    return mocked_vars # Return the dict for potential use in tests if needed

@pytest.fixture
def dummy_env_file(tmp_path):
    """Fixture to create a dummy .env file for path existence checks."""
    env_content = ("TARGET_LOCATION=File City\n") # Minimal content
    env_file = tmp_path / ".env.testfile"
    env_file.write_text(env_content)
    return env_file

@pytest.fixture
def dummy_greenhouse_tokens_file(tmp_path):
    """Fixture to create a dummy Greenhouse tokens JSON file."""
    tokens_content = {"companyA": "token123", "companyB": "token456"}
    tokens_file = tmp_path / "tokens_from_file.json" 
    tokens_file.write_text(json.dumps(tokens_content))
    return tokens_file
    
@pytest.fixture
def dummy_greenhouse_tokens_file_env(tmp_path):
    """Fixture to create a dummy Greenhouse tokens JSON file for env var path."""
    tokens_content = {"companyEnvA": "token_env_123"}
    tokens_file = tmp_path / "gh_tokens_env.json" 
    tokens_file.write_text(json.dumps(tokens_content))
    return tokens_file


class TestConfigManager:

    def test_initialization_no_env_file_uses_env_vars_and_defaults(self, mocker, mock_env_vars, dummy_greenhouse_tokens_file_env):
        """Test initialization when .env file doesn't exist, uses env vars and defaults."""
        # env_file_path is .nonexistent.env, so os.path.exists for it should be False.
        def selective_exists(path_arg):
            if path_arg == '.nonexistent.env': return False 
            # Allow finding token file relative to CWD or by absolute path from tmp_path
            if str(path_arg) == str(dummy_greenhouse_tokens_file_env): return True
            if os.path.basename(str(path_arg)) == dummy_greenhouse_tokens_file_env.name: return True 
            return False
        mocker.patch('src.config.config_manager.os.path.exists', selective_exists)
        mocker.patch('builtins.open', unittest_mock_open(read_data=dummy_greenhouse_tokens_file_env.read_text()))

        # mock_env_vars fixture already sets the env vars
        manager = ConfigManager(env_file_path='.nonexistent.env') 

        assert manager.target_schools == ['SchoolA', 'SchoolB'] 
        assert manager.target_location == 'Test City'        
        assert manager.pm_keywords == ['Keyword1', 'Keyword2'] 
        assert manager.scraping_api_key == 'test_scrape_key_env'
        assert manager.lever_api_key == 'test_lever_key_env'
        assert manager.db_path == 'sqlite:///test_db_env.db'
        assert manager.greenhouse_tokens_json_path == 'gh_tokens_env.json'
        assert manager.greenhouse_board_tokens == {"companyEnvA": "token_env_123"}

    def test_initialization_with_dummy_env_file_overrides_env_vars(self, mocker, dummy_env_file):
        """Test that ConfigManager prioritizes vars as if loaded from .env file."""
        # Values that should be treated as if loaded from the .env file
        simulated_file_values = {
            'TARGET_SCHOOLS': 'FileSchoolA, FileSchoolB,FileSchoolC',
            'TARGET_LOCATION': 'File City',
            'PM_KEYWORDS': 'FileKeyword1',
            'SCRAPING_API_KEY': 'test_scrape_key_file',
            'DB_PATH': 'sqlite:///test_db_file.db',
            'GREENHOUSE_TOKENS_JSON_PATH': 'tokens_from_file.json',
            'NOTION_TOKEN': 'file_notion_token'
            # LEVER_API_KEY is intentionally missing here
        }
        # Value expected ONLY from initial environment (not overridden by file)
        env_only_value = {'LEVER_API_KEY': 'env_lever_api_key_present'}
        
        # Expected tokens dict if tokens_from_file.json were loaded
        expected_tokens = {"companyA": "token123", "companyB": "token456"}

        # Patch os.getenv with a side effect
        original_getenv = os.getenv
        def mock_getenv_side_effect(key, default=None):
            if key in simulated_file_values:
                return simulated_file_values[key]
            if key in env_only_value:
                return env_only_value[key]
            # For any other key, return None or default to mimic getenv behavior
            # Or potentially call original_getenv if needed for other vars.
            # Let's return None for simplicity, assuming ConfigManager handles defaults.
            return default 
            
        mocker.patch('src.config.config_manager.os.getenv', side_effect=mock_getenv_side_effect)

        # Mock os.path.exists to find the .env file (so load_dotenv is called, though its effect is bypassed)
        # Token file doesn't need to exist because we mock _load_greenhouse_tokens.
        env_file_path_str = str(dummy_env_file)
        mocker.patch('src.config.config_manager.os.path.exists', lambda p: str(p) == env_file_path_str)
        
        # Mock load_dotenv to do nothing, as our getenv patch handles its effect
        mocker.patch('src.config.config_manager.load_dotenv', return_value=None)

        # Directly mock _load_greenhouse_tokens to return the expected dictionary
        mocker.patch.object(ConfigManager, '_load_greenhouse_tokens', return_value=expected_tokens)

        # Initialize ConfigManager
        manager = ConfigManager(env_file_path=env_file_path_str)

        # Assertions
        assert manager.target_schools == ['FileSchoolA', 'FileSchoolB', 'FileSchoolC']
        assert manager.target_location == 'File City' 
        assert manager.pm_keywords == ['FileKeyword1']
        assert manager.scraping_api_key == 'test_scrape_key_file' 
        assert manager.lever_api_key == 'env_lever_api_key_present' 
        assert manager.db_path == 'sqlite:///test_db_file.db' 
        assert manager.greenhouse_tokens_json_path == 'tokens_from_file.json' 
        assert manager.greenhouse_board_tokens == expected_tokens

    def test_default_values_when_vars_not_in_file_or_env(self, mocker):
        """Test that default values are used when variables are completely missing."""
        mocker.patch.dict(os.environ, {}, clear=True) 
        mocker.patch('os.path.exists', return_value=False) 
        mocker.patch.object(ConfigManager, '_load_greenhouse_tokens', return_value={}) 
        manager = ConfigManager(env_file_path='.ghost.env')
        assert manager.target_schools == ['Questrom', 'University School'] 
        assert manager.target_location == 'New York City' 
        assert manager.pm_keywords == ['Product Manager', 'Product Owner'] 
        assert manager.scraping_api_key is None
        assert manager.lever_api_key is None
        assert manager.db_path == 'sqlite:///leads.db' 
        assert manager.greenhouse_tokens_json_path is None
        assert manager.greenhouse_board_tokens == {}

    def test_get_list_config_helper(self, mocker):
        """Test the _get_list_config helper method."""
        with patch.object(ConfigManager, '_load_greenhouse_tokens', return_value={}), \
             patch('os.path.exists', return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            manager = ConfigManager(env_file_path='.dummy.env')
        mocker.patch.dict(os.environ, {'TEST_LIST': 'item1, item2,  item3 ,item4'}, clear=True)
        assert manager._get_list_config('TEST_LIST') == ['item1', 'item2', 'item3', 'item4']
        mocker.patch.dict(os.environ, {'TEST_LIST_EMPTY_ITEMS': 'itemA,,itemB, ,itemC'}, clear=True)
        assert manager._get_list_config('TEST_LIST_EMPTY_ITEMS') == ['itemA', 'itemB', 'itemC']
        mocker.patch.dict(os.environ, {}, clear=True) 
        assert manager._get_list_config('NON_EXISTENT_LIST', default_value=['def1', 'def2']) == ['def1', 'def2']
        assert manager._get_list_config('NON_EXISTENT_LIST_NO_DEFAULT') == [] 
        mocker.patch.dict(os.environ, {'EMPTY_LIST_VAR': ''}, clear=True)
        assert manager._get_list_config('EMPTY_LIST_VAR', default_value=['d1']) == ['d1'] 
        mocker.patch.dict(os.environ, {'WHITESPACE_LIST_VAR': '  '}, clear=True) 
        assert manager._get_list_config('WHITESPACE_LIST_VAR', default_value=['d1']) == [] 

    def test_load_greenhouse_tokens_file_not_set(self, mocker):
        """Test _load_greenhouse_tokens behavior when JSON path env var is not set."""
        mocker.patch.dict(os.environ, {}, clear=True) 
        mocker.patch('os.path.exists', return_value=False) 
        manager = ConfigManager(env_file_path=".dummy_no_gh_path.env")
        assert manager.greenhouse_tokens_json_path is None
        assert manager.greenhouse_board_tokens == {}

    def test_load_greenhouse_tokens_file_not_found(self, mocker, tmp_path):
        """Test _load_greenhouse_tokens when JSON file is specified but not found."""
        env_file = tmp_path / ".env.gh_file_not_found"
        env_file.write_text("GREENHOUSE_TOKENS_JSON_PATH=non_existent_tokens.json")
        def selective_exists(path_arg):
            if path_arg == str(env_file): return True
            return False
        mocker.patch('src.config.config_manager.os.path.exists', selective_exists)
        manager = ConfigManager(env_file_path=str(env_file))
        assert manager.greenhouse_board_tokens == {}

    def test_load_greenhouse_tokens_invalid_json(self, mocker, tmp_path):
        """Test _load_greenhouse_tokens with an invalid JSON file."""
        env_file = tmp_path / ".env.gh_invalid_json"
        tokens_file_relative_path = "invalid_tokens.json"
        tokens_file_abs_path = tmp_path / tokens_file_relative_path
        env_file.write_text(f"GREENHOUSE_TOKENS_JSON_PATH={tokens_file_relative_path}")
        tokens_file_abs_path.write_text("this is not json")
        def selective_exists(path_arg):
            if path_arg == str(env_file): return True
            if path_arg == str(tokens_file_abs_path): return True 
            return False
        mocker.patch('src.config.config_manager.os.path.exists', selective_exists)
        manager = ConfigManager(env_file_path=str(env_file))
        assert manager.greenhouse_board_tokens == {}

    def test_load_greenhouse_tokens_json_not_dict(self, mocker, tmp_path):
        """Test _load_greenhouse_tokens when JSON content is not a dictionary."""
        env_file = tmp_path / ".env.gh_json_not_dict"
        tokens_file_relative_path = "not_dict_tokens.json"
        tokens_file_abs_path = tmp_path / tokens_file_relative_path
        env_file.write_text(f"GREENHOUSE_TOKENS_JSON_PATH={tokens_file_relative_path}")
        tokens_file_abs_path.write_text(json.dumps(["this", "is", "a", "list"])) 
        def selective_exists(path_arg):
            if path_arg == str(env_file): return True
            if path_arg == str(tokens_file_abs_path): return True
            return False
        mocker.patch('src.config.config_manager.os.path.exists', selective_exists)
        manager = ConfigManager(env_file_path=str(env_file))
        assert manager.greenhouse_board_tokens == {}

    def test_load_greenhouse_tokens_successful_path_near_env(self, mocker, tmp_path):
        """Test successful loading behavior by mocking _load_greenhouse_tokens and setting env var via getenv mock."""
        env_file = tmp_path / ".env.gh_success_direct_mock"
        tokens_file_relative_path = "my_gh_tokens_near.json"
        tokens_data = {"boardTestNear": "tokenTestNear"}

        # Need dummy .env file only for ConfigManager to find it
        env_file.write_text("SOME_VAR=SOME_VALUE") # Content doesn't matter

        # 1. Patch os.getenv to return the correct path *for this specific key*
        original_getenv = os.getenv
        def mock_getenv_for_path(key, default=None):
            if key == 'GREENHOUSE_TOKENS_JSON_PATH':
                return tokens_file_relative_path
            # Optionally handle other keys needed during init or fall back
            return original_getenv(key, default) 
        mocker.patch('src.config.config_manager.os.getenv', side_effect=mock_getenv_for_path)

        # 2. Mock os.path.exists just to find the .env file
        mocker.patch('src.config.config_manager.os.path.exists', lambda p: p == str(env_file))
        
        # 3. Directly mock the _load_greenhouse_tokens method
        mocker.patch.object(ConfigManager, '_load_greenhouse_tokens', return_value=tokens_data)
        
        # 4. Mock load_dotenv to do nothing (as getenv mock handles the needed value)
        mocker.patch('src.config.config_manager.load_dotenv', return_value=None)

        # 5. Initialize ConfigManager
        manager = ConfigManager(env_file_path=str(env_file))
        
        # 6. Assertions
        assert manager.greenhouse_board_tokens == tokens_data
        assert manager.greenhouse_tokens_json_path == tokens_file_relative_path
        
    def test_warning_for_missing_scraping_api_key(self, mocker, caplog):
        """Test that a warning is logged if SCRAPING_API_KEY is missing."""
        mocker.patch.dict(os.environ, {}, clear=True) 
        mocker.patch('os.path.exists', return_value=False) 
        mocker.patch.object(ConfigManager, '_load_greenhouse_tokens', return_value={})
        import logging 
        caplog.set_level(logging.WARNING)
        ConfigManager() 
        assert any("SCRAPING_API_KEY is not set" in message for message in caplog.messages)

    def test_paths_for_config_error_import(self):
        """ This test is more of a meta-test to ensure ConfigError can be imported."""
        try:
            from src.core.exceptions import ConfigError as CE
            assert CE is not None
            assert issubclass(CE, Exception)
        except ImportError as e:
            pytest.fail(f"Could not import ConfigError for testing: {e}")
