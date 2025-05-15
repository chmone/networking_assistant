import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import patch # Import patch

# Assuming the main FastAPI app is defined in src.web_app.api_main
from src.web_app.api_main import app
# Import the actual scraper to mock its path if needed for specific tests
# from src.data_acquisition.linkedin_scraper import LinkedInScraper 

# It's good practice to have a client fixture, even if simple for now
@pytest.fixture
def test_client_generation():
    # For these tests, we might want to ensure a fresh app instance or handle scraper instantiation carefully.
    # If LinkedInScraper is instantiated at module level in the router, TestClient(app) should use that.
    client = TestClient(app)
    yield client
    # No dependency overrides to clear for this specific test yet

# We'll patch the scrape_user_profile_details method for most tests
@patch('src.web_app.routers.generation_router.linkedin_scraper.scrape_user_profile_details')
def test_generate_leads_from_profile_success(mock_scrape_method, test_client_generation):
    """Test successful lead generation request."""
    mock_profile_data = {
        "profile_url": "https://www.linkedin.com/in/testuser/",
        "full_name": "Mocked User",
        "headline": "Mocked Headline",
        "education": [],
        "experience": [],
        "skills": ["mocking"],
        "status": "scraped_mock"
    }
    mock_scrape_method.return_value = mock_profile_data
    
    payload = {
        "linkedin_url": "https://www.linkedin.com/in/testuser/",
        "networking_goals": {
            "target_companies": ["Company A", "Company B"],
            "target_roles": ["Role X", "Role Y"]
        }
    }
    response = test_client_generation.post("/api/v1/generation/generate-leads-from-profile/", json=payload)
    
    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_scrape_method.assert_called_once_with("https://www.linkedin.com/in/testuser/")
    
    response_data = response.json()
    assert response_data["message"] == "Lead generation process initiated. Profile data (placeholder) retrieved."
    assert response_data["linkedin_url"] == payload["linkedin_url"]
    assert response_data["networking_goals"]["target_companies"] == payload["networking_goals"]["target_companies"]
    assert response_data["networking_goals"]["target_roles"] == payload["networking_goals"]["target_roles"]
    assert response_data["scraped_profile_data"] == mock_profile_data

# No need to mock for validation error tests, as scraping shouldn't be called if Pydantic validation fails.
def test_generate_leads_from_profile_invalid_url(test_client_generation):
    """Test request with an invalid LinkedIn URL format."""
    payload = {
        "linkedin_url": "htp:/invalid-url", # Invalid URL scheme
        "networking_goals": {
            "target_companies": ["Company A"],
        }
    }
    response = test_client_generation.post("/api/v1/generation/generate-leads-from-profile/", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    response_data = response.json()
    assert "detail" in response_data
    assert any("URL scheme should be 'http' or 'https'" in error.get("msg", "") for error in response_data.get("detail", []))

def test_generate_leads_from_profile_missing_linkedin_url(test_client_generation):
    """Test request missing the linkedin_url field."""
    payload = {
        "networking_goals": {
            "target_companies": ["Company A"],
        }
    }
    response = test_client_generation.post("/api/v1/generation/generate-leads-from-profile/", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    response_data = response.json()
    assert "detail" in response_data
    assert any(error.get("type") == "missing" and "linkedin_url" in error.get("loc", []) for error in response_data.get("detail", []))

@patch('src.web_app.routers.generation_router.linkedin_scraper.scrape_user_profile_details')
def test_generate_leads_from_profile_empty_goals(mock_scrape_method, test_client_generation):
    """Test successful request with empty networking_goals lists."""
    mock_profile_data = {"status": "scraped_mock_empty_goals"}
    mock_scrape_method.return_value = mock_profile_data
    
    payload = {
        "linkedin_url": "https://www.linkedin.com/in/testuser/",
        "networking_goals": {
            "target_companies": [],
            "target_roles": []
        }
    }
    response = test_client_generation.post("/api/v1/generation/generate-leads-from-profile/", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_scrape_method.assert_called_once_with("https://www.linkedin.com/in/testuser/")
    response_data = response.json()
    assert response_data["linkedin_url"] == payload["linkedin_url"]
    assert response_data["networking_goals"]["target_companies"] == []
    assert response_data["networking_goals"]["target_roles"] == []
    assert response_data["scraped_profile_data"] == mock_profile_data

@patch('src.web_app.routers.generation_router.linkedin_scraper.scrape_user_profile_details')
def test_generate_leads_from_profile_null_goals(mock_scrape_method, test_client_generation):
    """Test successful request with null networking_goals fields (optional)."""
    mock_profile_data = {"status": "scraped_mock_null_goals"}
    mock_scrape_method.return_value = mock_profile_data
    
    payload = {
        "linkedin_url": "https://www.linkedin.com/in/testuser2/",
        "networking_goals": {
            "target_companies": None,
            "target_roles": None
        }
    }
    response = test_client_generation.post("/api/v1/generation/generate-leads-from-profile/", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED
    mock_scrape_method.assert_called_once_with("https://www.linkedin.com/in/testuser2/")
    response_data = response.json()
    assert response_data["linkedin_url"] == payload["linkedin_url"]
    assert response_data["networking_goals"]["target_companies"] is None
    assert response_data["networking_goals"]["target_roles"] is None
    assert response_data["scraped_profile_data"] == mock_profile_data 