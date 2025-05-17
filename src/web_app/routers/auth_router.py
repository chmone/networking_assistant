from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from src.services import linkedin_oauth_service
from src.core.config import settings

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

@router.get("/linkedin/login", response_class=RedirectResponse)
async def linkedin_login(request: Request):
    """
    Redirects the user to LinkedIn's authorization page.
    """
    if not settings.LINKEDIN_CLIENT_ID or not settings.LINKEDIN_CLIENT_SECRET:
        raise HTTPException(
            status_code=500, 
            detail="LinkedIn OAuth credentials are not configured."
        )
    authorization_url = await linkedin_oauth_service.generate_authorization_url(request.session)
    return RedirectResponse(url=authorization_url, status_code=307) # Use 307 for explicit GET

@router.get("/linkedin/callback")
async def linkedin_callback(request: Request, code: str = Query(None), state: str = Query(None), error: str = Query(None), error_description: str = Query(None)):
    """
    Handles the callback from LinkedIn after user authorization.
    Exchanges the authorization code for an access token.
    """
    if error:
        # LinkedIn returned an error (e.g., user denied access)
        return JSONResponse(
            status_code=400, 
            content={"detail": f"LinkedIn authentication failed: {error} - {error_description}"}
        )
    
    if not code or not state:
        return JSONResponse(
            status_code=400, 
            content={"detail": "Missing authorization code or state from LinkedIn callback."}
        )

    try:
        token_data = await linkedin_oauth_service.exchange_code_for_token(
            code=code, 
            received_state=state, 
            session=request.session
        )
        
        # Store the access token in the session (secure persistent storage is for Subtask 3.3)
        request.session["linkedin_access_token"] = token_data.get("access_token")
        request.session["linkedin_token_expires_at"] = token_data.get("expires_in") # Typically seconds from now
        # Potentially store refresh token if provided and if we plan to use it: token_data.get("refresh_token")

        # Redirect to a frontend success page (placeholder for now)
        # In a real app, this would be a page in your frontend that signifies successful login.
        return RedirectResponse(url="/docs", status_code=307) # Redirecting to /docs for now as a test
    
    except HTTPException as he:
        # Forward HTTPExceptions raised by the service (e.g., state mismatch, LinkedIn API error)
        return JSONResponse(status_code=he.status_code, content={"detail": he.detail})
    except Exception as e:
        # Log the exception e for server-side review
        print(f"Unexpected error in LinkedIn callback: {e}") # Basic logging
        return JSONResponse(
            status_code=500, 
            content={"detail": "An unexpected error occurred during LinkedIn authentication processing."}
        ) 