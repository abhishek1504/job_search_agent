"""Small compatibility shim for apify-client's ActorClient.call() return value.

Older apify-client versions (<3.0) returned a plain dict, so code accessed
run["defaultDatasetId"]. Newer versions (>=3.0) return a typed `Run` pydantic
object with snake_case attributes instead (run.default_dataset_id), which
isn't subscriptable and breaks dict-style access.

This helper works with either, so the scraper modules don't have to care
which apify-client version is installed.
"""

from __future__ import annotations

from typing import Any


def get_default_dataset_id(run: Any) -> str:
    if run is None:
        raise RuntimeError(
            "Apify actor run did not return a result (call() returned None) — "
            "it likely didn't finish within the wait time. Check the run in the "
            "Apify console."
        )
    if isinstance(run, dict):
        return run["defaultDatasetId"]
    return run.default_dataset_id
