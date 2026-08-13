"""Google Sheets writer.

Mirrors the n8n "Update Linkedin jobs" node: appendOrUpdate rows keyed on Job ID.
Requires a Google service account JSON key with the target sheet shared to it
(see .env.example / README).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .config import ROOT_DIR, Settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Column order mirrors the n8n Google Sheets node's schema.
COLUMNS = [
    "Job ID",
    "Title",
    "Job Description",
    "Platform",
    "Link",
    "Date",
    "Rating",
    "Company Name",
    "Expired",
    "Remote",
    "Status",
    "Resume Link",
    "Prompt",
]


def _load_text(name: str) -> str:
    return (ROOT_DIR / "data" / name).read_text().strip()


def build_prompt_column(job: dict[str, Any], candidate: dict[str, str]) -> str:
    """Recreates the n8n workflow's 'Prompt' column: a ready-to-paste instruction
    for tailoring + generating a resume PDF for this specific job, using the
    candidate's LinkedIn-style profile."""

    linkedin_profile = _load_text("linkedin_profile.txt")
    instructions = _load_text("resume_instructions.txt")
    company = job.get("companyName", "")

    return (
        f"Here is the job description: {job.get('descriptionText', '')}\n\n"
        f'Here is my complete profile: "{linkedin_profile}"\n\n'
        f"{instructions} "
        f"For more information, here is my GitHub profile as well {candidate.get('github', '')}. "
        f"Keep the contact information (Email: {candidate.get('email', '')}, "
        f"Phone: {candidate.get('phone', '')}) intact, educational information, and "
        f"professional experience intact. "
        f'Once the PDF is generated, name the file Resume_{company}.pdf'
    )


def build_row(job: dict[str, Any], score_raw_text: str, candidate: dict[str, str]) -> dict[str, str]:
    return {
        "Job ID": str(job.get("id", "")),
        "Title": job.get("title", ""),
        "Job Description": job.get("descriptionText", ""),
        "Platform": "Linkedin",
        "Link": job.get("link", ""),
        "Date": job.get("postedAt", ""),
        "Rating": score_raw_text,
        "Company Name": job.get("companyName", ""),
        "Expired": "",
        "Remote": "",
        "Status": "",
        "Resume Link": "",
        "Prompt": build_prompt_column(job, candidate),
    }


class JobsSheet:
    def __init__(self, settings: Settings):
        sheet_cfg = settings.google_sheets
        creds = Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=SCOPES
        )
        gc = gspread.authorize(creds)
        self._ws = gc.open_by_key(sheet_cfg["spreadsheet_id"]).worksheet(
            sheet_cfg["worksheet_name"]
        )
        self._match_column = sheet_cfg["match_column"]
        self._header = self._ensure_header()

    def _ensure_header(self) -> list[str]:
        header = self._ws.row_values(1)
        if not header:
            self._ws.append_row(COLUMNS)
            return COLUMNS
        return header

    def _find_row_index(self, match_value: str) -> int | None:
        col_idx = self._header.index(self._match_column) + 1
        values = self._ws.col_values(col_idx)
        for i, v in enumerate(values[1:], start=2):  # skip header, sheet rows are 1-indexed
            if v == match_value:
                return i
        return None

    def append_or_update(self, row: dict[str, str]) -> str:
        """Mirrors n8n's appendOrUpdate: update the row if Job ID already exists,
        otherwise append a new row. Returns 'updated' or 'appended'."""

        ordered_values = [row.get(col, "") for col in self._header]
        match_value = row.get(self._match_column, "")

        existing_row_idx = self._find_row_index(match_value)
        if existing_row_idx is not None:
            self._ws.update(
                f"A{existing_row_idx}",
                [ordered_values],
            )
            logger.info("Updated row %d for Job ID %s", existing_row_idx, match_value)
            return "updated"

        self._ws.append_row(ordered_values)
        logger.info("Appended new row for Job ID %s", match_value)
        return "appended"

    def get_row(self, job_id: str) -> dict[str, str] | None:
        """Fetches an existing row by Job ID as a {column: value} dict, or
        None if no row matches. Used to pull a job that's already in the
        sheet (e.g. for regenerating a resume) without re-scraping/scoring."""

        row_idx = self._find_row_index(job_id)
        if row_idx is None:
            return None

        values = self._ws.row_values(row_idx)
        # row_values() can come back shorter than the header if trailing
        # cells are empty — pad so zip() doesn't silently drop columns.
        values += [""] * (len(self._header) - len(values))
        return dict(zip(self._header, values))

    def update_cell(self, job_id: str, column: str, value: str) -> bool:
        """Updates a single column for the row matching job_id. Returns False
        if no matching row was found (no-op), True if updated."""

        row_idx = self._find_row_index(job_id)
        if row_idx is None:
            logger.warning("No row found for Job ID %s, can't update %r.", job_id, column)
            return False

        col_idx = self._header.index(column) + 1
        self._ws.update_cell(row_idx, col_idx, value)
        logger.info("Updated %r for Job ID %s", column, job_id)
        return True
