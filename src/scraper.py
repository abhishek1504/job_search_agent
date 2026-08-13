"""LinkedIn job scraping via Apify (public, logged-out search).

Mirrors the n8n "Get Linkedin jobs" + "Pick relevant items" nodes:
1. Run the cheap_scraper/linkedin-job-scraper actor with config.yaml's actor_input.
2. Pull all items from the run's default dataset, normalized onto a common schema.
"""

from __future__ import annotations

import logging
from typing import Any

from apify_client import ApifyClient

from .apify_compat import get_default_dataset_id
from .config import Settings
from .job_normalize import normalize_job

logger = logging.getLogger(__name__)


def fetch_linkedin_jobs(settings: Settings) -> list[dict[str, Any]]:
    client = ApifyClient(settings.apify_api_token)
    apify_cfg = settings.apify
    actor_input = apify_cfg["actor_input"]

    num_urls = len(actor_input.get("startUrls", []))
    logger.info(
        "Running Apify actor %s with %d start URL(s)...",
        apify_cfg["actor_id"],
        num_urls,
    )

    run = client.actor(apify_cfg["actor_id"]).call(
        run_input=actor_input,
        memory_mbytes=apify_cfg.get("memory_mb"),
        # This is distinct from actor_input's own "maxItems" field: that one is an
        # actor-specific input value, while this is the platform-level pay-per-result
        # billing cap (what the actor's "Maximum charged results" warning refers to).
        # Both need to be set for pay-per-result actors like this one.
        max_items=actor_input.get("maxItems"),
    )

    dataset_id = get_default_dataset_id(run)
    logger.info("Actor run finished, pulling dataset %s...", dataset_id)

    items = [normalize_job(item) for item in client.dataset(dataset_id).iterate_items()]
    logger.info("Fetched %d job listing(s) from Apify.", len(items))
    return items
