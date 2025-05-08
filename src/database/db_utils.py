import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from typing import Type, TypeVar, List, Dict, Any, Optional
from sqlalchemy import asc, desc # Import asc and desc for sorting

# Assuming models.py is in the same directory (src/database/)
from src.database.models import Base, Lead, Company, JobPosting, job_applications
from src.core.exceptions import DataProcessingError

logger = logging.getLogger(__name__)

ModelType = TypeVar('ModelType', bound=Base)

def create_entity(db: Session, model: Type[ModelType], data: Dict[str, Any]) -> Optional[ModelType]:
    """Generic function to create a new entity."""
    try:
        entity = model(**data)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        # logger.info(f"Successfully created {model.__name__} with ID {entity.id}")
        return entity
    except IntegrityError as e:
        db.rollback() # Rollback the session on integrity error
        logger.error(f"Database integrity error creating {model.__name__}: {e}")
        # Optionally re-raise a custom exception or return None
        # Re-raise custom error as expected by the test
        raise DataProcessingError(f"Database integrity error creating {model.__name__}: {e}") from e 
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating {model.__name__}: {e}")
        # Re-raise custom error as expected by the test
        raise DataProcessingError(f"Database error creating {model.__name__}: {e}") from e 
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating {model.__name__}: {e}. Data: {data}")
        # Re-raise custom error as expected by the test
        raise DataProcessingError(f"Unexpected error creating {model.__name__}: {e}") from e 
    # return None # Removed, as exceptions are raised

def get_entity(db: Session, model: Type[ModelType], entity_id: int) -> Optional[ModelType]:
    """Generic function to get an entity by its ID."""
    try:
        entity = db.query(model).filter(model.id == entity_id).first()
        if entity:
            logger.debug(f"Retrieved {model.__name__} with ID {entity_id}")
        else:
            logger.debug(f"{model.__name__} with ID {entity_id} not found.")
        return entity
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error retrieving {model.__name__} ID {entity_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving {model.__name__} ID {entity_id}: {e}")
    return None

def get_entities(db: Session, model: Type[ModelType], 
                   skip: int = 0, limit: int = 100, 
                   filters: Optional[Dict[str, Any]] = None,
                   order_by_column: Optional[Any] = None, # Accept SQLAlchemy column object
                   sort_direction: str = 'asc') -> List[ModelType]:
    """Generic function to retrieve a list of entities with filtering, sorting, and pagination."""
    try:
        query = db.query(model)
        
        # Apply filters
        if filters:
            for key, value in filters.items():
                if value is None: continue # Skip None values in filters
                
                # Handle special filter types (like ilike)
                if key.endswith('__ilike'):
                    actual_key = key[:-7]
                    if hasattr(model, actual_key):
                        query = query.filter(getattr(model, actual_key).ilike(value))
                elif hasattr(model, key):
                    query = query.filter(getattr(model, key) == value)
                else:
                    logger.warning(f"Attempted to filter on non-existent attribute '{key}' for model {model.__name__}")
                    # Optionally raise an error or just ignore

        # Apply sorting
        if order_by_column is not None:
            if sort_direction == 'desc':
                query = query.order_by(desc(order_by_column))
            else:
                query = query.order_by(asc(order_by_column))
        
        # Apply pagination
        entities = query.offset(skip).limit(limit).all()
        # logger.debug(f"Retrieved {len(entities)} entities for model {model.__name__} with skip={skip}, limit={limit}, filters={filters}")
        return entities
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving entities for {model.__name__}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error retrieving entities for {model.__name__}: {e}")
        return []

def update_entity(db: Session, model: Type[ModelType], entity_id: int, data: Dict[str, Any]) -> Optional[ModelType]:
    """Generic function to update an existing entity."""
    try:
        entity = db.query(model).get(entity_id)
        if entity is None:
            logger.warning(f"{model.__name__} with ID {entity_id} not found for update.")
            return None
        
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
            else:
                logger.warning(f"Attempted to update non-existent attribute '{key}' on {model.__name__}")
                
        db.commit()
        db.refresh(entity)
        # logger.info(f"Successfully updated {model.__name__} with ID {entity.id}")
        return entity
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error updating {model.__name__} ID {entity_id}: {e}")
        return None
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating {model.__name__} ID {entity_id}: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error updating {model.__name__} ID {entity_id}: {e}. Data: {data}")
    return None

def delete_entity(db: Session, model: Type[ModelType], entity_id: int) -> bool:
    """Generic function to delete an entity by its ID."""
    try:
        entity = db.query(model).filter(model.id == entity_id).first()
        if entity:
            db.delete(entity)
            db.commit()
            logger.info(f"Successfully deleted {model.__name__} with ID {entity_id}")
            return True
        else:
            logger.warning(f"{model.__name__} with ID {entity_id} not found for deletion.")
            return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"SQLAlchemy error deleting {model.__name__} ID {entity_id}: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error deleting {model.__name__} ID {entity_id}: {e}")
    return False

# --- Specific functions for job_applications (Many-to-Many relationship) ---

def add_lead_to_job_posting(db: Session, lead_id: int, job_posting_id: int, application_status: Optional[str] = "Applied") -> bool:
    """Associates a lead with a job posting."""
    try:
        # Check if lead and job posting exist
        lead = get_entity(db, Lead, lead_id)
        job = get_entity(db, JobPosting, job_posting_id)

        if not lead:
            logger.error(f"Lead with ID {lead_id} not found. Cannot associate with job posting.")
            return False
        if not job:
            logger.error(f"JobPosting with ID {job_posting_id} not found. Cannot associate lead.")
            return False
            
        # Check if association already exists to prevent IntegrityError if primary keys are only (lead_id, job_posting_id)
        # This check might be redundant if your SQLAlchemy relationship handles this or if you want to allow re-application with different status.
        # For simplicity, we'll assume a simple add. If you want to update status of an existing application, use a dedicated function.
        
        # stmt = job_applications.insert().values(lead_id=lead_id, job_posting_id=job_posting_id, status=application_status)
        # db.execute(stmt)
        # db.commit()
        
        # Alternative using ORM relationships if preferred (might be more intuitive but less direct for many-to-many through table inserts)
        # Requires 'applicants' and 'applied_jobs' relationships to be correctly set up in models.py
        if job not in lead.applied_jobs: # Avoid duplicates if relationship is already there
            lead.applied_jobs.append(job)
            # You might want to update the status on the association object if you had direct access to it
            # This part is tricky with simple append, might need to create an actual JobApplication object if it was a model
            db.commit()
            logger.info(f"Successfully associated Lead ID {lead_id} with JobPosting ID {job_posting_id}.")
            # How to set the status on the association?
            # After commit, the association should exist. We can query for it and update.
            # This is getting complex for a simple 'add'.
            # For now, this approach just creates the link. Status on association is not set via this method.
            # TODO: Revisit how to set 'status' on the job_applications association table when using relationship.append()
            # A more explicit way for association tables with extra data is often to define an Association Object (e.g. JobApplication class)
        else:
            logger.info(f"Lead ID {lead_id} is already associated with JobPosting ID {job_posting_id}.")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"SQLAlchemy error associating lead {lead_id} with job {job_posting_id}: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error associating lead {lead_id} with job {job_posting_id}: {e}")
    return False

def remove_lead_from_job_posting(db: Session, lead_id: int, job_posting_id: int) -> bool:
    """Removes the association between a lead and a job posting."""
    try:
        lead = get_entity(db, Lead, lead_id)
        job = get_entity(db, JobPosting, job_posting_id)

        if not lead or not job:
            logger.error(f"Lead ID {lead_id} or JobPosting ID {job_posting_id} not found for disassociation.")
            return False

        if job in lead.applied_jobs:
            lead.applied_jobs.remove(job)
            db.commit()
            logger.info(f"Successfully disassociated Lead ID {lead_id} from JobPosting ID {job_posting_id}.")
            return True
        else:
            logger.info(f"Lead ID {lead_id} was not associated with JobPosting ID {job_posting_id}.")
            return False
            
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"SQLAlchemy error disassociating lead {lead_id} from job {job_posting_id}: {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error disassociating lead {lead_id} from job {job_posting_id}: {e}")
    return False

def get_lead_applications(db: Session, lead_id: int) -> List[JobPosting]:
    """Gets all job postings a lead has applied to."""
    lead = get_entity(db, Lead, lead_id)
    if lead:
        return lead.applied_jobs
    return []

def get_job_applicants(db: Session, job_posting_id: int) -> List[Lead]:
    """Gets all leads who have applied to a specific job posting."""
    job = get_entity(db, JobPosting, job_posting_id)
    if job:
        return job.applicants
    return []

# TODO: Add functions for filtering, pagination, bulk operations, and advanced search as per subtask 3.4 full scope.
# For now, these basic CRUD and association helpers should suffice as a starting point. 