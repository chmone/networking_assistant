from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

# Adjust path to import from sibling directories (database, web_app)
# import sys
# import os
# current_dir = os.path.dirname(os.path.abspath(__file__))
# src_path = os.path.abspath(os.path.join(current_dir, '..', '..')) # Should point to src/
# if src_path not in sys.path:
#     sys.path.insert(0, src_path)

# Use absolute imports
# from database import db_utils, models 
# from web_app import schemas
from src.database import db_utils, models
from src.web_app import schemas
from src.web_app.api_main import get_db # Import the dependency

router = APIRouter()

@router.post("/", response_model=schemas.CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(company: schemas.CompanyCreate, db: Session = Depends(get_db)):
    """Create a new company."""
    # Check if company with same name already exists
    existing_company = db_utils.get_entities(db, models.Company, filters={'name': company.name}, limit=1)
    if existing_company:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Company with name '{company.name}' already exists.")

    db_company = db_utils.create_entity(db, models.Company, company.dict())
    if db_company is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create company")
    return db_company

@router.get("/", response_model=List[schemas.CompanyRead])
def read_companies(skip: int = 0, limit: int = 100, name: Optional[str] = None, db: Session = Depends(get_db)):
    """Retrieve a list of companies, with optional name filtering and pagination."""
    filters = {}
    if name: # Basic name filtering (can be expanded)
        # For partial matching, db_utils.get_entities would need modification
        # Using exact match for now
        filters['name'] = name 
    
    companies = db_utils.get_entities(db, models.Company, skip=skip, limit=limit, filters=filters)
    return companies

@router.get("/{company_id}", response_model=schemas.CompanyRead)
def read_company(company_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific company by its ID."""
    db_company = db_utils.get_entity(db, models.Company, company_id)
    if db_company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return db_company

@router.put("/{company_id}", response_model=schemas.CompanyRead)
def update_company(company_id: int, company: schemas.CompanyUpdate, db: Session = Depends(get_db)):
    """Update an existing company."""
    # Check if updated name conflicts with another company
    if company.name is not None:
        existing_company = db_utils.get_entities(db, models.Company, filters={'name': company.name}, limit=1)
        if existing_company and existing_company[0].id != company_id:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Company name '{company.name}' already exists.")

    update_data = company.dict(exclude_unset=True)
    # Add logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Update payload received: {company.dict()}")
    logger.debug(f"Update data after exclude_unset: {update_data}")
    
    if not update_data:
         logger.warning(f"Update for company {company_id} failed: No update data provided after exclude_unset.")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    updated_company = db_utils.update_entity(db, models.Company, company_id, update_data)
    if updated_company is None:
        db_company_check = db_utils.get_entity(db, models.Company, company_id)
        if db_company_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update company")
    return updated_company

@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    """Delete a company by its ID."""
    # Consider implications: Deleting a company might affect related Leads/JobPostings depending on DB constraints/cascades.
    # The JobPosting model has cascade delete orphan, leads do not by default.
    deleted = db_utils.delete_entity(db, models.Company, company_id)
    if not deleted:
        db_company_check = db_utils.get_entity(db, models.Company, company_id)
        if db_company_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete company")
    return None 