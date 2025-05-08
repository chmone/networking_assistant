from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional, List
from datetime import datetime
import enum # Use standard enum for schema definition consistency

# Replicate Enums from models.py for schema validation
# Avoids direct dependency on SQLAlchemy models in schemas if preferred
class LeadStatusEnum(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CONVERTED = "converted"
    ARCHIVED = "archived" # Added to match model

# Replicate JobType Enum
class JobTypeEnum(str, enum.Enum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    INTERNSHIP = "Internship"

# --- Lead Schemas ---

# Base properties shared by Create and Read schemas
class LeadBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: LeadStatusEnum = LeadStatusEnum.NEW
    source: Optional[str] = None
    notes: Optional[str] = None
    company_id: Optional[int] = None # Link to company
    # Add other relevant fields exposed via API
    # linkedin_profile_url: Optional[HttpUrl] = None 

# Properties required for creating a new Lead
class LeadCreate(LeadBase):
    pass # Inherits all from LeadBase, assumes all needed are there

# Properties required for updating an existing Lead (all optional)
class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[LeadStatusEnum] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    company_id: Optional[int] = None

# Properties returned when reading a Lead (includes ID and timestamps)
class LeadRead(LeadBase):
    id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic V2 config
    model_config = {
        "from_attributes": True,
        "use_enum_values": True
    }


# --- Company Schemas (Placeholder for Task 10.3) ---
class CompanyBase(BaseModel):
    name: str
    website: Optional[HttpUrl] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[HttpUrl] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

class CompanyRead(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    # leads: List[LeadRead] = [] # Example of including related leads
    # job_postings: List['JobPostingRead'] = [] # Forward reference needed

    # Pydantic V2 config
    model_config = {
        "from_attributes": True,
        "use_enum_values": True
    }


# --- JobPosting Schemas (Placeholder for Task 10.3) ---
class JobPostingBase(BaseModel):
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_range: Optional[str] = None
    location: Optional[str] = None
    # job_type: Optional[JobTypeEnum] = None # Define JobTypeEnum if needed
    status: str = "Open"
    company_id: Optional[int] = None
    job_url: Optional[HttpUrl] = None

class JobPostingCreate(JobPostingBase):
    pass

class JobPostingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_range: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[JobTypeEnum] = None
    status: Optional[str] = None
    company_id: Optional[int] = None
    job_url: Optional[HttpUrl] = None

class JobPostingRead(JobPostingBase):
    id: int
    created_at: datetime
    updated_at: datetime
    # company: Optional[CompanyRead] = None # Example of related company
    # applicants: List[LeadRead] = [] # Example of related leads

    # Pydantic V2 config
    model_config = {
        "from_attributes": True,
        "use_enum_values": True
    }

# Update forward references if needed (e.g., if CompanyRead includes JobPostingRead)
# CompanyRead.update_forward_refs()
# JobPostingRead.update_forward_refs() 