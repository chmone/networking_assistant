from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

# Use absolute imports
# from database import db_utils, models 
# from web_app import schemas
from src.database import db_utils, models
from src.web_app import schemas
from src.web_app.api_main import get_db # Import the dependency

router = APIRouter()

@router.post("/", response_model=schemas.JobPostingRead, status_code=status.HTTP_201_CREATED)
def create_job_posting(job: schemas.JobPostingCreate, db: Session = Depends(get_db)):
    """Create a new job posting."""
    # Check if company_id exists if provided
    if job.company_id:
        db_company = db_utils.get_entity(db, models.Company, job.company_id)
        if not db_company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company with id {job.company_id} not found")
            
    # Check if job with same URL already exists for this company (if company known)
    if job.job_url and job.company_id:
        existing_job = db_utils.get_entities(db, models.JobPosting, filters={'job_url': job.job_url, 'company_id': job.company_id}, limit=1)
        if existing_job:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Job posting with URL {job.job_url} already exists for company ID {job.company_id}.")
    elif job.job_url: # Check URL globally if company not specified (less reliable)
         existing_job = db_utils.get_entities(db, models.JobPosting, filters={'job_url': job.job_url}, limit=1)
         if existing_job:
             # Allow if no company specified? Or reject? Rejecting for now.
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Job posting with URL {job.job_url} already exists (company not specified).")

    db_job = db_utils.create_entity(db, models.JobPosting, job.dict())
    if db_job is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create job posting")
    return db_job

@router.get("/", response_model=List[schemas.JobPostingRead])
def read_job_postings(skip: int = 0, limit: int = 100, company_id: Optional[int] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    """Retrieve a list of job postings, with optional filtering and pagination."""
    filters = {}
    if company_id:
        filters['company_id'] = company_id
    if status:
        filters['status'] = status
    
    jobs = db_utils.get_entities(db, models.JobPosting, skip=skip, limit=limit, filters=filters)
    return jobs

@router.get("/{job_id}", response_model=schemas.JobPostingRead)
def read_job_posting(job_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific job posting by its ID."""
    db_job = db_utils.get_entity(db, models.JobPosting, job_id)
    if db_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found")
    return db_job

@router.put("/{job_id}", response_model=schemas.JobPostingRead)
def update_job_posting(job_id: int, job: schemas.JobPostingUpdate, db: Session = Depends(get_db)):
    """Update an existing job posting."""
    # Check if company_id exists if provided
    if job.company_id is not None:
        db_company = db_utils.get_entity(db, models.Company, job.company_id)
        if not db_company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company with id {job.company_id} not found")

    # Check if updated URL conflicts with another job for the *same company* if company known
    if job.job_url is not None:
        db_job_check = db_utils.get_entity(db, models.JobPosting, job_id)
        current_company_id = db_job_check.company_id if db_job_check else None
        target_company_id = job.company_id if job.company_id is not None else current_company_id
        
        if target_company_id:
             existing_job = db_utils.get_entities(db, models.JobPosting, filters={'job_url': job.job_url, 'company_id': target_company_id}, limit=1)
             if existing_job and existing_job[0].id != job_id:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Job posting URL {job.job_url} already exists for company ID {target_company_id}.")
        # If no company context, checking URL globally might be too strict

    update_data = job.dict(exclude_unset=True)
    if not update_data:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    updated_job = db_utils.update_entity(db, models.JobPosting, job_id, update_data)
    if updated_job is None:
        db_job_check = db_utils.get_entity(db, models.JobPosting, job_id)
        if db_job_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update job posting")
    return updated_job

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_posting(job_id: int, db: Session = Depends(get_db)):
    """Delete a job posting by its ID."""
    deleted = db_utils.delete_entity(db, models.JobPosting, job_id)
    if not deleted:
        db_job_check = db_utils.get_entity(db, models.JobPosting, job_id)
        if db_job_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete job posting")
    return None 