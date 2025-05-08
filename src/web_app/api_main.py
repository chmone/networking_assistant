import logging
import sys
import os
import time # For request timing
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import status
import uuid

# Adjust path to import from other top-level directories (config, database, etc.)
# This assumes api_main.py is in src/web_app/
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.abspath(os.path.join(current_dir, '..'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from config.config_manager import ConfigManager
    from database.db_manager import DatabaseManager
    from database import models # For potential response models if needed
    # Import db_utils if routes will directly use them
    # from database import db_utils 
except ImportError as e:
    logging.critical(f"Failed to import core modules needed for API: {e}. API cannot start correctly.")
    # In a real scenario, you might exit or prevent the app from running fully
    # For now, define dummies to allow file loading
    class ConfigManager: 
        def __init__(self, *args, **kwargs): pass
        def get_config(self, key, default=None): return default
    class DatabaseManager: 
        def __init__(self, *args, **kwargs): pass
        def get_session(self): raise RuntimeError("Dummy DBManager")
        def managed_session(self): raise RuntimeError("Dummy DBManager")

logger = logging.getLogger(__name__)

# --- Global Variables / App Initialization ---
# TODO: Load config path more robustly if needed
config_file_path = os.path.abspath(os.path.join(src_path, '..', '.env')) 

# Initialize global components (consider dependency injection frameworks for larger apps)
# These might raise exceptions on init failure, handled by FastAPI startup events later if needed
config_manager = ConfigManager(env_file_path=config_file_path)
db_manager = DatabaseManager(config=config_manager)

app = FastAPI(
    title="Networking Assistant API",
    description="API for managing leads, companies, and job postings.",
    version="0.1.0"
)

# --- Middleware Setup ---
# Configure CORS (Cross-Origin Resource Sharing)
# Adjust origins based on where your frontend will be hosted
origins = [
    "http://localhost",
    "http://localhost:8501", # Default for Streamlit
    "http://localhost:3000", # Common for React dev servers
    # Add production frontend URL(s) here eventually
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Dependency Injection / Session Management ---
def get_db() -> Session:
    """FastAPI dependency to get a database session for a request."""
    # Use the managed_session context manager from db_manager
    with db_manager.managed_session() as session:
        yield session
        # Session commit/rollback/close is handled by managed_session

def get_config() -> ConfigManager:
    """FastAPI dependency to get the ConfigManager instance."""
    # Return the globally initialized instance
    # In more complex apps, this might involve a request-scoped config or context
    return config_manager

# --- Exception Handlers ---
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error occurred for request {request.method} {request.url}: {exc}")
    # You might want to provide more or less detail depending on environment (dev vs prod)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An internal database error occurred: {str(exc)}"}, # Avoid leaking too much in prod
    )

# Add handlers for other custom exceptions if needed
# @app.exception_handler(CustomValidationError)
# async def custom_validation_exception_handler(request: Request, exc: CustomValidationError):
#     return JSONResponse(status_code=400, content={"detail": str(exc)})

# --- Request Logging Middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    idem = str(uuid.uuid4()) # Generate a unique ID for each request
    logger.info(f"rid={idem} start request path={request.url.path}")
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = '{0:.2f}'.format(process_time)
    logger.info(f"rid={idem} completed_in={formatted_process_time}ms status_code={response.status_code}")
    
    return response

# --- API Routes (Routers will be added in later subtasks) ---

@app.get("/")
def read_root():
    """Root endpoint for basic API health check.""" 
    return {"message": "Networking Assistant API is running."}

# Example: Placeholder for future lead endpoints
from .routers import leads # Assuming routers are in web_app/routers/
app.include_router(leads.router, prefix="/api/v1/leads", tags=["Leads"])

# Example: Placeholder for future company endpoints
from .routers import companies
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])

# Example: Placeholder for future job posting endpoints
from .routers import jobs
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Job Postings"])


# --- Application Startup / Shutdown Events (Optional) ---
@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application startup...")
    # Configure logging (could read level/format from config_manager)
    log_level_str = config_manager.get_config("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger.info(f"Logging configured with level: {log_level_str}")
    
    try:
        # Ensure DB connection is okay on startup (optional check)
        with db_manager.managed_session() as db:
            db.execute(models.text("SELECT 1")) # Use models.text directly
        logger.info("Database connection verified.")
    except Exception as e:
        logger.critical(f"Database connection failed on startup: {e}")
        # Potentially prevent app from fully starting or raise critical error

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI application shutdown...")
    # Perform any cleanup here if needed
    # (e.g., closing external connections not handled by contexts)

# --- Main execution (for running with uvicorn) ---
# Typically you run FastAPI apps with: uvicorn src.web_app.api_main:app --reload
# The following block is mostly for direct execution testing, not production.
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting FastAPI app directly using Uvicorn...")
    # Note: Running directly might have issues with relative imports if not structured perfectly
    # Recommended to run using the uvicorn command from the project root.
    uvicorn.run("api_main:app", host="127.0.0.1", port=8000, reload=True) 