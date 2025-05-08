from sqlalchemy import create_engine, Column, Integer, String, Text, Enum, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.sql import func
import datetime
import enum
import sqlalchemy

# Base class for declarative models
# SQLALCHEMY_WARN_20 Imports from "sqlalchemy.orm.declarative" will be deprecated in SQLAlchemy 2.1. Use "sqlalchemy.orm" instead. (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
Base = declarative_base()

# Association table for Lead <-> JobPosting (Many-to-Many)
job_applications = sqlalchemy.Table('job_applications',
    Base.metadata,
    sqlalchemy.Column('lead_id', sqlalchemy.Integer, sqlalchemy.ForeignKey('leads.id', ondelete='CASCADE'), primary_key=True),
    sqlalchemy.Column('job_posting_id', sqlalchemy.Integer, sqlalchemy.ForeignKey('job_postings.id', ondelete='CASCADE'), primary_key=True),
    sqlalchemy.Column('application_date', sqlalchemy.DateTime, default=datetime.datetime.utcnow, nullable=False),
    sqlalchemy.Column('status', sqlalchemy.String, nullable=True) # e.g., Applied, Interviewing, Offer, Rejected
)

# Enum for Lead Status
class LeadStatus(enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CONVERTED = "converted"
    ARCHIVED = "archived"

class JobType(enum.Enum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    INTERNSHIP = "Internship"

class Lead(Base):
    __tablename__ = 'leads'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, nullable=True)
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW.value, nullable=False)
    source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # Relationships to be defined in Subtask 3.2
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    company = relationship("Company", back_populates="leads")
    
    applied_jobs = relationship(
        "JobPosting",
        secondary=job_applications,
        back_populates="applicants"
    )

    def __repr__(self):
        return f"<Lead(id={self.id}, name='{self.name}', status='{self.status.value if self.status else None}')>"

class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    website = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    size = Column(String, nullable=True)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # Relationships to be defined in Subtask 3.2
    leads = relationship("Lead", back_populates="company")
    job_postings = relationship("JobPosting", back_populates="company", cascade="all, delete-orphan") # If a company is deleted, its job postings are deleted

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}')>"

class JobPosting(Base):
    __tablename__ = 'job_postings'
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    salary_range = Column(String, nullable=True)
    location = Column(String, nullable=True)
    job_url = Column(String, nullable=True)
    job_type = Column(Enum(JobType), nullable=True)
    status = Column(String, default="Open", nullable=False) # e.g., Open, Closed, Filled
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    
    # Relationships to be defined in Subtask 3.2
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    company = relationship("Company", back_populates="job_postings")

    applicants = relationship(
        "Lead",
        secondary=job_applications,
        back_populates="applied_jobs"
    )

    def __repr__(self):
        return f"<JobPosting(id={self.id}, title='{self.title}', status='{self.status}')>"

# Association table for a many-to-many relationship between Leads and JobPostings
# To be implemented/confirmed in Subtask 3.2 if this is the desired relationship.
# class JobApplication(Base):
#     __tablename__ = 'job_applications'
#     lead_id = Column(Integer, ForeignKey('leads.id', ondelete='CASCADE'), primary_key=True)
#     job_posting_id = Column(Integer, ForeignKey('job_postings.id', ondelete='CASCADE'), primary_key=True)
#     application_date = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
#     status = Column(String, nullable=True) # e.g., Applied, Interviewing, Offer, Rejected
# 
#     # Optional: Add relationships back to Lead and JobPosting if needed for direct access from an application instance
#     # lead = relationship("Lead", back_populates="job_applications")
#     # job_posting = relationship("JobPosting", back_populates="job_applications")
#
#     def __repr__(self):
#         return f"<JobApplication(lead_id={self.lead_id}, job_id={self.job_posting_id}, status='{self.status}')>" 