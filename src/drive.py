import io
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .config import settings
from .crypto import decrypt, encrypt

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_NAME = "Peduni Expenses"


def _get_service(encrypted_tokens: str):
    token_data = json.loads(decrypt(encrypted_tokens))
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def _refresh_and_encrypt(encrypted_tokens: str) -> str:
    """Refresh tokens if needed and return updated encrypted tokens."""
    token_data = json.loads(decrypt(encrypted_tokens))
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data["token"] = creds.token
        return encrypt(json.dumps(token_data))
    return encrypted_tokens


def ensure_folder(encrypted_tokens: str) -> str:
    """Get or create the Peduni Expenses folder, return its ID."""
    service = _get_service(encrypted_tokens)
    results = service.files().list(
        q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)",
    ).execute()

    files = results.get("files", [])
    if files:
        return files[0]["id"]

    folder = service.files().create(
        body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]


def upload_file(encrypted_tokens: str, folder_id: str, filename: str, content: bytes, mime_type: str) -> str:
    """Upload a file to the user's Drive folder, return file ID."""
    service = _get_service(encrypted_tokens)
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
    file = service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    return file["id"]
