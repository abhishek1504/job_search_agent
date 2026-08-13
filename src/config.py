"""Loads config.yaml + .env into a single settings object used across the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    raw: dict[str, Any]

    # --- credentials (from .env) ---
    apify_api_token: str
    openai_api_key: str
    google_service_account_file: str
    linkedin_cookies_file: str | None
    linkedin_user_agent: str | None

    # --- convenience accessors mirroring config.yaml sections ---
    @property
    def scraper_mode(self) -> str:
        return self.raw.get("scraper_mode", "public")

    @property
    def apify(self) -> dict:
        return self.raw["apify"]

    @property
    def apify_authenticated(self) -> dict:
        return self.raw["apify_authenticated"]

    @property
    def batch_size(self) -> int:
        return self.raw["batching"]["batch_size"]

    @property
    def scoring(self) -> dict:
        return self.raw["scoring"]

    @property
    def google_sheets(self) -> dict:
        return self.raw["google_sheets"]

    @property
    def resume_generation(self) -> dict:
        return self.raw["resume_generation"]

    @property
    def candidate(self) -> dict:
        return self.raw["candidate"]


def load_settings(config_path: str | Path = ROOT_DIR / "config.yaml") -> Settings:
    load_dotenv(ROOT_DIR / ".env")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    missing = [
        name
        for name in ("APIFY_API_TOKEN", "OPENAI_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )

    scraper_mode = raw.get("scraper_mode", "public")
    linkedin_cookies_file = os.getenv("LINKEDIN_COOKIES_FILE", "./linkedin_cookies.json")
    linkedin_user_agent = os.getenv("LINKEDIN_USER_AGENT")

    if scraper_mode == "authenticated":
        if not Path(linkedin_cookies_file).exists():
            raise RuntimeError(
                f"scraper_mode is 'authenticated' but cookies file not found at "
                f"{linkedin_cookies_file}. Export your LinkedIn session cookies and set "
                f"LINKEDIN_COOKIES_FILE in .env, or set scraper_mode back to 'public'."
            )
        if not linkedin_user_agent:
            raise RuntimeError(
                "scraper_mode is 'authenticated' but LINKEDIN_USER_AGENT is not set in .env."
            )

    return Settings(
        raw=raw,
        apify_api_token=os.environ["APIFY_API_TOKEN"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        google_service_account_file=os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE", "./service_account.json"
        ),
        linkedin_cookies_file=linkedin_cookies_file,
        linkedin_user_agent=linkedin_user_agent,
    )
