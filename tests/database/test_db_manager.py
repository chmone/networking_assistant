# Initial test file for db_manager.py
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from src.database.db_manager import DatabaseManager
# Assuming ConfigManager is in src.config.config_manager
# For testing, we create a mock ConfigManager directly

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.db_path = "sqlite:///:memory:"
    return config

class TestDatabaseManagerInitialization:
    @patch('src.database.db_manager.create_engine')
    @patch('src.database.db_manager.sessionmaker')
    def test_init_connect_success(self, mock_sessionmaker, mock_create_engine, mock_config):
        mock_engine_instance = MagicMock()
        mock_create_engine.return_value = mock_engine_instance
        mock_session_factory_instance = MagicMock()
        mock_sessionmaker.return_value = mock_session_factory_instance

        db_manager = DatabaseManager(config=mock_config)

        mock_create_engine.assert_called_once_with(mock_config.db_path)
        assert db_manager.engine is mock_engine_instance
        mock_sessionmaker.assert_called_once_with(autocommit=False, autoflush=False, bind=mock_engine_instance)
        assert db_manager.Session is mock_session_factory_instance

    @patch('src.database.db_manager.create_engine', side_effect=SQLAlchemyError("Engine creation failed"))
    def test_init_connect_engine_creation_fails(self, mock_create_engine_fails, mock_config):
        # Expect ConnectionError because _connect now raises it when create_engine fails
        with pytest.raises(ConnectionError, match="Database connection/setup failed: Engine creation failed"):
            # Instantiation should happen INSIDE the raises block
            db_manager = DatabaseManager(config=mock_config) 
        
        # Assertions after the expected exception
        mock_create_engine_fails.assert_called_once_with(mock_config.db_path)
        # db_manager instance might not be fully assigned if __init__ raised early
        # Can't reliably check db_manager.engine is None here.

    @patch('src.database.db_manager.create_engine') # Successful engine creation
    @patch('src.database.db_manager.sessionmaker', side_effect=Exception("Sessionmaker failed"))
    def test_init_connect_sessionmaker_fails(self, mock_sessionmaker_fails, mock_create_engine_success, mock_config):
        mock_engine_instance = MagicMock()
        mock_create_engine_success.return_value = mock_engine_instance

        with pytest.raises(ConnectionError, match="Unexpected database initialization error: Sessionmaker failed"):
            DatabaseManager(config=mock_config)

        mock_create_engine_success.assert_called_once_with(mock_config.db_path)
        mock_sessionmaker_fails.assert_called_once_with(autocommit=False, autoflush=False, bind=mock_engine_instance)
        # db_manager instance won't be fully initialized, so can't check db_manager.engine / .Session here

# Tests for initialize_database
class TestInitializeDatabase:
    @patch('src.database.db_manager.Base.metadata.create_all')
    def test_initialize_database_success(self, mock_create_all, mock_config):
        db_manager = DatabaseManager(config=mock_config) # Assumes _connect works or is mocked if needed for engine
        # Ensure engine is mocked for this test if _connect isn't fully successful in test setup
        db_manager.engine = MagicMock() # Directly set a mock engine for this test unit
        
        db_manager.initialize_database()
        
        mock_create_all.assert_called_once_with(db_manager.engine)

    def test_initialize_database_no_engine(self, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        db_manager.engine = None # Explicitly set engine to None
        
        with patch('src.database.db_manager.Base.metadata.create_all') as mock_create_all:
            db_manager.initialize_database()
            mock_create_all.assert_not_called()
        # TODO: Assert logger.error was called - requires patching logger

    @patch('src.database.db_manager.Base.metadata.create_all', side_effect=SQLAlchemyError("Schema creation failed"))
    def test_initialize_database_sqlalchemy_error(self, mock_create_all_fails, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        db_manager.engine = MagicMock() # Ensure engine is present
        
        db_manager.initialize_database()
        
        mock_create_all_fails.assert_called_once_with(db_manager.engine)
        # TODO: Assert logger.exception was called

    @patch('src.database.db_manager.Base.metadata.create_all', side_effect=Exception("Unexpected schema error"))
    def test_initialize_database_unexpected_error(self, mock_create_all_unexpected_fails, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        db_manager.engine = MagicMock()

        db_manager.initialize_database()
        mock_create_all_unexpected_fails.assert_called_once_with(db_manager.engine)
        # TODO: Assert logger.exception was called

# Tests for get_session
class TestGetSession:
    def test_get_session_success(self, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        # Assume _connect was successful during init, so db_manager.Session is a mock sessionmaker
        mock_session_factory = MagicMock()
        mock_created_session = MagicMock()
        mock_session_factory.return_value = mock_created_session
        db_manager.Session = mock_session_factory # Directly assign a mock sessionmaker
        
        session = db_manager.get_session()
        
        mock_session_factory.assert_called_once_with()
        assert session is mock_created_session

    @patch.object(DatabaseManager, '_connect')
    def test_get_session_none_attempts_reconnect_success(self, mock_connect, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        db_manager.Session = None # Start with no Session factory
        
        # Simulate _connect succeeding and setting up self.Session
        mock_new_session_factory = MagicMock()
        mock_new_created_session = MagicMock()
        mock_new_session_factory.return_value = mock_new_created_session
        
        def connect_side_effect():
            db_manager.Session = mock_new_session_factory # _connect sets this up
        mock_connect.side_effect = connect_side_effect
        
        with patch.object(db_manager, '_connect', side_effect=db_manager._connect) as mock_reconnect: # Spy on _connect
            session = db_manager.get_session()
            assert session is not None
            mock_reconnect.assert_called_once() # _connect should be called by get_session
        # mock_connect was called in init and by get_session
        assert mock_connect.call_count == 2 

    @patch('src.database.db_manager.DatabaseManager._connect') 
    def test_get_session_reconnect_fails_raises_error(self, mock_connect, mock_config):
        # 1. First call in __init__ should succeed (let's make it do nothing for simplicity)
        mock_connect.side_effect = [None]
        db_manager = DatabaseManager(config=mock_config)
        mock_connect.assert_called_once() # Called during init
        db_manager.Session = None # Manually set Session to None to trigger reconnect attempt
        
        # 2. Configure the mock for the SECOND call (triggered by get_session)
        mock_connect.side_effect = ConnectionError("Reconnect fail") 
        
        # 3. Call get_session and expect ConnectionError from the second _connect call
        with pytest.raises(ConnectionError, match="Reconnect fail"):
            db_manager.get_session()

        # Check _connect was called twice in total (once in init, once in get_session)
        assert mock_connect.call_count == 2

    def test_get_session_initial_session_none_no_engine(self, mock_config):
        # This tests if _connect fails initially and Session is None from the start
        # and then get_session is called.
        with patch('src.database.db_manager.create_engine', side_effect=SQLAlchemyError("Initial engine fail")) as mock_create_engine_fail,\
             patch.object(DatabaseManager, '_connect') as mock_connect_method_on_instance: # To check calls on the instance
            
            db_m = DatabaseManager(config=mock_config) # _connect called in init, fails to set Session
            assert db_m.Session is None

            # Now, when get_session is called, it will call db_m._connect() again.
            # Let's make this second _connect call also fail to set Session.
            def specific_connect_failure():
                db_m.engine = None # Ensure engine also reflects failure state
                db_m.Session = None
            
            # We need to re-patch _connect on the *instance* or ensure the class patch works for the second call
            # Patching the method on the instance for the second call triggered by get_session:
            db_m._connect = MagicMock(side_effect=specific_connect_failure) 

            with pytest.raises(ConnectionError, match="Database connection failed, cannot get session."):
                db_m.get_session()
            
            # _connect was called once in __init__, and once by get_session
            # The first call is to the original _connect (which we indirectly controlled via create_engine patch)
            # The second call is to the instance-level MagicMock we just set.
            db_m._connect.assert_called_once()

# Tests for managed_session
class TestManagedSession:
    @patch.object(DatabaseManager, 'get_session')
    def test_managed_session_success(self, mock_get_session_method, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        mock_session_instance = MagicMock()
        mock_get_session_method.return_value = mock_session_instance
        
        with db_manager.managed_session() as session:
            assert session is mock_session_instance
            # Simulate operations within the session
            session.add(MagicMock())
        
        mock_get_session_method.assert_called_once()
        mock_session_instance.commit.assert_called_once()
        mock_session_instance.rollback.assert_not_called()
        mock_session_instance.close.assert_called_once()

    @patch.object(DatabaseManager, 'get_session')
    def test_managed_session_sqlalchemy_error_triggers_rollback(self, mock_get_session_method, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        mock_session_instance = MagicMock()
        mock_get_session_method.return_value = mock_session_instance
        
        error_to_raise = SQLAlchemyError("Simulated DB error")
        
        with pytest.raises(SQLAlchemyError, match="Simulated DB error") as exc_info:
            with db_manager.managed_session() as session:
                session.execute("bad query").side_effect = error_to_raise # Simulate error source
                # More directly, cause the error inside the block
                raise error_to_raise 
        
        assert exc_info.value is error_to_raise
        mock_get_session_method.assert_called_once()
        mock_session_instance.commit.assert_not_called()
        mock_session_instance.rollback.assert_called_once()
        mock_session_instance.close.assert_called_once()

    @patch.object(DatabaseManager, 'get_session')
    def test_managed_session_unexpected_error_triggers_rollback(self, mock_get_session_method, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        mock_session_instance = MagicMock()
        mock_get_session_method.return_value = mock_session_instance
        
        error_to_raise = ValueError("Simulated unexpected error")
        
        with pytest.raises(ValueError, match="Simulated unexpected error") as exc_info:
            with db_manager.managed_session() as session:
                raise error_to_raise
        
        assert exc_info.value is error_to_raise
        mock_get_session_method.assert_called_once()
        mock_session_instance.commit.assert_not_called()
        mock_session_instance.rollback.assert_called_once()
        mock_session_instance.close.assert_called_once()

    @patch.object(DatabaseManager, 'get_session')
    def test_managed_session_get_session_fails(self, mock_get_session_method, mock_config):
        db_manager = DatabaseManager(config=mock_config)
        error_to_raise = ConnectionError("Cannot get session")
        mock_get_session_method.side_effect = error_to_raise
        
        with pytest.raises(ConnectionError, match="Cannot get session") as exc_info:
            with db_manager.managed_session() as session: # pragma: no cover (should not be reached)
                pass # This block should not execute
        
        assert exc_info.value is error_to_raise
        mock_get_session_method.assert_called_once()
        # commit, rollback, close on the session instance should not be called as session was never obtained.

# TODO: Add tests for managed_session

# TODO: Add test cases for DatabaseManager 