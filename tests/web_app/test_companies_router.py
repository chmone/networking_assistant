# Initial test file for companies router
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import datetime # Import datetime
import unittest.mock # Import unittest.mock

# from src.web_app.app import app # Need to import the app object
# from src.database import db_manager # For dependency overrides

# client = TestClient(app)

# Assuming the main FastAPI app is defined in src.web_app.app
# and it includes the companies router.
from src.web_app.api_main import app 
from src.database import models
from src.web_app import schemas
from src.web_app.api_main import get_db # The dependency we need to override

# Re-use or redefine fixtures if needed (can be moved to conftest.py later)
@pytest.fixture
def mock_db_session_override():
    session = MagicMock()
    session.query = MagicMock()
    return session

@pytest.fixture
def test_client(mock_db_session_override):
    app.dependency_overrides[get_db] = lambda: mock_db_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

# --- Tests for POST /companies/ ---
@patch('src.web_app.routers.companies.db_utils.get_entities', return_value=[]) # No existing company with name
@patch('src.web_app.routers.companies.db_utils.create_entity')
def test_create_company_success(mock_create, mock_get_entities, test_client):
    company_data = {"name": "New Company", "website": "http://newco.com"}
    mock_created_db_company = models.Company(id=1, **company_data, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_create.return_value = mock_created_db_company

    response = test_client.post("/api/v1/companies/", json=company_data)

    assert response.status_code == status.HTTP_201_CREATED
    mock_get_entities.assert_called_once()
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[1] == models.Company
    assert args[2]['name'] == company_data['name']
    
    response_data = response.json()
    assert response_data['id'] == mock_created_db_company.id
    assert response_data['name'] == company_data['name']
    assert response_data['website'] # Pydantic validates, value might differ slightly (e.g., trailing slash)

@patch('src.web_app.routers.companies.db_utils.get_entities') # Company name exists
def test_create_company_name_exists(mock_get_entities, test_client):
    company_data = {"name": "Existing Company"}
    mock_get_entities.return_value = [models.Company(id=5, name="Existing Company")]

    response = test_client.post("/api/v1/companies/", json=company_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Company with name '{company_data['name']}' already exists" in response.json()['detail']

@patch('src.web_app.routers.companies.db_utils.get_entities', return_value=[])
@patch('src.web_app.routers.companies.db_utils.create_entity', return_value=None) # DB failure
def test_create_company_db_failure(mock_create, mock_get_entities, test_client):
    company_data = {"name": "Fail Co"}
    response = test_client.post("/api/v1/companies/", json=company_data)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to create company" in response.json()['detail']

# --- Tests for GET /companies/ ---
@patch('src.web_app.routers.companies.db_utils.get_entities')
def test_read_companies_defaults(mock_get_entities, test_client):
    mock_companies_db = [
        models.Company(id=1, name="Co A", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)),
        models.Company(id=2, name="Co B", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    ]
    mock_get_entities.return_value = mock_companies_db

    response = test_client.get("/api/v1/companies/")

    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 0
    assert kwargs.get('limit') == 100
    assert kwargs.get('filters') == {}
    
    response_data = response.json()
    assert len(response_data) == 2
    assert response_data[0]['name'] == "Co A"

@patch('src.web_app.routers.companies.db_utils.get_entities')
def test_read_companies_with_params(mock_get_entities, test_client):
    mock_companies_db = [models.Company(id=3, name="Target Co", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))]
    mock_get_entities.return_value = mock_companies_db

    response = test_client.get("/api/v1/companies/?skip=5&limit=10&name=Target Co")
    
    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 5
    assert kwargs.get('limit') == 10
    assert kwargs.get('filters') == {'name': 'Target Co'}

    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]['name'] == "Target Co"

@patch('src.web_app.routers.companies.db_utils.get_entities', return_value=[])
def test_read_companies_no_results(mock_get_entities, test_client):
    response = test_client.get("/api/v1/companies/?name=nonexistent")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

# --- Tests for GET /companies/{company_id} ---
@patch('src.web_app.routers.companies.db_utils.get_entity')
def test_read_company_success(mock_get_entity, test_client):
    company_id = 1
    mock_company_db = models.Company(id=company_id, name="Found Co", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_get_entity.return_value = mock_company_db

    response = test_client.get(f"/api/v1/companies/{company_id}")

    assert response.status_code == status.HTTP_200_OK
    mock_get_entity.assert_called_once()
    args, kwargs = mock_get_entity.call_args
    assert args[1] == models.Company
    assert args[2] == company_id

    response_data = response.json()
    assert response_data['id'] == company_id
    assert response_data['name'] == "Found Co"

@patch('src.web_app.routers.companies.db_utils.get_entity', return_value=None)
def test_read_company_not_found(mock_get_entity, test_client):
    company_id = 999
    response = test_client.get(f"/api/v1/companies/{company_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company not found" in response.json()['detail']
    mock_get_entity.assert_called_once()

# Test PUT /companies/{company_id}
class TestUpdateCompany:

    @patch('src.web_app.routers.companies.db_utils.get_entities') # Mock for name conflict check
    @patch('src.web_app.routers.companies.db_utils.update_entity') # Mock the actual update function
    def test_update_company_success(self, mock_update_entity_func, mock_get_entities_func, test_client):
        company_id = 1
        update_payload = {"name": "Updated Co Name", "industry": "Finance"}
        
        # 1. Mock get_entities to return [] (no name conflict)
        mock_get_entities_func.return_value = [] 
        
        # 2. Mock update_entity to return the updated object
        mock_updated_db_company = models.Company(
            id=company_id, 
            name=update_payload["name"], 
            industry=update_payload["industry"], 
            created_at=datetime.datetime.now(datetime.UTC), 
            updated_at=datetime.datetime.now(datetime.UTC)
        )
        mock_update_entity_func.return_value = mock_updated_db_company

        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)

        # --- Assertions ---
        assert response.status_code == status.HTTP_200_OK
        # Check that get_entities was called for name conflict check
        mock_get_entities_func.assert_called_once_with(
            unittest.mock.ANY,        # db (positional)
            models.Company,           # model (positional)
            filters={'name': update_payload["name"]},
            limit=1
        )
        # Check that update_entity was called correctly
        mock_update_entity_func.assert_called_once_with(
            unittest.mock.ANY,        # db (positional)
            models.Company,           # model (positional)
            company_id,               # entity_id (positional)
            update_payload            # data (positional)
        )
        # Check the response body
        response_data = response.json()
        assert response_data["id"] == company_id
        assert response_data["name"] == update_payload["name"]
        assert response_data["industry"] == update_payload["industry"]

    @patch('src.web_app.routers.companies.db_utils.get_entities')
    def test_update_company_name_conflict(self, mock_get_entities_func, test_client):
        company_id = 1
        update_payload = {"name": "Existing Name"}
        # Mock get_entities to return a *different* company with the target name
        mock_get_entities_func.return_value = [models.Company(id=99, name="Existing Name")]

        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]
        mock_get_entities_func.assert_called_once()

    # Test case where name doesn't change (should not trigger conflict check)
    @patch('src.web_app.routers.companies.db_utils.get_entities') 
    @patch('src.web_app.routers.companies.db_utils.update_entity')
    def test_update_company_name_not_changed(self, mock_update_entity_func, mock_get_entities_func, test_client):
        company_id = 1
        update_payload = {"industry": "New Industry"} # Name is not included
        # Add missing fields to the mock return object
        mock_update_entity_func.return_value = models.Company(
            id=company_id, 
            name="Original Name", 
            industry="New Industry",
            created_at=datetime.datetime.now(datetime.UTC),
            updated_at=datetime.datetime.now(datetime.UTC) 
        )
        
        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)
        
        assert response.status_code == status.HTTP_200_OK
        mock_get_entities_func.assert_not_called() # Name conflict check shouldn't run
        mock_update_entity_func.assert_called_once()

    @patch('src.web_app.routers.companies.db_utils.get_entities', return_value=[]) # Mock for name conflict
    @patch('src.web_app.routers.companies.db_utils.update_entity', return_value=None)
    @patch('src.web_app.routers.companies.db_utils.get_entity', return_value=None) # Mock get_entity for 404 check
    def test_update_company_not_found(self, mock_get_entity_for_404_check, mock_update_entity_returns_none, mock_get_entities_for_conflict, test_client):
        company_id = 999
        update_payload = {"name": "Doesn't Matter"}
        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        mock_get_entities_for_conflict.assert_called_once_with(
            unittest.mock.ANY, # db session (positional)
            models.Company,    # model (positional)
            filters={'name': update_payload["name"]},
            limit=1
        )
        mock_update_entity_returns_none.assert_called_once()
        mock_get_entity_for_404_check.assert_called_once_with(unittest.mock.ANY, models.Company, company_id)
        
    @patch('src.web_app.routers.companies.db_utils.get_entities', return_value=[]) # Mock for name conflict
    @patch('src.web_app.routers.companies.db_utils.update_entity', return_value=None)
    @patch('src.web_app.routers.companies.db_utils.get_entity') # Mock get_entity returning the object
    def test_update_company_db_failure(self, mock_get_entity_exists_check, mock_update_entity_returns_none, mock_get_entities_for_conflict, test_client):
        company_id = 1
        update_payload = {"name": "DB Fail"}
        # This mock is for the get_entity called AFTER update_entity fails
        mock_get_entity_exists_check.return_value = models.Company(
            id=company_id, 
            name="Original Name Before DB Fail",
            created_at=datetime.datetime.now(datetime.UTC), # Add required fields
            updated_at=datetime.datetime.now(datetime.UTC)  # Add required fields
        ) 
        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to update company" in response.json()["detail"]

        mock_get_entities_for_conflict.assert_called_once_with(
            unittest.mock.ANY, # db session (positional)
            models.Company,    # model (positional)
            filters={'name': update_payload["name"]},
            limit=1
        )
        mock_update_entity_returns_none.assert_called_once()
        mock_get_entity_exists_check.assert_called_once_with(unittest.mock.ANY, models.Company, company_id)

    def test_update_company_no_update_data(self, test_client):
        company_id = 1
        update_payload = {} # Empty payload
        response = test_client.put(f"/api/v1/companies/{company_id}", json=update_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No fields provided" in response.json()["detail"]

# --- Tests for DELETE /companies/{company_id} ---
@patch('src.web_app.routers.companies.db_utils.delete_entity', return_value=True)
def test_delete_company_success(mock_delete_entity, test_client):
    company_id = 1
    response = test_client.delete(f"/api/v1/companies/{company_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete_entity.assert_called_once()
    args, kwargs = mock_delete_entity.call_args
    assert args[1] == models.Company
    assert args[2] == company_id
    assert not response.content

@patch('src.web_app.routers.companies.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.companies.db_utils.get_entity', return_value=None)
def test_delete_company_not_found(mock_get_entity, mock_delete_entity, test_client):
    company_id = 999
    response = test_client.delete(f"/api/v1/companies/{company_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company not found" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once()

@patch('src.web_app.routers.companies.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.companies.db_utils.get_entity')
def test_delete_company_db_failure(mock_get_entity, mock_delete_entity, test_client):
    company_id = 1
    mock_get_entity.return_value = models.Company(id=company_id, name="Existing Co") # Simulate company exists
    response = test_client.delete(f"/api/v1/companies/{company_id}")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to delete company" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once() 