# Initial test file for db_utils.py
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import asc, desc # Required for tests involving order_by
import datetime # Import datetime

from src.database.db_utils import (
    create_entity, get_entity, get_entities, update_entity, delete_entity,
    add_lead_to_job_posting, remove_lead_from_job_posting, 
    get_lead_applications, get_job_applicants
)
from src.database.models import Lead, Company, JobPosting, LeadStatus # Using actual models for type hints and structure
from src.core.exceptions import DataProcessingError

# Mock for a generic SQLAlchemy model instance for testing
class MockBaseModel:
    id: int
    def __init__(self, **kwargs):
        self.id = kwargs.pop('id', None) # Simulate id assignment on commit/refresh
        for key, value in kwargs.items():
            setattr(self, key, value)

@pytest.fixture
def mock_db_session():
    session = MagicMock()
    # Configure common session methods
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock(side_effect=lambda instance: setattr(instance, 'id', getattr(instance, 'id', 123)) if instance else None)
    session.rollback = MagicMock()
    session.query = MagicMock()
    # session.execute for relationship table operations if needed later
    session.execute = MagicMock()
    return session

# Tests for create_entity
class TestCreateEntity:
    def test_create_entity_success(self, mock_db_session):
        lead_data = {"name": "Test Lead", "status": LeadStatus.NEW}
        # Ensure the mock lead has all necessary fields for Lead model if it matters
        mock_lead_instance = Lead(id=1, **lead_data, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC))
        
        # We are testing db_utils.create_entity, not the Lead model itself directly in this call
        # The create_entity function will instantiate the model internally.
        # So, we don't mock Lead itself, but check db_session.add and db_session.commit

        created_lead = create_entity(mock_db_session, Lead, lead_data)
        
        mock_db_session.add.assert_called_once() # Check that add was called with an instance of Lead
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(mock_db_session.add.call_args[0][0])
        
        assert created_lead is not None
        assert created_lead.name == lead_data["name"]
        # For this test, we assume db_utils.create_entity handles instantiation correctly

    @patch('src.database.db_utils.logger')
    def test_create_entity_integrity_error(self, mock_logger, mock_db_session):
        lead_data = {"name": "Fail Lead"}
        mock_db_session.commit.side_effect = IntegrityError("mocked error", params=None, orig=None)
        
        with pytest.raises(DataProcessingError) as exc_info:
            create_entity(mock_db_session, Lead, lead_data)
        
        mock_db_session.add.assert_called_once() # Add is called before commit
        mock_db_session.rollback.assert_called_once()
        assert "Database integrity error" in str(exc_info.value)
        mock_logger.error.assert_called_once()

    @patch('src.database.db_utils.logger')
    def test_create_entity_unexpected_error(self, mock_logger, mock_db_session):
        lead_data = {"name": "Unexpected Fail Lead"}
        mock_db_session.commit.side_effect = Exception("unexpected db error")

        with pytest.raises(DataProcessingError) as exc_info:
            create_entity(mock_db_session, Lead, lead_data)

        mock_db_session.add.assert_called_once()
        mock_db_session.rollback.assert_called_once() # Rollback should be called
        assert "Unexpected error creating Lead: unexpected db error" in str(exc_info.value)
        mock_logger.error.assert_called_once()

# Tests for get_entity
class TestGetEntity:
    def test_get_entity_found(self, mock_db_session):
        entity_id = 1
        mock_entity_instance = MockBaseModel(id=entity_id, name="Found Entity")
        
        # Configure the mock query chain
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_entity_instance
        
        # Using Company as a concrete model type for the test, could be any model
        retrieved_entity = get_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.query.assert_called_once_with(Company)
        # Check that filter was called with an expression comparing Company.id to entity_id
        # This is a bit tricky to assert perfectly without inspecting the SQL expression object.
        # A common way is to check that filter was called, and trust SQLAlchemy if the construction was right.
        mock_query.filter.assert_called_once()
        # We can check the `model.id == entity_id` part more indirectly by ensuring `first` was called on the result of `filter`
        mock_filter.first.assert_called_once()
        assert retrieved_entity is mock_entity_instance

    def test_get_entity_not_found(self, mock_db_session):
        entity_id = 2
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = None # Simulate not found
        
        retrieved_entity = get_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.query.assert_called_once_with(Company)
        mock_query.filter.assert_called_once()
        mock_filter.first.assert_called_once()
        assert retrieved_entity is None

    def test_get_entity_sqlalchemy_error(self, mock_db_session):
        entity_id = 3
        mock_db_session.query.side_effect = SQLAlchemyError("DB error during query")
        
        retrieved_entity = get_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.query.assert_called_once_with(Company)
        assert retrieved_entity is None

    def test_get_entity_unexpected_error(self, mock_db_session):
        entity_id = 4
        # Simulate an error deeper in the query chain if query() itself doesn't fail
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.side_effect = Exception("Unexpected processing error")

        retrieved_entity = get_entity(mock_db_session, Company, entity_id)
        assert retrieved_entity is None

# Tests for get_entities
class TestGetEntities:
    def test_get_entities_basic(self, mock_db_session):
        mock_entities = [MockBaseModel(id=1), MockBaseModel(id=2)]
        mock_query = mock_db_session.query.return_value
        mock_offset = mock_query.offset.return_value
        mock_limit = mock_offset.limit.return_value
        mock_limit.all.return_value = mock_entities
        
        # Using Lead as a concrete model type
        entities = get_entities(mock_db_session, Lead)
        
        mock_db_session.query.assert_called_once_with(Lead)
        mock_query.offset.assert_called_once_with(0) # Default skip
        mock_offset.limit.assert_called_once_with(100) # Default limit
        mock_limit.all.assert_called_once()
        assert entities == mock_entities

    def test_get_entities_with_filters(self, mock_db_session):
        mock_query = mock_db_session.query.return_value
        # Make filter itself return the mock_query to allow chaining of filters
        mock_query.filter.return_value = mock_query 
        mock_offset = mock_query.offset.return_value
        mock_limit = mock_offset.limit.return_value
        mock_limit.all.return_value = [MockBaseModel(id=1, name="Filtered Lead")]

        filters = {"name": "Filtered Lead", "status__ilike": "%active%", "non_existent_attr": "value"}
        
        entities = get_entities(mock_db_session, Lead, filters=filters)
        
        mock_db_session.query.assert_called_once_with(Lead)
        # Assert filter was called for 'name' and 'status__ilike'
        # This requires checking the call_args_list or using more specific mock setups for each filter call if needed
        assert mock_query.filter.call_count == 2 
        # Example of checking one specific call (order might vary)
        # Difficult to assert specific filter expressions directly without deeper inspection or helper mocks
        # For now, checking call_count implies it attempted to apply existing attribute filters.

        mock_query.offset.assert_called_once_with(0)
        mock_offset.limit.assert_called_once_with(100)
        mock_limit.all.assert_called_once()
        assert len(entities) == 1
        assert entities[0].name == "Filtered Lead"

    def test_get_entities_with_sorting(self, mock_db_session):
        # Mock the query chain more directly
        mock_query_obj = MagicMock() # Represents the Query object
        mock_db_session.query.return_value = mock_query_obj
        mock_query_obj.filter.return_value = mock_query_obj # filter returns self for chaining
        mock_query_obj.order_by.return_value = mock_query_obj # order_by returns self
        mock_query_obj.offset.return_value = mock_query_obj # offset returns self
        mock_query_obj.limit.return_value = mock_query_obj # limit returns self
        mock_query_obj.all.return_value = [Lead(name="Sorted Lead")]

        leads = get_entities(mock_db_session, Lead, filters={}, order_by_column=Lead.name, sort_direction='asc')

        mock_db_session.query.assert_called_once_with(Lead)
        mock_query_obj.filter.assert_not_called() # Changed from assert_called_once_with()
        mock_query_obj.order_by.assert_called_once() # Called once after query (since no filter)
        args, _ = mock_query_obj.order_by.call_args
        assert args[0].compare(Lead.name.asc()) # Check the SQLAlchemy expression

        mock_query_obj.offset.assert_called_once_with(0)
        mock_query_obj.limit.assert_called_once_with(100) # Default limit
        mock_query_obj.all.assert_called_once()
        assert len(leads) == 1
        assert leads[0].name == "Sorted Lead"

    def test_get_entities_desc_sorting(self, mock_db_session):
        # Similar simplified setup
        mock_query_obj = MagicMock()
        mock_db_session.query.return_value = mock_query_obj
        mock_query_obj.filter.return_value = mock_query_obj
        mock_query_obj.order_by.return_value = mock_query_obj
        mock_query_obj.offset.return_value = mock_query_obj
        mock_query_obj.limit.return_value = mock_query_obj
        mock_query_obj.all.return_value = [Lead(name="Sorted Desc Lead")]

        get_entities(mock_db_session, Lead, filters={}, order_by_column=Lead.name, sort_direction='desc')
        
        mock_db_session.query.assert_called_once_with(Lead) # Ensure query reset if needed
        mock_query_obj.filter.assert_not_called() # Changed from assert_called_once_with()
        mock_query_obj.order_by.assert_called_once() 
        args, _ = mock_query_obj.order_by.call_args
        assert args[0].compare(Lead.name.desc())
        mock_query_obj.offset.assert_called_once_with(0)
        mock_query_obj.limit.assert_called_once_with(100)
        mock_query_obj.all.assert_called_once()

    def test_get_entities_with_pagination(self, mock_db_session):
        mock_query = mock_db_session.query.return_value
        mock_offset = mock_query.offset.return_value
        mock_limit = mock_offset.limit.return_value
        mock_limit.all.return_value = [MockBaseModel(id=1)]
        
        skip, limit = 10, 50
        get_entities(mock_db_session, Lead, skip=skip, limit=limit)
        
        mock_query.offset.assert_called_once_with(skip)
        mock_offset.limit.assert_called_once_with(limit)

    def test_get_entities_sqlalchemy_error(self, mock_db_session):
        mock_db_session.query.side_effect = SQLAlchemyError("DB error")
        entities = get_entities(mock_db_session, Lead)
        assert entities == []

    def test_get_entities_unexpected_error(self, mock_db_session):
        mock_query = mock_db_session.query.return_value
        mock_query.offset.side_effect = Exception("Unexpected error")
        entities = get_entities(mock_db_session, Lead)
        assert entities == []

    def test_get_entities_filter_none_value(self, mock_db_session):
        mock_query = mock_db_session.query.return_value
        mock_offset = mock_query.offset.return_value
        mock_limit = mock_offset.limit.return_value
        mock_limit.all.return_value = []

        filters = {"name": None} # Filter with None value should be skipped
        get_entities(mock_db_session, Lead, filters=filters)
        mock_query.filter.assert_not_called() # filter should not be called for None value

# Tests for update_entity
class TestUpdateEntity:
    def test_update_entity_success(self, mock_db_session):
        entity_id = 1
        update_data = {"name": "Updated Name", "status": "updated_status"}
        # Mock the entity instance that query().get() will return
        mock_entity_instance = MockBaseModel(id=entity_id, name="Old Name", status="old_status") 
        
        mock_query = mock_db_session.query.return_value
        mock_query.get.return_value = mock_entity_instance
        
        # Call the function under test
        updated_entity = update_entity(mock_db_session, Company, entity_id, update_data)
        
        mock_db_session.query.assert_called_once_with(Company)
        mock_query.get.assert_called_once_with(entity_id)
        
        # Check that attributes were updated on the mock instance
        assert mock_entity_instance.name == "Updated Name"
        assert mock_entity_instance.status == "updated_status"
        
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once_with(mock_entity_instance)
        assert updated_entity is mock_entity_instance

    def test_update_entity_not_found(self, mock_db_session):
        entity_id = 99
        update_data = {"name": "Updated Name"}
        
        mock_query = mock_db_session.query.return_value
        mock_query.get.return_value = None # Simulate entity not found
        
        updated_entity = update_entity(mock_db_session, Company, entity_id, update_data)
        
        mock_db_session.query.assert_called_once_with(Company)
        mock_query.get.assert_called_once_with(entity_id)
        mock_db_session.commit.assert_not_called()
        mock_db_session.refresh.assert_not_called()
        assert updated_entity is None

    def test_update_entity_integrity_error(self, mock_db_session):
        entity_id = 1
        update_data = {"name": "Unique Name Violation"}
        mock_entity_instance = MockBaseModel(id=entity_id, name="Old Name")
        
        mock_query = mock_db_session.query.return_value
        mock_query.get.return_value = mock_entity_instance
        mock_db_session.commit.side_effect = IntegrityError("mock statement", "mock params", "mock orig")
        
        updated_entity = update_entity(mock_db_session, Company, entity_id, update_data)
        
        assert mock_entity_instance.name == "Unique Name Violation" # setattr happens before commit
        mock_db_session.commit.assert_called_once()
        mock_db_session.rollback.assert_called_once()
        mock_db_session.refresh.assert_not_called()
        assert updated_entity is None

    def test_update_entity_sqlalchemy_error_on_commit(self, mock_db_session):
        entity_id = 1
        update_data = {"name": "New Name"}
        mock_entity_instance = MockBaseModel(id=entity_id, name="Old Name")
        
        mock_query = mock_db_session.query.return_value
        mock_query.get.return_value = mock_entity_instance
        mock_db_session.commit.side_effect = SQLAlchemyError("DB error on commit")
        
        updated_entity = update_entity(mock_db_session, Company, entity_id, update_data)

        mock_db_session.rollback.assert_called_once()
        assert updated_entity is None

    def test_update_entity_update_non_existent_attribute(self, mock_db_session):
        # This should log a warning but proceed with other valid attributes
        entity_id = 1
        update_data = {"name": "Good Update", "non_existent_field": "bad_value"}
        mock_entity_instance = Company(id=entity_id, name="Old Name") # Use a real model for hasattr check
        
        mock_query = mock_db_session.query.return_value
        mock_query.get.return_value = mock_entity_instance
        
        updated_entity = update_entity(mock_db_session, Company, entity_id, update_data)
        
        assert mock_entity_instance.name == "Good Update"
        assert not hasattr(mock_entity_instance, "non_existent_field")
        mock_db_session.commit.assert_called_once()
        assert updated_entity is mock_entity_instance

# Tests for delete_entity
class TestDeleteEntity:
    def test_delete_entity_success(self, mock_db_session):
        entity_id = 1
        mock_entity_instance = MockBaseModel(id=entity_id)
        
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_entity_instance
        
        result = delete_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.query.assert_called_once_with(Company)
        # mock_query.filter.assert_called_once_with(Company.id == entity_id) # simplified check
        mock_query.filter.assert_called_once()
        mock_filter.first.assert_called_once()
        mock_db_session.delete.assert_called_once_with(mock_entity_instance)
        mock_db_session.commit.assert_called_once()
        assert result is True

    def test_delete_entity_not_found(self, mock_db_session):
        entity_id = 99
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = None # Simulate not found
        
        result = delete_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.delete.assert_not_called()
        mock_db_session.commit.assert_not_called()
        assert result is False

    def test_delete_entity_sqlalchemy_error_on_delete(self, mock_db_session):
        entity_id = 1
        mock_entity_instance = MockBaseModel(id=entity_id)
        
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_entity_instance
        mock_db_session.delete.side_effect = SQLAlchemyError("DB error on delete")
        
        result = delete_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called() # Commit should not be reached
        assert result is False

    def test_delete_entity_sqlalchemy_error_on_commit(self, mock_db_session):
        entity_id = 1
        mock_entity_instance = MockBaseModel(id=entity_id)
        
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_entity_instance
        mock_db_session.commit.side_effect = SQLAlchemyError("DB error on commit")
        
        result = delete_entity(mock_db_session, Company, entity_id)
        
        mock_db_session.delete.assert_called_once_with(mock_entity_instance)
        mock_db_session.rollback.assert_called_once()
        assert result is False

# Tests for Many-to-Many relationship functions
# Mock Lead and JobPosting instances with relationship attributes
@pytest.fixture
def mock_lead_instance():
    lead = MagicMock(spec=Lead) # Use spec to get attributes like applied_jobs if they exist on Lead
    lead.id = 1
    lead.name = "Test Lead"
    lead.applied_jobs = [] # Mock the relationship attribute as a list
    return lead

@pytest.fixture
def mock_job_instance():
    job = MagicMock(spec=JobPosting)
    job.id = 101
    job.title = "Test Job"
    job.applicants = [] # Mock the relationship attribute as a list
    return job

class TestJobApplicationFunctions:
    @patch('src.database.db_utils.get_entity')
    def test_add_lead_to_job_posting_success(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        # Configure get_entity to return our mock instances
        def get_entity_side_effect(db_sess, model_cls, entity_id):
            if model_cls == Lead and entity_id == mock_lead_instance.id: return mock_lead_instance
            if model_cls == JobPosting and entity_id == mock_job_instance.id: return mock_job_instance
            return None
        mock_get_entity_func.side_effect = get_entity_side_effect
        
        mock_lead_instance.applied_jobs = [] 

        result = add_lead_to_job_posting(mock_db_session, mock_lead_instance.id, mock_job_instance.id)
        
        assert mock_get_entity_func.call_count == 2
        assert mock_job_instance in mock_lead_instance.applied_jobs
        mock_db_session.commit.assert_called_once()
        assert result is True

    @patch('src.database.db_utils.get_entity')
    def test_add_lead_to_job_posting_already_associated(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        mock_get_entity_func.side_effect = [mock_lead_instance, mock_job_instance]
        mock_lead_instance.applied_jobs = [mock_job_instance]

        result = add_lead_to_job_posting(mock_db_session, mock_lead_instance.id, mock_job_instance.id)
        
        assert len(mock_lead_instance.applied_jobs) == 1
        mock_db_session.commit.assert_not_called()
        assert result is True

    @patch('src.database.db_utils.get_entity', return_value=None)
    def test_add_lead_to_job_posting_lead_not_found(self, mock_get_entity_func, mock_db_session, mock_job_instance):
        result = add_lead_to_job_posting(mock_db_session, 999, mock_job_instance.id)
        mock_db_session.commit.assert_not_called()
        assert result is False

    @patch('src.database.db_utils.get_entity')
    def test_add_lead_to_job_posting_job_not_found(self, mock_get_entity_func, mock_db_session, mock_lead_instance):
        mock_get_entity_func.side_effect = [mock_lead_instance, None]
        result = add_lead_to_job_posting(mock_db_session, mock_lead_instance.id, 999)
        mock_db_session.commit.assert_not_called()
        assert result is False

    @patch('src.database.db_utils.get_entity')
    def test_add_lead_to_job_posting_db_error(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        mock_get_entity_func.side_effect = [mock_lead_instance, mock_job_instance]
        mock_lead_instance.applied_jobs = []
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit error")
        
        result = add_lead_to_job_posting(mock_db_session, mock_lead_instance.id, mock_job_instance.id)
        
        mock_db_session.rollback.assert_called_once()
        assert result is False
    
    @patch('src.database.db_utils.get_entity')
    def test_remove_lead_from_job_posting_success(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        mock_get_entity_func.side_effect = [mock_lead_instance, mock_job_instance]
        mock_lead_instance.applied_jobs = [mock_job_instance]

        result = remove_lead_from_job_posting(mock_db_session, mock_lead_instance.id, mock_job_instance.id)
        
        assert mock_job_instance not in mock_lead_instance.applied_jobs
        mock_db_session.commit.assert_called_once()
        assert result is True

    @patch('src.database.db_utils.get_entity')
    def test_remove_lead_from_job_posting_not_associated(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        mock_get_entity_func.side_effect = [mock_lead_instance, mock_job_instance]
        mock_lead_instance.applied_jobs = []

        result = remove_lead_from_job_posting(mock_db_session, mock_lead_instance.id, mock_job_instance.id)
        
        mock_db_session.commit.assert_not_called()
        assert result is False

    @patch('src.database.db_utils.get_entity')
    def test_get_lead_applications(self, mock_get_entity_func, mock_db_session, mock_lead_instance, mock_job_instance):
        mock_get_entity_func.return_value = mock_lead_instance
        mock_lead_instance.applied_jobs = [mock_job_instance, MagicMock(spec=JobPosting)]
        
        applications = get_lead_applications(mock_db_session, mock_lead_instance.id)
        mock_get_entity_func.assert_called_once_with(mock_db_session, Lead, mock_lead_instance.id)
        assert applications == mock_lead_instance.applied_jobs

    @patch('src.database.db_utils.get_entity', return_value=None)
    def test_get_lead_applications_lead_not_found(self, mock_get_entity_func, mock_db_session):
        applications = get_lead_applications(mock_db_session, 999)
        assert applications == []

    @patch('src.database.db_utils.get_entity')
    def test_get_job_applicants(self, mock_get_entity_func, mock_db_session, mock_job_instance, mock_lead_instance):
        mock_get_entity_func.return_value = mock_job_instance
        mock_job_instance.applicants = [mock_lead_instance, MagicMock(spec=Lead)]
        
        applicants = get_job_applicants(mock_db_session, mock_job_instance.id)
        mock_get_entity_func.assert_called_once_with(mock_db_session, JobPosting, mock_job_instance.id)
        assert applicants == mock_job_instance.applicants

    @patch('src.database.db_utils.get_entity', return_value=None)
    def test_get_job_applicants_job_not_found(self, mock_get_entity_func, mock_db_session):
        applicants = get_job_applicants(mock_db_session, 999)
        assert applicants == []

# TODO: Add test cases for other db_utils functions 