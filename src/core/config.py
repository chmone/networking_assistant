from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Personal Networking Hub"
    API_V1_STR: str = "/api/v1"

    # LinkedIn OAuth Configuration
    LINKEDIN_CLIENT_ID: Optional[str] = None
    LINKEDIN_CLIENT_SECRET: Optional[str] = None
    LINKEDIN_REDIRECT_URI: Optional[str] = "http://localhost:8000/api/auth/callback" # Default, can be overridden by .env
    LINKEDIN_AUTHORIZATION_URL: str = "https://www.linkedin.com/oauth/v2/authorization"
    LINKEDIN_ACCESS_TOKEN_URL: str = "https://www.linkedin.com/oauth/v2/accessToken"
    LINKEDIN_SCOPES: str = "openid profile email" # Space-separated

    # Session Management
    SESSION_SECRET_KEY: Optional[str] = None # MUST be set in .env for session middleware

    # Database (Example, adjust as needed if you have one)
    # SQLALCHEMY_DATABASE_URL: Optional[str] = "sqlite:///./leads.db"

    # SerpApi (from previous context, if still needed)
    # SERPAPI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore" # Ignore extra fields from .env

settings = Settings() 