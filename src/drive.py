import io
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .config import settings
from .crypto import decrypt

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
ROOT_FOLDER_NAME = "Peduni"


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


def _get_or_create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Get or create a Drive folder by name under an optional parent, return its ID."""
    parent_clause = f" and '{parent_id}' in parents" if parent_id else ""
    results = service.files().list(
        q=f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false{parent_clause}",
        fields="files(id)",
    ).execute()

    files = results.get("files", [])
    if files:
        return files[0]["id"]

    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]

    folder = service.files().create(body=body, fields="id").execute()
    return folder["id"]


def ensure_root_folder(encrypted_tokens: str) -> str:
    """Get or create the root Peduni folder, return its ID."""
    service = _get_service(encrypted_tokens)
    return _get_or_create_folder(service, ROOT_FOLDER_NAME)


def upload_file(encrypted_tokens: str, root_folder_id: str, month_str: str, filename: str, content: bytes, mime_type: str) -> str:
    """
    Upload a file into Peduni/<month_str>/, creating the month folder if needed.
    month_str should be formatted as YYYY-MM (e.g. '2026-03').
    Returns the Drive file ID.
    """
    service = _get_service(encrypted_tokens)
    month_folder_id = _get_or_create_folder(service, month_str, parent_id=root_folder_id)

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
    file = service.files().create(
        body={"name": filename, "parents": [month_folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    return file["id"]
