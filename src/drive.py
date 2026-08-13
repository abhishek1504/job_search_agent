"""Uploads generated resume PDFs to Google Drive, using the same service
account as the Sheets integration, and returns a shareable link.

One-time setup:
1. Create (or reuse) a Drive folder to hold generated resumes.
2. Share that folder with the service account's email — found as "client_email"
   inside your service_account.json — with Editor access.
3. Put that folder's ID in config.yaml under resume_generation.drive_folder_id.

Why sharing is required: the service account has its own separate, invisible
Drive space. Files it creates there aren't visible in your normal Drive unless
they live inside a folder you've explicitly shared with it — sharing the
folder is what makes uploaded resumes show up in your own Google Drive.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_drive_service(settings: Settings):
    creds = Credentials.from_service_account_file(settings.google_service_account_file, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_resume(
    settings: Settings,
    pdf_path: Path,
    folder_id: str,
    share_with_email: str | None = None,
) -> str:
    """Uploads pdf_path into the given Drive folder. If share_with_email is
    set, also explicitly grants that address writer access (belt-and-braces —
    it should already be visible via the shared folder, but this guarantees
    it). Returns a webViewLink you can open in a browser."""

    service = _get_drive_service(settings)

    file_metadata = {"name": pdf_path.name, "parents": [folder_id]}
    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=False)

    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    file_id = uploaded["id"]

    if share_with_email:
        try:
            service.permissions().create(
                fileId=file_id,
                body={"type": "user", "role": "writer", "emailAddress": share_with_email},
                fields="id",
                sendNotificationEmail=False,
            ).execute()
        except Exception:
            # Non-fatal: the file is still uploaded and reachable via the shared
            # folder even if this explicit per-file grant fails for some reason.
            logger.exception("Could not grant %s explicit access to the uploaded file.", share_with_email)

    link = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
    logger.info("Uploaded resume to Drive: %s", link)
    return link
