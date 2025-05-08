import logging
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import sys
import os
import contextlib
from typing import Optional

# Adjust path to import sibling modules
# current_dir = os.path.dirname(os.path.abspath(__file__))
# sys.path.append(os.path.abspath(os.path.join(current_dir, '..')))

# Ensure Base is imported from the local models.py
from .models import Base

try:
    # Assuming config_manager.py is in src/config/
    from config.config_manager import ConfigManager
except ImportError:
    # Fallback if run differently
    # This path adjustment might be fragile depending on execution context
    config_path = os.path.abspath(os.path.join(current_dir, '..', 'config'))
    if config_path not in sys.path:
        sys.path.insert(0, config_path)
    try:
        from config_manager import ConfigManager
    except ImportError:
        logging.error("Failed to import ConfigManager. Ensure it's in src/config/")
        # Define a dummy class if import fails to avoid crashing later
        class ConfigManager:
            def __init__(self, *args, **kwargs):
                self.db_path = 'sqlite:///fallback_leads.db'
                logging.warning("Using fallback ConfigManager due to import error.")


logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connection, sessions, and schema initialization."""
    
    def __init__(self, config: ConfigManager):
        """
        Initializes the DatabaseManager.

        Args:
            config: An instance of ConfigManager containing the db_path.
        """
        self.config = config
        self.engine = None
        self.Session = None
        self._connect()

    def _connect(self):
        """Establishes the database connection and creates a sessionmaker."""
        try:
            db_url = self.config.db_path
            logger.info(f"Connecting to database: {db_url}")
            # Add connect_args for SQLite write access across threads if needed later
            # connect_args={'check_same_thread': False} # Use with caution!
            self.engine = create_engine(db_url) 
            # Test connection (optional, but good practice)
            with self.engine.connect() as connection:
                logger.info("Database engine created and connection successful.")
            self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            logger.info("Database sessionmaker configured.")
        except SQLAlchemyError as e: # Catch specific SQLAlchemy errors first
            logger.error(f"Failed to create SQLAlchemy engine or sessionmaker: {e}")
            self.engine = None
            self.Session = None
            raise ConnectionError(f"Database connection/setup failed: {e}") from e # Re-raise as ConnectionError
        except Exception as e: # Catch any other unexpected errors during setup
            logger.error(f"An unexpected error occurred during database initialization: {e}")
            self.engine = None
            self.Session = None
            # Optionally re-raise or handle as a critical failure
            raise ConnectionError(f"Unexpected database initialization error: {e}") from e # Re-raise as ConnectionError

    def initialize_database(self):
        """Creates all tables in the database based on the defined models."""
        if not self.engine:
            logger.error("Database engine not initialized. Cannot create tables.")
            return

        try:
            logger.info("Initializing database schema (creating tables if they don't exist)...")
            # This command creates tables based on all classes inheriting from Base
            Base.metadata.create_all(self.engine)
            logger.info("Database schema initialization complete.")
        except SQLAlchemyError as e:
            logger.exception(f"Failed to initialize database schema: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during schema initialization: {e}")

    def get_session(self) -> Optional[Session]:
        """Provides a database session."""
        if not self.Session:
            logger.error("Sessionmaker not initialized. Cannot provide session.")
            # Maybe attempt to reconnect or raise an error
            self._connect() # Attempt to reconnect
            if not self.Session:
                 raise ConnectionError("Database connection failed, cannot get session.")
        return self.Session()

    @contextlib.contextmanager
    def managed_session(self):
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Session rollback due to SQLAlchemy error: {e}")
            session.rollback()
            raise
        except Exception as e:
            logger.error(f"Session rollback due to an unexpected error: {e}")
            session.rollback()
            raise
        finally:
            session.close()

# Example usage (for direct testing of this file)
if __name__ == '__main__':
    # Basic logging for testing
    import logging
    import contextlib # Add this import for the new managed_session
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Testing DatabaseManager...")
    
    # Create a dummy .env file for testing
    dummy_env_path = ".env.test_db_manager"
    # Use an in-memory db for this test run
    dummy_db_path = "sqlite:///:memory:" 
    # Or use a file: 
    # dummy_db_file = "test_leads.db"
    # dummy_db_path = f"sqlite:///{dummy_db_file}"
    
    with open(dummy_env_path, "w") as f:
        f.write(f"DB_PATH={dummy_db_path}\n")
        # Add other dummy config if needed by ConfigManager
        f.write("SCRAPING_API_KEY=dummy_key\n") 

    try:
        test_config = ConfigManager(env_file_path=dummy_env_path)
        db_manager = DatabaseManager(config=test_config)
        
        if db_manager.engine and db_manager.Session:
            print("\n--- DatabaseManager Initialization Test --- ")
            print(f"Engine dialect: {db_manager.engine.dialect.name}")
            
            print("\n--- Schema Initialization Test --- ")
            db_manager.initialize_database()
            # You would typically check if tables exist here in a real test
            print("Schema initialized (check logs for errors).")
            
            print("\n--- Session Retrieval Test --- ")
            session = None
            try:
                session = db_manager.get_session()
                print(f"Session obtained: {session}")
                # Example: Try a simple query
                # result = session.execute('SELECT 1')
                # print(f"Simple query result: {result.scalar()}")
            except Exception as session_e:
                print(f"Error getting or using session: {session_e}")
            finally:
                if session:
                    session.close()
                    print("Session closed.")
            
            print("\n--- Managed Session Test --- ")
            try:
                with db_manager.managed_session() as session:
                    print(f"Managed session obtained: {session}")
                    # Example: Try a simple query within the managed session
                    # result = session.execute(sqlalchemy.text('SELECT 1'))
                    # print(f"Simple query result from managed session: {result.scalar()})
                    # To test rollback, you could raise an exception here:
                    # raise ValueError("Simulated error for rollback")
                print("Managed session committed and closed.")
            except Exception as managed_session_e:
                print(f"Error during managed session: {managed_session_e}")

            print("\nDatabaseManager basic tests completed.")
        else:
            print("DatabaseManager failed to initialize correctly.")
            
    except Exception as e:
        logger.exception(f"An error occurred during DatabaseManager testing: {e}")
    finally:
        # Clean up dummy files
        if os.path.exists(dummy_env_path):
            os.remove(dummy_env_path)
        # if os.path.exists(dummy_db_file):
        #     os.remove(dummy_db_file)
        print("Cleanup complete.") 