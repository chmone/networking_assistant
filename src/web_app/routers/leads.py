from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

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

@router.post("/", response_model=schemas.LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(lead: schemas.LeadCreate, db: Session = Depends(get_db)):
    """Create a new lead."""
    # Optional: Check if company_id exists if provided
    if lead.company_id:
        db_company = db_utils.get_entity(db, models.Company, lead.company_id)
        if not db_company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company with id {lead.company_id} not found")
            
    # Optional: Check if lead with same email already exists
    if lead.email:
        existing_lead = db_utils.get_entities(db, models.Lead, filters={'email': lead.email}, limit=1)
        if existing_lead:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Lead with email {lead.email} already exists.")

    db_lead = db_utils.create_entity(db, models.Lead, lead.dict())
    if db_lead is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create lead")
    return db_lead

@router.get("/", response_model=List[schemas.LeadRead])
def read_leads(skip: int = 0, limit: int = 100, 
                 status: Optional[schemas.LeadStatusEnum] = None, 
                 name_contains: Optional[str] = None,
                 company_id: Optional[int] = None,
                 sort_by: Optional[str] = None,
                 sort_order: str = 'asc',
                 db: Session = Depends(get_db)):
    """Retrieve a list of leads, with optional filtering, sorting, and pagination."""
    filters = {}
    if status:
        filters['status'] = status # db_utils expects the enum member
    if name_contains: 
        filters['name__ilike'] = f"%{name_contains}%"
    if company_id:
        filters['company_id'] = company_id
        
    order_by_column = None
    if sort_by:
        if hasattr(models.Lead, sort_by):
            order_by_column = getattr(models.Lead, sort_by)
        else:
            pass
            
    sort_direction = sort_order.lower()
    if sort_direction not in ['asc', 'desc']:
        sort_direction = 'asc'
        
    leads = db_utils.get_entities(
        db, models.Lead, 
        skip=skip, limit=limit, filters=filters,
        order_by_column=order_by_column,
        sort_direction=sort_direction
    )
    return leads

@router.get("/{lead_id}", response_model=schemas.LeadRead)
def read_lead(lead_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific lead by its ID."""
    db_lead = db_utils.get_entity(db, models.Lead, lead_id)
    if db_lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return db_lead

@router.put("/{lead_id}", response_model=schemas.LeadRead)
def update_lead(lead_id: int, lead: schemas.LeadUpdate, db: Session = Depends(get_db)):
    """Update an existing lead."""
    # Optional: Check if company_id exists if provided in update
    if lead.company_id is not None:
        db_company = db_utils.get_entity(db, models.Company, lead.company_id)
        if not db_company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company with id {lead.company_id} not found")

    # Optional: Check if updated email conflicts with another lead
    if lead.email is not None:
        existing_lead = db_utils.get_entities(db, models.Lead, filters={'email': lead.email}, limit=1)
        if existing_lead and existing_lead[0].id != lead_id:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Email {lead.email} already exists for another lead.")

    # Exclude unset fields from the update data
    update_data = lead.dict(exclude_unset=True)
    if not update_data:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    updated_lead = db_utils.update_entity(db, models.Lead, lead_id, update_data)
    if updated_lead is None:
        # Need to differentiate between not found and update error
        db_lead_check = db_utils.get_entity(db, models.Lead, lead_id)
        if db_lead_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update lead")
    return updated_lead

@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    """Delete a lead by its ID."""
    deleted = db_utils.delete_entity(db, models.Lead, lead_id)
    if not deleted:
        # Need to differentiate between not found and delete error
        db_lead_check = db_utils.get_entity(db, models.Lead, lead_id)
        if db_lead_check is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        else:
             # Deletion failed for some other reason (permissions, DB error?) - less likely with simple delete
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete lead")
    # No content returned on successful deletion
    return None 