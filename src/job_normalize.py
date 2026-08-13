"""Shared helper for normalizing job records from different Apify actors onto
one common schema, so scorer.py and sheets.py don't need to know which
scraper produced a given job.

Different LinkedIn scraper actors use different field names for the same
data. This maps the common variants onto: id, title, companyName, location,
descriptionText, link, postedAt. Original fields are preserved too, in case
you need something actor-specific.
"""

from __future__ import annotations

from typing import Any


def first(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if "." in key:
            obj = item
            for part in key.split("."):
                obj = obj.get(part, {}) if isinstance(obj, dict) else {}
            if obj not in (None, {}, ""):
                return obj
        elif item.get(key) not in (None, ""):
            return item[key]
    return default


def normalize_job(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["id"] = first(item, "id", "jobId", "jobPostingId")
    normalized["title"] = first(item, "title", "jobTitle")
    normalized["companyName"] = first(
        item, "companyName", "company.name", "companyDetails.name", "organizationName", "company"
    )
    normalized["location"] = first(item, "location", "jobLocation", "textualLocation")
    normalized["descriptionText"] = first(
        item, "descriptionText", "description", "jobDescription", "descriptionHtml"
    )
    normalized["link"] = first(item, "link", "jobUrl", "url", "applyUrl", "applicationLink")
    normalized["postedAt"] = first(
        item, "postedAt", "postedDate", "listedAt", "publishedAt", "postingDate"
    )
    return normalized
