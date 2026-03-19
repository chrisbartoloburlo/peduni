import json

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow

from .config import settings
from .crypto import encrypt
from .db import SessionLocal, User

web_app = FastAPI()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def _make_flow(state: str | None = None) -> Flow:
    return Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=f"{settings.base_url}/auth/callback",
    )


@web_app.get("/auth/google/{telegram_user_id}")
async def start_auth(telegram_user_id: int):
    flow = _make_flow(state=str(telegram_user_id))
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # Redirect directly to Google
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=auth_url)


@web_app.get("/auth/callback")
def oauth_callback(code: str, state: str):
    """Sync endpoint — google-auth-oauthlib is synchronous."""
    telegram_user_id = int(state)

    flow = _make_flow(state=state)
    flow.fetch_token(code=code)

    creds = flow.credentials
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }

    import asyncio

    async def _update_db():
        async with SessionLocal() as session:
            user = await session.get(User, telegram_user_id)
            if user:
                user.google_tokens = encrypt(json.dumps(token_data))
                user.setup_step = "awaiting_provider"
                await session.commit()

    asyncio.run(_update_db())

    # Notify the user in Telegram
    httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
        json={
            "chat_id": telegram_user_id,
            "text": (
                "✅ Google Drive connected!\n\n"
                "Now choose your AI provider. Reply with one of:\n"
                "• anthropic\n"
                "• openai\n"
                "• gemini"
            ),
        },
    )

    return HTMLResponse("""
        <html>
        <body style="font-family: sans-serif; text-align: center; padding: 60px;">
            <h2>Google Drive connected!</h2>
            <p>Go back to Telegram to finish setup.</p>
        </body>
        </html>
    """)
