# Initial test file for jobs router
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import datetime

from src.web_app.api_main import app 
from src.database import models
from src.web_app import schemas
from src.web_app.api_main import get_db

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

# --- Tests for POST /jobs/ ---
@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=MagicMock()) # Company check passes
@patch('src.web_app.routers.jobs.db_utils.get_entities', return_value=[]) # No existing job URL
@patch('src.web_app.routers.jobs.db_utils.create_entity')
def test_create_job_success(mock_create, mock_get_entities, mock_get_entity, test_client):
    job_data = {"title": "New Job", "company_id": 1, "job_url": "http://newjob.com", "status": "Open", "job_type": "Full-time"}
    mock_get_entity.return_value = MagicMock() # Company found
    mock_get_entities.return_value = [] # No job with this URL for this company
    
    mock_created_db_job = models.JobPosting(
        id=1, 
        title=job_data['title'], 
        company_id=job_data['company_id'], 
        job_url=job_data['job_url'], 
        status=job_data['status'], 
        job_type=models.JobType.FULL_TIME,
        created_at=datetime.datetime.now(datetime.UTC),
        updated_at=datetime.datetime.now(datetime.UTC)
    )
    mock_create.return_value = mock_created_db_job

    response = test_client.post("/api/v1/jobs/", json=job_data)

    assert response.status_code == status.HTTP_201_CREATED
    mock_get_entity.assert_called_once() # Company check
    mock_get_entities.assert_called_once() # URL check
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[1] == models.JobPosting
    assert args[2]['title'] == job_data['title']
    
    response_data = response.json()
    assert response_data['id'] == mock_created_db_job.id
    assert response_data['title'] == job_data['title']
    assert response_data['job_url'] # Pydantic validated

@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=None) # Company check fails
def test_create_job_company_not_found(mock_get_entity, test_client):
    job_data = {"title": "New Job", "company_id": 999}
    response = test_client.post("/api/v1/jobs/", json=job_data)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company with id 999 not found" in response.json()['detail']

@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=MagicMock()) # Company check passes
@patch('src.web_app.routers.jobs.db_utils.get_entities') # URL check fails
def test_create_job_url_exists_for_company(mock_get_entities, mock_get_entity, test_client):
    job_data = {"title": "New Job", "company_id": 1, "job_url": "http://jobs.com/existing"}
    mock_get_entities.return_value = [models.JobPosting(id=5, job_url=job_data['job_url'], company_id=1, title="Existing Job")]
    
    response = test_client.post("/api/v1/jobs/", json=job_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Job posting with URL {job_data['job_url']} already exists for company ID {job_data['company_id']}" in response.json()['detail']

@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=MagicMock())
@patch('src.web_app.routers.jobs.db_utils.get_entities', return_value=[])
@patch('src.web_app.routers.jobs.db_utils.create_entity', return_value=None) # DB failure
def test_create_job_db_failure(mock_create, mock_get_entities, mock_get_entity, test_client):
    job_data = {"title": "Fail Job", "company_id": 1}
    response = test_client.post("/api/v1/jobs/", json=job_data)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to create job posting" in response.json()['detail']

# --- Tests for GET /jobs/ ---
@patch('src.web_app.routers.jobs.db_utils.get_entities')
def test_read_jobs_defaults(mock_get_entities, test_client):
    mock_jobs_db = [
        models.JobPosting(id=1, title="Job A", company_id=1, status="Open", job_type=models.JobType.FULL_TIME, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)),
        models.JobPosting(id=2, title="Job B", company_id=2, status="Closed", job_type=models.JobType.CONTRACT, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    ]
    mock_get_entities.return_value = mock_jobs_db

    response = test_client.get("/api/v1/jobs/")

    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 0
    assert kwargs.get('limit') == 100
    assert kwargs.get('filters') == {}
    
    response_data = response.json()
    assert len(response_data) == 2
    assert response_data[0]['title'] == "Job A"

@patch('src.web_app.routers.jobs.db_utils.get_entities')
def test_read_jobs_with_params(mock_get_entities, test_client):
    mock_jobs_db = [models.JobPosting(id=3, title="Filtered Job", company_id=5, status="Open", created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))]
    mock_get_entities.return_value = mock_jobs_db

    response = test_client.get("/api/v1/jobs/?skip=10&limit=5&company_id=5&status=Open")
    
    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_called_once()
    args, kwargs = mock_get_entities.call_args
    assert kwargs.get('skip') == 10
    assert kwargs.get('limit') == 5
    assert kwargs.get('filters') == {'company_id': 5, 'status': 'Open'}

    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]['title'] == "Filtered Job"

@patch('src.web_app.routers.jobs.db_utils.get_entities', return_value=[])
def test_read_jobs_no_results(mock_get_entities, test_client):
    response = test_client.get("/api/v1/jobs/?status=Closed")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

# --- Tests for GET /jobs/{job_id} ---
@patch('src.web_app.routers.jobs.db_utils.get_entity')
def test_read_job_success(mock_get_entity, test_client):
    job_id = 1
    mock_job_db = models.JobPosting(id=job_id, title="Found Job", company_id=1, status="Open", job_type=models.JobType.PART_TIME, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_get_entity.return_value = mock_job_db

    response = test_client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == status.HTTP_200_OK
    mock_get_entity.assert_called_once()
    args, kwargs = mock_get_entity.call_args
    assert args[1] == models.JobPosting
    assert args[2] == job_id

    response_data = response.json()
    assert response_data['id'] == job_id
    assert response_data['title'] == "Found Job"

@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=None)
def test_read_job_not_found(mock_get_entity, test_client):
    job_id = 999
    response = test_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Job posting not found" in response.json()['detail']
    mock_get_entity.assert_called_once()

# --- Tests for PUT /jobs/{job_id} ---
@patch('src.web_app.routers.jobs.db_utils.get_entity') # Mocks company check and the check within URL conflict logic
@patch('src.web_app.routers.jobs.db_utils.get_entities', return_value=[]) # No URL conflict
@patch('src.web_app.routers.jobs.db_utils.update_entity')
def test_update_job_success(mock_update_entity, mock_get_entities, mock_get_entity, test_client):
    job_id = 1
    update_payload = {"title": "Updated Job Title", "status": "Closed", "job_type": "Contract"}
    mock_updated_db_job = models.JobPosting(id=job_id, title="Updated Job Title", status="Closed", job_type=models.JobType.CONTRACT, company_id=1, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
    mock_update_entity.return_value = mock_updated_db_job
    mock_get_entity.return_value = MagicMock() # For company check
    mock_get_entities.return_value = [] # No URL conflict

    response = test_client.put(f"/api/v1/jobs/{job_id}", json=update_payload)

    assert response.status_code == status.HTTP_200_OK
    mock_get_entities.assert_not_called()
    mock_update_entity.assert_called_once()
    args, kwargs = mock_update_entity.call_args
    assert args[2] == job_id
    assert args[3] == update_payload
    
    response_data = response.json()
    assert response_data['title'] == update_payload['title']
    assert response_data['status'] == update_payload['status']

@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=None) # Company check fails
def test_update_job_company_not_found(mock_get_entity, test_client):
    job_id = 1
    update_payload = {"company_id": 999}
    response = test_client.put(f"/api/v1/jobs/{job_id}", json=update_payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Company with id 999 not found" in response.json()['detail']

@patch('src.web_app.routers.jobs.db_utils.get_entity') # Mocks job check and company check
@patch('src.web_app.routers.jobs.db_utils.get_entities') # URL conflict exists
def test_update_job_url_conflict(mock_get_entities, mock_get_entity, test_client):
    job_id = 1
    target_company_id = 5
    conflicting_url = "http://jobs.com/taken"
    update_payload = {"job_url": conflicting_url, "company_id": target_company_id}
    
    # Simulate get_entity finding the job being updated (needed for company_id context)
    # and finding the company (target_company_id) exists
    mock_job_being_updated = models.JobPosting(id=job_id, company_id=target_company_id) # Original job
    mock_company = models.Company(id=target_company_id)
    mock_get_entity.side_effect = [mock_company, mock_job_being_updated] # First call for company, second for job

    # Simulate get_entities finding another job (id=2) with the same URL and company
    mock_get_entities.return_value = [models.JobPosting(id=2, job_url=conflicting_url, company_id=target_company_id, title="Other Job")]

    response = test_client.put(f"/api/v1/jobs/{job_id}", json=update_payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Job posting URL {conflicting_url} already exists for company ID {target_company_id}" in response.json()['detail']
    # Check calls: get_entity for company, get_entity for job (inside check), get_entities for conflict
    assert mock_get_entity.call_count == 2
    mock_get_entities.assert_called_once()

def test_update_job_no_update_data(test_client):
    job_id = 1
    response = test_client.put(f"/api/v1/jobs/{job_id}", json={})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "No fields provided for update" in response.json()['detail']

@patch('src.web_app.routers.jobs.db_utils.update_entity', return_value=None) # update fails
@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=None) # check confirms not found
def test_update_job_not_found(mock_get_entity_check, mock_update_entity, test_client):
    job_id = 999
    update_payload = {"title": "Update Nonexistent"}

    response = test_client.put(f"/api/v1/jobs/{job_id}", json=update_payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Job posting not found" in response.json()['detail']
    mock_update_entity.assert_called_once()
    mock_get_entity_check.assert_called_once() # Called after update failed

@patch('src.web_app.routers.jobs.db_utils.update_entity', return_value=None) # update fails
@patch('src.web_app.routers.jobs.db_utils.get_entity') # check finds job exists
def test_update_job_db_failure(mock_get_entity_check, mock_update_entity, test_client):
    job_id = 1
    update_payload = {"title": "Update Fail"}
    mock_get_entity_check.return_value = models.JobPosting(id=job_id, title="Original Job")

    response = test_client.put(f"/api/v1/jobs/{job_id}", json=update_payload)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to update job posting" in response.json()['detail']
    mock_update_entity.assert_called_once()
    mock_get_entity_check.assert_called_once()

# --- Tests for DELETE /jobs/{job_id} ---
@patch('src.web_app.routers.jobs.db_utils.delete_entity', return_value=True)
def test_delete_job_success(mock_delete_entity, test_client):
    job_id = 1
    response = test_client.delete(f"/api/v1/jobs/{job_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete_entity.assert_called_once()
    args, kwargs = mock_delete_entity.call_args
    assert args[1] == models.JobPosting
    assert args[2] == job_id
    assert not response.content

@patch('src.web_app.routers.jobs.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.jobs.db_utils.get_entity', return_value=None)
def test_delete_job_not_found(mock_get_entity, mock_delete_entity, test_client):
    job_id = 999
    response = test_client.delete(f"/api/v1/jobs/{job_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Job posting not found" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once()

@patch('src.web_app.routers.jobs.db_utils.delete_entity', return_value=False)
@patch('src.web_app.routers.jobs.db_utils.get_entity')
def test_delete_job_db_failure(mock_get_entity, mock_delete_entity, test_client):
    job_id = 1
    mock_get_entity.return_value = models.JobPosting(id=job_id, title="Existing Job") # Simulate job exists
    response = test_client.delete(f"/api/v1/jobs/{job_id}")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to delete job posting" in response.json()['detail']
    mock_delete_entity.assert_called_once()
    mock_get_entity.assert_called_once() 