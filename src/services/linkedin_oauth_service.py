import httpx
import secrets
from urllib.parse import urlencode

from fastapi import HTTPException, status
from starlette.datastructures import URL

from src.core.config import settings

async def generate_authorization_url(session: dict) -> str:
    """
    Generates the LinkedIn authorization URL with a CSRF state token.
    The state token is stored in the user's session.
    """
    state = secrets.token_urlsafe(32)
    session["linkedin_oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": settings.LINKEDIN_SCOPES,
    }
    authorization_url = URL(settings.LINKEDIN_AUTHORIZATION_URL).replace_query_params(**params)
    return str(authorization_url)

async def exchange_code_for_token(code: str, received_state: str, session: dict) -> dict:
    """
    Exchanges the authorization code for an access token from LinkedIn.
    Validates the CSRF state token.
    """
    expected_state = session.pop("linkedin_oauth_state", None)
    if not expected_state or received_state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid CSRF state token."
        )

    token_data_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "client_secret": settings.LINKEDIN_CLIENT_SECRET,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.LINKEDIN_ACCESS_TOKEN_URL,
                data=token_data_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()  # Raises an HTTPStatusError for 4xx/5xx responses
            token_info = response.json()
            return token_info
        except httpx.HTTPStatusError as e:
            # Attempt to parse error from LinkedIn if available
            error_detail = f"Failed to obtain access token from LinkedIn: {e.response.status_code}"
            try:
                linkedin_error = e.response.json()
                error_detail += f" - {linkedin_error.get('error_description', linkedin_error.get('error', 'Unknown LinkedIn error'))}"
            except Exception:
                pass # Keep generic error if LinkedIn error response is not JSON or parsable
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, # 502 because we got an error from upstream (LinkedIn)
                detail=error_detail
            )
        except httpx.RequestError as e:
            # For network errors, DNS failures, etc.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Network error while contacting LinkedIn: {str(e)}"
            ) 