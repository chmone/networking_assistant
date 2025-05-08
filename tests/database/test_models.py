# Initial test file for models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
# from datetime import datetime, timezone # Import both
import datetime

from src.database.models import Base, Lead, Company, JobPosting, LeadStatus, JobType, job_applications

# In-memory SQLite database for testing
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine) # Create tables

Session = sessionmaker(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Creates a new database session for a test."""
    session = Session()
    yield session
    session.rollback() # Rollback any changes made during the test
    session.close()

# Tests for Lead model
class TestLeadModel:
    def test_create_lead_minimal(self, db_session):
        # Explicitly set expected default value for testing instantiation
        lead = Lead(name="Test Lead", status=LeadStatus.NEW)
        db_session.add(lead)
        db_session.flush()
        assert lead.name == "Test Lead"
        assert lead.status == LeadStatus.NEW 
        assert lead.email is None
        assert lead.phone is None
        assert lead.source is None
        assert lead.notes is None
        assert isinstance(lead.created_at, datetime.datetime)
        assert isinstance(lead.updated_at, datetime.datetime)
        # Relationship attributes should exist
        assert hasattr(lead, 'company')
        assert hasattr(lead, 'applied_jobs')

    def test_create_lead_all_fields(self, db_session):
        now = datetime.datetime.now(datetime.UTC)
        lead = Lead(
            name="Full Lead",
            email="full@example.com",
            phone="1234567890",
            status=LeadStatus.CONTACTED,
            source="Manual",
            notes="Some notes here",
            created_at=now,
            updated_at=now
        )
        db_session.add(lead)
        db_session.flush()
        assert lead.name == "Full Lead"
        assert lead.email == "full@example.com"
        assert lead.phone == "1234567890"
        assert lead.status == LeadStatus.CONTACTED
        assert lead.source == "Manual"
        assert lead.notes == "Some notes here"
        assert lead.created_at == now
        assert lead.updated_at == now
        assert isinstance(lead.created_at, datetime.datetime)
        assert isinstance(lead.updated_at, datetime.datetime)

    def test_lead_repr(self):
        lead = Lead(id=1, name="Repr Lead", status=LeadStatus.INTERESTED)
        assert repr(lead) == "<Lead(id=1, name='Repr Lead', status='interested')>"
    
    def test_lead_repr_no_id_status_none(self):
        lead = Lead(name="No ID Lead")
        lead.status = None # Simulate a case where status might be None before DB flush or if nullable was True
        assert repr(lead) == "<Lead(id=None, name='No ID Lead', status='None')>"

# Tests for Company model
class TestCompanyModel:
    def test_create_company_minimal(self, db_session):
        now = datetime.datetime.now(datetime.UTC) # Use timezone-aware now
        # Explicitly set expected default values for testing instantiation
        company = Company(name="Test Company", created_at=now, updated_at=now)
        db_session.add(company)
        db_session.flush()
        assert company.name == "Test Company"
        assert company.website is None
        assert company.industry is None
        assert company.size is None
        assert company.location is None
        assert company.description is None
        # Assert against the explicitly set datetime
        assert company.created_at == now 
        assert company.updated_at == now
        assert isinstance(company.created_at, datetime.datetime) # Keep type check
        # Relationship attributes should exist
        assert hasattr(company, 'leads')
        assert hasattr(company, 'job_postings')
        assert company.created_at is not None
        assert company.updated_at is not None
        assert isinstance(company.created_at, datetime.datetime)
        assert isinstance(company.updated_at, datetime.datetime)

    def test_create_company_all_fields(self, db_session):
        now = datetime.datetime.now(datetime.UTC)
        company = Company(
            name="Full Company Inc.",
            website="http://fullcompany.com",
            industry="Tech",
            size="1000+",
            location="New York, NY",
            description="A great company.",
            created_at=now,
            updated_at=now
        )
        db_session.add(company)
        db_session.flush()
        assert company.name == "Full Company Inc."
        assert company.website == "http://fullcompany.com"
        assert company.industry == "Tech"
        assert company.size == "1000+"
        assert company.location == "New York, NY"
        assert company.description == "A great company."
        assert company.created_at == now
        assert company.updated_at == now
        assert isinstance(company.created_at, datetime.datetime)
        assert isinstance(company.updated_at, datetime.datetime)

    def test_company_repr(self):
        company = Company(id=1, name="Repr Company")
        assert repr(company) == "<Company(id=1, name='Repr Company')>"
    
    def test_company_repr_no_id(self):
        company = Company(name="No ID Company")
        assert repr(company) == "<Company(id=None, name='No ID Company')>"

# Tests for JobPosting model
class TestJobPostingModel:
    def test_create_job_posting_minimal(self, db_session):
        now = datetime.datetime.now(datetime.UTC) # Use timezone-aware now
        # Explicitly set expected default values for testing instantiation
        job = JobPosting(title="Test Job", status="Open", created_at=now, updated_at=now)
        db_session.add(job)
        db_session.flush()
        assert job.title == "Test Job"
        assert job.status == "Open"
        assert job.description is None
        assert job.requirements is None
        assert job.salary_range is None
        assert job.location is None
        assert job.job_type is None
        # Assert against the explicitly set datetime
        assert job.created_at == now 
        assert job.updated_at == now 
        assert isinstance(job.created_at, datetime.datetime) # Keep type check
        # Relationship attributes should exist
        assert hasattr(job, 'company')
        assert hasattr(job, 'applicants')

    def test_create_job_posting_all_fields(self, db_session):
        now = datetime.datetime.now(datetime.UTC)
        job = JobPosting(
            title="Full Job Posting",
            description="A detailed description.",
            requirements="Many requirements.",
            salary_range="$100k - $150k",
            location="Remote",
            job_type=JobType.FULL_TIME,
            status="Closed",
            created_at=now,
            updated_at=now
        )
        db_session.add(job)
        db_session.flush()
        assert job.title == "Full Job Posting"
        assert job.description == "A detailed description."
        assert job.requirements == "Many requirements."
        assert job.salary_range == "$100k - $150k"
        assert job.location == "Remote"
        assert job.job_type == JobType.FULL_TIME
        assert job.status == "Closed"
        assert job.created_at == now
        assert job.updated_at == now
        assert isinstance(job.created_at, datetime.datetime)
        assert isinstance(job.updated_at, datetime.datetime)

    def test_job_posting_repr(self):
        job = JobPosting(id=1, title="Repr Job", status="Open")
        assert repr(job) == "<JobPosting(id=1, title='Repr Job', status='Open')>"

    def test_job_posting_repr_no_id(self):
        job = JobPosting(title="No ID Job", status="Pending")
        assert repr(job) == "<JobPosting(id=None, title='No ID Job', status='Pending')>"

# TODO: Add test cases for job_applications table (if direct interaction is needed)
# TODO: Add test cases for Enums (LeadStatus, JobType) if they have methods or complex logic (they don't currently) 