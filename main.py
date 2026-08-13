"""Job Search Agent — Python port of the "Job Automation" n8n workflow.

Pipeline (mirrors the n8n node graph):
  1. Get Linkedin jobs      -> src.scraper.fetch_linkedin_jobs   (Apify actor run)
                               or src.scraper_authenticated.fetch_linkedin_jobs_authenticated
                               depending on config.yaml's scraper_mode
  2. Pick relevant items    -> included in fetch_linkedin_jobs   (dataset items)
  3. Loop Over Items        -> simple batching loop below
  4. Curate Linkedin jobs   -> src.scorer.score_job              (OpenAI match score)
  5. Filter                 -> score > threshold
  6. Update Linkedin jobs   -> src.sheets.JobsSheet.append_or_update

Run manually:
    python main.py
"""

from __future__ import annotations

import logging

from openai import OpenAI

from src.config import load_settings
from src.scraper import fetch_linkedin_jobs
from src.scorer import score_job
from src.sheets import JobsSheet, build_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("job_search_agent")


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_jobs(settings):
    """Picks the scraper per config.yaml's scraper_mode. If 'authenticated' fails
    (e.g. expired cookies) and apify_authenticated.fallback_to_public is true,
    falls back to the anonymous public scraper for this run."""

    if settings.scraper_mode != "authenticated":
        return fetch_linkedin_jobs(settings)

    from src.scraper_authenticated import fetch_linkedin_jobs_authenticated

    try:
        return fetch_linkedin_jobs_authenticated(settings)
    except Exception:
        if settings.apify_authenticated.get("fallback_to_public", True):
            logger.exception(
                "Authenticated scraper failed, falling back to the public scraper for this run."
            )
            return fetch_linkedin_jobs(settings)
        raise


def main():
    settings = load_settings()
    openai_client = OpenAI(api_key=settings.openai_api_key)
    sheet = JobsSheet(settings)

    threshold = settings.scoring["score_threshold"]
    model = settings.scoring["model"]

    resume_cfg = settings.resume_generation
    resume_enabled = resume_cfg.get("enabled", False)
    if resume_enabled:
        from pathlib import Path
        from src.resume_generator import generate_resume

    jobs = fetch_jobs(settings)
    if not jobs:
        logger.info("No jobs returned from Apify. Exiting.")
        return

    total_matched = 0

    # Mirrors the n8n "Loop Over Items" batching (batch size from config).
    for batch_num, batch in enumerate(chunked(jobs, settings.batch_size), start=1):
        logger.info("Processing batch %d (%d job(s))...", batch_num, len(batch))

        for job in batch:
            title = job.get("title", "<untitled>")
            try:
                result = score_job(openai_client, model, job)
            except Exception:
                logger.exception("Scoring failed for job %r, skipping.", title)
                continue

            logger.info("Scored %r -> %d (%s)", title, result.score, result.raw_text)

            if result.score <= threshold:
                continue

            total_matched += 1
            row = build_row(job, result.raw_text, settings.candidate)

            try:
                action = sheet.append_or_update(row)
            except Exception:
                logger.exception("Failed to write job %r to Google Sheet.", title)
                continue

            logger.info("%s row in Google Sheet for %r (score %d)", action, title, result.score)

            if resume_enabled:
                try:
                    path = generate_resume(
                        openai_client,
                        job,
                        settings.candidate,
                        model=resume_cfg["model"],
                        max_pages=resume_cfg["max_pages"],
                        output_dir=Path(resume_cfg["output_dir"]),
                    )
                    logger.info("Generated tailored resume: %s", path)
                except Exception:
                    logger.exception("Resume generation failed for job %r.", title)

    logger.info("Done. %d/%d job(s) cleared the score threshold (>%d).", total_matched, len(jobs), threshold)


if __name__ == "__main__":
    main()
