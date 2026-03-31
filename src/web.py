import asyncio
import base64
import hashlib
import json
import os
import secrets

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow

from .config import settings
from .crypto import encrypt
from .db import SessionLocal, User

web_app = FastAPI()

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# PKCE verifier stores (telegram_user_id -> verifier string)
_google_verifiers: dict[int, str] = {}
_or_verifiers: dict[int, str] = {}

GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# ── Google OAuth ──────────────────────────────────────────────────────────────

def _make_google_flow(state: str | None = None) -> Flow:
    return Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=f"{settings.base_url}/auth/callback",
    )


@web_app.get("/auth/google/{telegram_user_id}")
async def google_start(telegram_user_id: int):
    flow = _make_google_flow(state=str(telegram_user_id))
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    if flow.code_verifier:
        _google_verifiers[telegram_user_id] = flow.code_verifier
    return RedirectResponse(url=auth_url)


@web_app.get("/auth/callback")
async def google_callback(code: str, state: str):
    telegram_user_id = int(state)

    def fetch_tokens():
        flow = _make_google_flow(state=state)
        verifier = _google_verifiers.pop(telegram_user_id, None)
        if verifier:
            flow.code_verifier = verifier
        flow.fetch_token(code=code)
        return flow.credentials

    creds = await asyncio.get_event_loop().run_in_executor(None, fetch_tokens)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }

    already_has_ai = False
    async with SessionLocal() as session:
        user = await session.get(User, telegram_user_id)
        if user:
            user.google_tokens = encrypt(json.dumps(token_data))
            already_has_ai = bool(user.ai_api_key) or user.ai_provider == "hosted"
            user.setup_step = "ready" if already_has_ai else "awaiting_ai_setup"
            await session.commit()

    async with httpx.AsyncClient() as client:
        if already_has_ai:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                json={
                    "chat_id": telegram_user_id,
                    "text": "✅ Google Drive reconnected! You're all set — send me a receipt.",
                },
            )
        else:
            or_url = f"{settings.base_url}/auth/openrouter/{telegram_user_id}"
            buttons = [
                [{"text": "Connect OpenRouter (recommended)", "url": or_url}],
                [{"text": "Pay per use with Telegram Stars", "callback_data": "pay_per_use"}],
                [{"text": "Use my own API key instead", "callback_data": "use_own_key"}],
            ]
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                json={
                    "chat_id": telegram_user_id,
                    "text": (
                        "✅ Google Drive connected!\n\n"
                        "Now let's connect your AI. Choose one:"
                    ),
                    "reply_markup": json.dumps({"inline_keyboard": buttons}),
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


# ── OpenRouter OAuth (PKCE) ───────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    """Generate (code_verifier, code_challenge) for PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@web_app.get("/auth/openrouter/{telegram_user_id}")
async def openrouter_start(telegram_user_id: int):
    verifier, challenge = _pkce_pair()
    _or_verifiers[telegram_user_id] = verifier
    callback_url = f"{settings.base_url}/auth/openrouter/callback?state={telegram_user_id}"
    auth_url = (
        f"https://openrouter.ai/auth"
        f"?callback_url={callback_url}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url=auth_url)


@web_app.get("/auth/openrouter/callback")
async def openrouter_callback(code: str, state: str):
    telegram_user_id = int(state)
    verifier = _or_verifiers.pop(telegram_user_id, None)

    # Exchange code for API key
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/auth/keys",
            json={"code": code, "code_verifier": verifier},
        )
        resp.raise_for_status()
        api_key = resp.json()["key"]

    async with SessionLocal() as session:
        user = await session.get(User, telegram_user_id)
        if user:
            user.ai_provider = "openrouter"
            user.ai_api_key = encrypt(api_key)
            user.setup_step = "ready"
            await session.commit()

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            json={
                "chat_id": telegram_user_id,
                "text": (
                    "✅ All set! OpenRouter connected.\n\n"
                    "You can now:\n"
                    "• Send me receipts, invoices, or screenshots\n"
                    "• Ask questions like \"how much did I spend on food this month?\""
                ),
            },
        )

    return HTMLResponse("""
        <html>
        <body style="font-family: sans-serif; text-align: center; padding: 60px;">
            <h2>OpenRouter connected!</h2>
            <p>Go back to Telegram — you're all set.</p>
        </body>
        </html>
    """)
