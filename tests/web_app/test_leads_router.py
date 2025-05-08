# Initial test file for leads router
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import datetime # Import datetime

# from src.web_app.app import app # Need to import the app object
# from src.database import db_manager # For dependency overrides

# client = TestClient(app)

# Assuming the main FastAPI app is defined in src.web_app.app
# and it includes the leads router.
from src.web_app.api_main import app 
from src.database import models # Need models for checks
from src.web_app import schemas # Need schemas for request/response models
from src.web_app.api_main import get_db # The dependency we need to override

# Create a fixture for the mock database session
@pytest.fixture
def mock_db_session_override():
    session = MagicMock()
    # Configure mocks for specific query methods if needed within tests
    session.query = MagicMock()
    return session

# Create a fixture for the TestClient, applying the dependency override
@pytest.fixture
def test_client(mock_db_session_override):
    # Override the get_db dependency before creating the client
    app.dependency_overrides[get_db] = lambda: mock_db_session_override
    client = TestClient(app)
    yield client # Use yield to allow cleanup after tests
    app.dependency_overrides.clear() # Clear overrides after tests

# --- Tests for POST /leads/ ---
@patch('src.web_app.routers.leads.db_utils.get_entity') # Mock check for company
@patch('src.web_app.routers.leads.db_utils.get_entities') # Mock check for existing email
@patch('src.web_app.routers.leads.db_utils.create_entity')
def test_create_lead_success(mock_create, mock_get_entities, mock_get_entity, test_client, mock_db_session_override):
    lead_data = {"name": "New Lead", "email": "new@example.com", "status": "new"}
    mock_get_entity.return_value = MagicMock() # Company found
    mock_get_entities.return_value = [] # No lead with this email exists

    # Ensure the created mock object also has the enum member for status if checked directly
    # Use the enum member for the mock object's attribute
    mock_created_lead_db = models.Lead(id=1, 
                                       name=lead_data['name'], 
                                       email=lead_data['email'], 
                                       status=models.LeadStatus.NEW, # Use enum member
                                       company_id=None, 
                                       created_at=datetime.datetime.now(datetime.UTC),
                                       updated_at=datetime.datetime.now(datetime.UTC))
    mock_create.return_value = mock_created_lead_db

    response = test_client.post("/api/v1/leads/", json=lead_data)

    assert response.status_code == status.HTTP_201_CREATED
    mock_get_entity.assert_not_called()
    mock_get_entities.assert_called_once()
    mock_create.assert_called_once()
    # Check if create_entity was called with the correct model and data
    args, kwargs = mock_create.call_args
    assert args[0] == mock_db_session_override
    assert args[1] == models.Lead
    # args[2] should be lead.dict() from the input schema
    assert args[2]['name'] == lead_data['name']
    assert args[2]['email'] == lead_data['email'] 
    
    # Validate response against the Read schema
    response_data = response.json()
    assert response_data['id'] == mock_created_lead_db.id
    assert response_data['name'] == lead_data['name']
    assert response_data['email'] == lead_data['email']
    assert "created_at" in response_data

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=None) # Company not found
def test_create_lead_company_not_found(mock_get_entity, test_client, mock_db_session_override):
    lead_data = {"name": "New Lead", "company_id": 999} # Non-existent company ID
    response = test_client.post("/api/v1/leads/", json=lead_data)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company with id 999 not found" in response.json()['detail']

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=MagicMock()) # Company found
@patch('src.web_app.routers.leads.db_utils.get_entities') # Mock check for existing email
def test_create_lead_email_exists(mock_get_entities, mock_get_entity, test_client, mock_db_session_override):
    lead_data = {"name": "New Lead", "email": "existing@example.com", "company_id": 1}
    # Simulate lead with this email already exists
    mock_get_entities.return_value = [models.Lead(id=5, email="existing@example.com", name="Old Lead")] 

    response = test_client.post("/api/v1/leads/", json=lead_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Lead with email {lead_data['email']} already exists" in response.json()['detail']

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=MagicMock())
@patch('src.web_app.routers.leads.db_utils.get_entities', return_value=[])
@patch('src.web_app.routers.leads.db_utils.create_entity', return_value=None) # Simulate DB failure on create
def test_create_lead_db_failure(mock_create, mock_get_entities, mock_get_entity, test_client):
    lead_data = {"name": "New Lead", "email": "fail@example.com", "company_id": 1}
    response = test_client.post("/api/v1/leads/", json=lead_data)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to create lead" in response.json()['detail']

# --- Tests for GET /leads/ ---
@patch('src.web_app.routers.leads.db_utils.get_entities')
def test_read_leads_defaults(mock_get_entities, test_client):
    # Ensure mock objects have a status, as the model expects it (default=NEW, nullable=False)
    mock_leads_db = [
        models.Lead(id=1, name="Lead 1", email="l1@example.com", status=models.LeadStatus.NEW, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)),
        models.Lead(id=2, name="Lead 2", email="l2@example.com", status=models.LeadStatus.CONTACTED, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    ]
    mock_get_entities.return_value = mock_leads_db

    response = test_client.get("/api/v1/leads/")

    assert response.status_code == status.HTTP_200_OK
    # Check if get_entities was called with default skip/limit and empty filters
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 0
    assert kwargs.get('limit') == 100
    assert kwargs.get('filters') == {}
    assert kwargs.get('order_by_column') is None
    assert kwargs.get('sort_direction') == 'asc'
    
    # Validate response structure (List[LeadRead])
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == len(mock_leads_db)
    assert response_data[0]['id'] == mock_leads_db[0].id
    assert response_data[0]['name'] == mock_leads_db[0].name

@patch('src.web_app.routers.leads.db_utils.get_entities')
def test_read_leads_with_params(mock_get_entities, test_client):
    mock_leads_db = [models.Lead(id=3, name="Filtered Lead", status=models.LeadStatus.CONTACTED, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))]
    mock_get_entities.return_value = mock_leads_db
    
    response = test_client.get("/api/v1/leads/?skip=5&limit=10&status=contacted&name_contains=Filtered&company_id=1&sort_by=name&sort_order=desc")
    
    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 5
    assert kwargs.get('limit') == 10
    expected_filters = {
        'status': schemas.LeadStatusEnum.CONTACTED,
        'name__ilike': '%Filtered%',
        'company_id': 1
    }
    assert kwargs.get('filters') == expected_filters
    assert kwargs.get('order_by_column') == models.Lead.name # Check column object
    assert kwargs.get('sort_direction') == 'desc'

    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]['name'] == "Filtered Lead"

@patch('src.web_app.routers.leads.db_utils.get_entities', return_value=[])
def test_read_leads_no_results(mock_get_entities, test_client):
    response = test_client.get("/api/v1/leads/?name_contains=nonexistent")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

# --- Tests for GET /leads/{lead_id} ---
@patch('src.web_app.routers.leads.db_utils.get_entity')
def test_read_lead_success(mock_get_entity, test_client):
    lead_id = 1
    # Ensure mock object has a status
    mock_lead_db = models.Lead(id=lead_id, name="Found Lead", email="found@example.com", status=models.LeadStatus.INTERESTED, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_get_entity.return_value = mock_lead_db

    response = test_client.get(f"/api/v1/leads/{lead_id}")

    assert response.status_code == status.HTTP_200_OK
    mock_get_entity.assert_called_once()
    args, kwargs = mock_get_entity.call_args
    assert args[1] == models.Lead
    assert args[2] == lead_id

    # Validate response against Read schema
    response_data = response.json()
    assert response_data['id'] == lead_id
    assert response_data['name'] == "Found Lead"

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=None)
def test_read_lead_not_found(mock_get_entity, test_client):
    lead_id = 999
    response = test_client.get(f"/api/v1/leads/{lead_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Lead not found" in response.json()['detail']
    mock_get_entity.assert_called_once()

# --- Tests for PUT /leads/{lead_id} ---
@patch('src.web_app.routers.leads.db_utils.get_entity') # Mock checks for company_id and lead_not_found fallback
@patch('src.web_app.routers.leads.db_utils.get_entities') # Mock check for email conflict
@patch('src.web_app.routers.leads.db_utils.update_entity')
def test_update_lead_success(mock_update_entity, mock_get_entities, mock_get_entity, test_client, mock_db_session_override):
    lead_id = 1
    update_payload = {"name": "Updated Lead Name", "status": "interested"}
    # Ensure the mock updated object has the enum member for status
    mock_updated_db_lead = models.Lead(id=lead_id, name="Updated Lead Name", status=models.LeadStatus.INTERESTED, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_update_entity.return_value = mock_updated_db_lead
    # Assume company check passes (if company_id was in payload), and email check passes
    mock_get_entity.return_value = MagicMock() # For company check if needed
    mock_get_entities.return_value = [] # No email conflict

    response = test_client.put(f"/api/v1/leads/{lead_id}", json=update_payload)

    assert response.status_code == status.HTTP_200_OK
    mock_update_entity.assert_called_once()
    args, kwargs = mock_update_entity.call_args
    assert args[1] == models.Lead
    assert args[2] == lead_id
    # Check data passed excludes unset fields
    assert args[3] == {"name": "Updated Lead Name", "status": schemas.LeadStatusEnum.INTERESTED} 
    
    response_data = response.json()
    assert response_data['id'] == lead_id
    assert response_data['name'] == "Updated Lead Name"
    assert response_data['status'] == schemas.LeadStatusEnum.INTERESTED.value # Read schema uses enum values

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=None) # Company check fails
def test_update_lead_company_not_found(mock_get_entity, test_client):
    lead_id = 1
    update_payload = {"company_id": 999} # Try to update with non-existent company
    response = test_client.put(f"/api/v1/leads/{lead_id}", json=update_payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company with id 999 not found" in response.json()['detail']

@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=MagicMock()) # Company check passes
@patch('src.web_app.routers.leads.db_utils.get_entities') # Email check fails
def test_update_lead_email_conflict(mock_get_entities, mock_get_entity, test_client):
    lead_id = 1
    conflicting_email = "taken@example.com"
    update_payload = {"email": conflicting_email}
    # Simulate another lead (id=2) has this email
    mock_get_entities.return_value = [models.Lead(id=2, email=conflicting_email, name="Other Lead")]

    response = test_client.put(f"/api/v1/leads/{lead_id}", json=update_payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Email {conflicting_email} already exists" in response.json()['detail']

def test_update_lead_no_update_data(test_client):
    lead_id = 1
    response = test_client.put(f"/api/v1/leads/{lead_id}", json={}) # Empty payload
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "No fields provided for update" in response.json()['detail']

@patch('src.web_app.routers.leads.db_utils.update_entity', return_value=None) # update fails
@patch('src.web_app.routers.leads.db_utils.get_entity') # subsequent check *finds* the lead
def test_update_lead_db_failure(mock_get_entity_check, mock_update_entity, test_client):
    lead_id = 1
    update_payload = {"name": "Update Fail"}
    # Simulate get_entity finding the lead when checked after update_entity failed
    mock_get_entity_check.return_value = models.Lead(id=lead_id, name="Original Name") 

    response = test_client.put(f"/api/v1/leads/{lead_id}", json=update_payload)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to update lead" in response.json()['detail']
    mock_update_entity.assert_called_once()
    mock_get_entity_check.assert_called_once()

# --- Tests for DELETE /leads/{lead_id} ---
@patch('src.web_app.routers.leads.db_utils.delete_entity', return_value=True)
def test_delete_lead_success(mock_delete_entity, test_client):
    lead_id = 1
    response = test_client.delete(f"/api/v1/leads/{lead_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete_entity.assert_called_once()
    args, kwargs = mock_delete_entity.call_args
    assert args[1] == models.Lead
    assert args[2] == lead_id
    # No response body for 204
    assert not response.content

@patch('src.web_app.routers.leads.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.leads.db_utils.get_entity', return_value=None) # Check finds lead doesn't exist
def test_delete_lead_not_found(mock_get_entity, mock_delete_entity, test_client):
    lead_id = 999
    response = test_client.delete(f"/api/v1/leads/{lead_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Lead not found" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once() # Called after delete failed

@patch('src.web_app.routers.leads.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.leads.db_utils.get_entity') # Check finds lead *does* exist
def test_delete_lead_db_failure(mock_get_entity, mock_delete_entity, test_client):
    lead_id = 1
    mock_get_entity.return_value = models.Lead(id=lead_id, name="Existing Lead") # Simulate lead exists
    response = test_client.delete(f"/api/v1/leads/{lead_id}")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to delete lead" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once() 