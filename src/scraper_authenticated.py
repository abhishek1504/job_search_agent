"""LinkedIn job scraping using a logged-in session (cookie-based auth).

Separate from scraper.py on purpose: this hits a different Apify actor
(curious_coder/linkedin-jobs-search-scraper, "Advanced Linkedin Job Scraper")
that requires your exported LinkedIn session cookies + user agent, and returns
personalized/recommended results the way your logged-in account would see them.

LinkedIn does not support real username/password automation (captcha/2FA block
it, and it would violate their ToS) — cookie-based auth is the supported
approach these scraping actors use instead. See .env.example for how to export
your cookies.

Because this ties scraping to your real account, treat it as higher-risk than
the anonymous public scraper (src/scraper.py): cookies expire and need
periodic re-export, and there's more chance of LinkedIn rate-limiting or
flagging the account for automated activity. scraper_mode: "public" in
config.yaml is the safer default; this module only runs when you explicitly
opt into scraper_mode: "authenticated".
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apify_client import ApifyClient

from .apify_compat import get_default_dataset_id
from .config import Settings
from .job_normalize import normalize_job

logger = logging.getLogger(__name__)


def _load_cookies(cookies_file: str) -> list[dict]:
    with open(cookies_file, "r") as f:
        return json.load(f)


def fetch_linkedin_jobs_authenticated(settings: Settings) -> list[dict[str, Any]]:
    client = ApifyClient(settings.apify_api_token)
    cfg = settings.apify_authenticated
    cookies = _load_cookies(settings.linkedin_cookies_file)

    all_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    search_urls = cfg["search_urls"]
    logger.info(
        "Running authenticated Apify actor %s across %d search URL(s)...",
        cfg["actor_id"],
        len(search_urls),
    )

    for search_url in search_urls:
        run_input = {
            "cookies": cookies,
            "userAgent": settings.linkedin_user_agent,
            "searchUrl": search_url,
            "scrapeJobDetails": cfg.get("scrape_job_details", True),
            "scrapeSkills": cfg.get("scrape_skills", True),
            "scrapeCompany": cfg.get("scrape_company", True),
        }
        if cfg.get("count"):
            run_input["count"] = cfg["count"]

        run = client.actor(cfg["actor_id"]).call(
            run_input=run_input,
            memory_mbytes=cfg.get("memory_mb"),
        )

        dataset_id = get_default_dataset_id(run)
        items = list(client.dataset(dataset_id).iterate_items())
        logger.info("Fetched %d job(s) for search URL: %s", len(items), search_url)

        for item in items:
            normalized = normalize_job(item)
            job_id = str(normalized.get("id", ""))
            if job_id and job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            all_items.append(normalized)

    logger.info("Fetched %d unique job listing(s) via authenticated scraper.", len(all_items))
    return all_items
