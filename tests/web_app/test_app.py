# Initial test file for app.py (main FastAPI app)
import pytest
from fastapi import status, FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
import datetime

# from src.web_app.app import app 

# Import the app and dependencies from api_main
from src.web_app.api_main import app, get_db, get_config, db_manager, config_manager
from src.database import models

# --- Test Client Setup ---
# We can use the app directly, but overrides might be needed per test class/method
@pytest.fixture
def mock_db_session():
    return MagicMock(spec=Session)

@pytest.fixture
def test_client_for_app(mock_db_session):
    # Override get_db for this client instance
    def override_get_db():
        # Simulate the context manager behavior
        @contextmanager
        def managed_session_mock():
            yield mock_db_session
        with managed_session_mock() as session:
            yield session
            
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

# --- Tests for api_main.py components ---

class TestAppSetup:
    def test_read_root(self, test_client_for_app):
        response = test_client_for_app.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Networking Assistant API is running."}

    # Test if routers are included correctly by checking if a basic GET request works
    @patch('src.web_app.routers.leads.db_utils.get_entity', 
           return_value=models.Lead(id=1, name="Test", status=models.LeadStatus.NEW, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)))
    def test_leads_router_included(self, mock_get_lead, test_client_for_app):
        response = test_client_for_app.get("/api/v1/leads/1")
        assert response.status_code == 200 # Expect 200 OK if router included and mock works

    @patch('src.web_app.routers.companies.db_utils.get_entity', 
           return_value=models.Company(id=1, name="Test Co", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)))
    def test_companies_router_included(self, mock_get_company, test_client_for_app):
        response = test_client_for_app.get("/api/v1/companies/1")
        assert response.status_code == 200

    @patch('src.web_app.routers.jobs.db_utils.get_entity', 
           return_value=models.JobPosting(id=1, title="Test Job", status="Open", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)))
    def test_jobs_router_included(self, mock_get_job, test_client_for_app):
        response = test_client_for_app.get("/api/v1/jobs/1")
        assert response.status_code == 200

class TestDependencies:
    @patch('src.web_app.api_main.db_manager') # Patch the global db_manager used by get_db
    def test_get_db_dependency(self, mock_global_db_manager, mock_db_session): # Use the session fixture
        # Mock the context manager provided by db_manager
        @contextmanager
        def managed_session_mock():
            yield mock_db_session
            # Simulate commit/rollback/close calls if needed, though managed_session handles it
            # mock_db_session.commit.assert_called...?
            # mock_db_session.close.assert_called...?
        mock_global_db_manager.managed_session.return_value = managed_session_mock()
        
        # Simulate calling the dependency
        db_gen = get_db()
        retrieved_session = next(db_gen)
        
        assert retrieved_session is mock_db_session
        mock_global_db_manager.managed_session.assert_called_once()
        # Check context manager cleanup (optional, depends on test detail level)
        with pytest.raises(StopIteration):
            next(db_gen)
            
    def test_get_config_dependency(self):
        # get_config should return the globally initialized config_manager
        retrieved_config = get_config()
        # We need to compare it to the actual imported global instance
        from src.web_app.api_main import config_manager as global_config
        assert retrieved_config is global_config 

class TestExceptionHandlers:
    # Test the SQLAlchemyError handler
    # We need an endpoint that can potentially raise SQLAlchemyError during its operation.
    # Let's use the create lead endpoint and make the db_utils call raise the error.
    @patch('src.web_app.routers.leads.db_utils.get_entity', return_value=MagicMock())
    @patch('src.web_app.routers.leads.db_utils.get_entities', return_value=[])
    @patch('src.web_app.routers.leads.db_utils.create_entity', side_effect=SQLAlchemyError("DB Unique constraint failed"))
    def test_sqlalchemy_exception_handler(self, mock_create_lead_fails, mock_get_entities, mock_get_company, test_client_for_app):
        lead_data = {"name": "Trigger DB Error", "company_id": 1}
        response = test_client_for_app.post("/api/v1/leads/", json=lead_data)
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "An internal database error occurred" in response.json()['detail']
        # Optionally check the specific error message part if it's included and stable
        assert "DB Unique constraint failed" in response.json()['detail']

# TODO: Add test cases for FastAPI app setup and root endpoint 