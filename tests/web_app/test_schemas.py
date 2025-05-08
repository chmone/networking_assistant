# Initial test file for schemas.py
import pytest
from pydantic import ValidationError
# from datetime import datetime, timezone
import datetime

# Assuming the schemas are in src/web_app/schemas.py
from src.web_app.schemas import (
    LeadBase, LeadCreate, LeadUpdate, LeadRead, LeadStatusEnum,
    CompanyBase, CompanyCreate, CompanyUpdate, CompanyRead,
    JobPostingBase, JobPostingCreate, JobPostingUpdate, JobPostingRead
)

# --- Tests for Lead Schemas ---
class TestLeadSchemas:

    def test_lead_base_valid(self):
        data = {"name": "Test Lead", "email": "test@example.com", "status": LeadStatusEnum.CONTACTED}
        lead = LeadBase(**data)
        assert lead.name == "Test Lead"
        assert lead.email == "test@example.com"
        assert lead.status == LeadStatusEnum.CONTACTED
        assert lead.phone is None # Check default

    def test_lead_base_invalid_email(self):
        with pytest.raises(ValidationError):
            LeadBase(name="Test Lead", email="invalid-email")

    def test_lead_base_missing_name(self):
        with pytest.raises(ValidationError):
            LeadBase(email="test@example.com")

    def test_lead_base_invalid_enum(self):
        with pytest.raises(ValidationError):
            LeadBase(name="Test Lead", status="invalid_status")

    def test_lead_create_inherits_base(self):
        data = {"name": "Create Lead", "source": "Web"}
        lead = LeadCreate(**data)
        assert lead.name == "Create Lead"
        assert lead.source == "Web"
        assert lead.status == LeadStatusEnum.NEW # Default from Base

    def test_lead_update_all_optional(self):
        # Empty data should be valid
        lead_update = LeadUpdate()
        assert lead_update.name is None
        assert lead_update.email is None
        
        # Valid partial update
        data = {"status": LeadStatusEnum.INTERESTED, "notes": "Updated notes"}
        lead_update = LeadUpdate(**data)
        assert lead_update.status == LeadStatusEnum.INTERESTED
        assert lead_update.notes == "Updated notes"
        assert lead_update.name is None

    def test_lead_update_invalid_data(self):
        with pytest.raises(ValidationError):
            LeadUpdate(email="bad-email")

    def test_lead_read_requires_id_timestamps(self):
        base_data = {"name": "Read Lead"}
        with pytest.raises(ValidationError): # Missing id, created_at, updated_at
            LeadRead(**base_data)
        
        now = datetime.datetime.now(datetime.UTC)
        full_data = {
            "id": 1, "name": "Read Lead", "email": "read@example.com", 
            "status": LeadStatusEnum.NEW, "created_at": now, "updated_at": now
        }
        lead_read = LeadRead(**full_data)
        assert lead_read.id == 1
        assert lead_read.name == "Read Lead"
        assert lead_read.created_at == now
        assert lead_read.status == LeadStatusEnum.NEW # Check enum serialization handled by Config

# --- Tests for Company Schemas ---
class TestCompanySchemas:
    def test_company_base_valid(self):
        data = {"name": "Test Co", "website": "http://testco.com", "industry": "Tech"}
        company = CompanyBase(**data)
        assert company.name == "Test Co"
        assert str(company.website) == "http://testco.com/" # Pydantic HttpUrl adds trailing slash
        assert company.industry == "Tech"
        assert company.size is None # Default

    def test_company_base_invalid_url(self):
        with pytest.raises(ValidationError):
            CompanyBase(name="Test Co", website="invalid-url")

    def test_company_base_missing_name(self):
        with pytest.raises(ValidationError):
            CompanyBase(website="http://testco.com")

    def test_company_create_inherits_base(self):
        data = {"name": "Create Co", "location": "Remote"}
        company = CompanyCreate(**data)
        assert company.name == "Create Co"
        assert company.location == "Remote"

    def test_company_update_all_optional(self):
        company_update = CompanyUpdate()
        assert company_update.name is None
        assert company_update.website is None

        data = {"industry": "Finance", "description": "Financial Services"}
        company_update = CompanyUpdate(**data)
        assert company_update.industry == "Finance"
        assert company_update.description == "Financial Services"
        assert company_update.name is None

    def test_company_update_invalid_data(self):
        with pytest.raises(ValidationError):
            CompanyUpdate(website="invalid-url")

    def test_company_read_requires_id_timestamps(self):
        base_data = {"name": "Read Co"}
        with pytest.raises(ValidationError): # Missing id, created_at, updated_at
            CompanyRead(**base_data)
        
        now = datetime.datetime.now(datetime.UTC)
        full_data = {
            "id": 2, "name": "Read Co", "website": "http://readco.com", 
            "industry": "Media", "created_at": now, "updated_at": now
        }
        company_read = CompanyRead(**full_data)
        assert company_read.id == 2
        assert company_read.name == "Read Co"
        assert company_read.created_at == now
        assert str(company_read.website) == "http://readco.com/"

# --- Tests for JobPosting Schemas ---
class TestJobPostingSchemas:
    def test_job_posting_base_valid(self):
        data = {"title": "Software Engineer", "location": "Remote", "job_url": "http://jobs.com/1"}
        job = JobPostingBase(**data)
        assert job.title == "Software Engineer"
        assert job.location == "Remote"
        assert str(job.job_url) == "http://jobs.com/1" # HttpUrl does not add trailing slash here?
        assert job.status == "Open" # Default
        assert job.description is None # Default

    def test_job_posting_base_invalid_url(self):
        with pytest.raises(ValidationError):
            JobPostingBase(title="Job", job_url="not-a-url")

    def test_job_posting_base_missing_title(self):
        with pytest.raises(ValidationError):
            JobPostingBase(location="Remote")

    def test_job_posting_create_inherits_base(self):
        data = {"title": "Create Job", "company_id": 1}
        job = JobPostingCreate(**data)
        assert job.title == "Create Job"
        assert job.company_id == 1
        assert job.status == "Open"

    def test_job_posting_update_all_optional(self):
        job_update = JobPostingUpdate()
        assert job_update.title is None
        assert job_update.status is None

        data = {"status": "Closed", "description": "Filled"}
        job_update = JobPostingUpdate(**data)
        assert job_update.status == "Closed"
        assert job_update.description == "Filled"
        assert job_update.title is None

    def test_job_posting_update_invalid_data(self):
        with pytest.raises(ValidationError):
            JobPostingUpdate(job_url="invalid")

    def test_job_posting_read_requires_id_timestamps(self):
        base_data = {"title": "Read Job"}
        with pytest.raises(ValidationError): # Missing id, created_at, updated_at
            JobPostingRead(**base_data)
        
        now = datetime.datetime.now(datetime.UTC)
        full_data = {
            "id": 3, "title": "Read Job", "location": "Hybrid", 
            "status": "Open", "created_at": now, "updated_at": now
        }
        job_read = JobPostingRead(**full_data)
        assert job_read.id == 3
        assert job_read.title == "Read Job"
        assert job_read.created_at == now
        assert job_read.status == "Open" 