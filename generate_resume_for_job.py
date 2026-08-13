"""Generate (or regenerate) a tailored resume PDF for a job that's already in
the Google Sheet, using its stored Prompt column — no re-scraping or
re-scoring needed.

Usage:
    python generate_resume_for_job.py <job_id>

Example:
    python generate_resume_for_job.py 4218827671

What it does:
1. Looks up the row with that Job ID in the sheet.
2. Feeds its "Prompt" column (the tailoring instructions saved when the job
   was first scored) to OpenAI to draft resume content, then renders a PDF.
3. Uploads the PDF to the Drive folder configured in config.yaml
   (resume_generation.drive_folder_id) and writes the link back into the
   sheet's "Resume Link" column.
4. Also saves a local copy under resume_generation.output_dir.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from openai import OpenAI

from src.config import load_settings
from src.resume_generator import generate_resume_from_prompt
from src.sheets import JobsSheet

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_resume_for_job")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <job_id>", file=sys.stderr)
        sys.exit(1)

    job_id = sys.argv[1]

    settings = load_settings()
    sheet = JobsSheet(settings)

    row = sheet.get_row(job_id)
    if row is None:
        logger.error("No row found in the sheet for Job ID %r.", job_id)
        sys.exit(1)

    prompt_text = row.get("Prompt", "")
    company_name = row.get("Company Name", "")
    title = row.get("Title", "<untitled>")

    if not prompt_text:
        logger.error(
            "Row for Job ID %r has no Prompt column value — nothing to generate from.", job_id
        )
        sys.exit(1)

    logger.info("Generating resume for %r at %s (Job ID %s)...", title, company_name, job_id)

    resume_cfg = settings.resume_generation
    openai_client = OpenAI(api_key=settings.openai_api_key)

    path = generate_resume_from_prompt(
        openai_client,
        prompt_text,
        company_name,
        model=resume_cfg["model"],
        max_pages=resume_cfg["max_pages"],
        output_dir=Path(resume_cfg["output_dir"]),
    )
    logger.info("Resume saved locally: %s", path)

    folder_id = resume_cfg.get("drive_folder_id")
    if not folder_id:
        logger.warning(
            "No resume_generation.drive_folder_id set in config.yaml — skipping Drive upload. "
            "The PDF is only available at the local path above."
        )
        return

    from src.drive import upload_resume

    link = upload_resume(
        settings, path, folder_id, share_with_email=resume_cfg.get("share_with_email")
    )
    sheet.update_cell(job_id, "Resume Link", link)
    logger.info("Uploaded to Drive and linked in sheet: %s", link)


if __name__ == "__main__":
    main()
