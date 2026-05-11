from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow

from config import (
    API_TOKEN,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    REDIRECT_URI,
    SCOPES,
)


# -----------------------------------------------------------------------------
# Autenticação simples
# -----------------------------------------------------------------------------

def check_auth(token: str):
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# -----------------------------------------------------------------------------
# OAuth Google Calendar
# -----------------------------------------------------------------------------

def build_google_flow():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID ou GOOGLE_CLIENT_SECRET ausente no Render.",
        )

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        autogenerate_code_verifier=False,
    )

    flow.redirect_uri = REDIRECT_URI
    return flow
