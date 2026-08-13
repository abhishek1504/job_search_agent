"""Job match scoring via OpenAI.

Mirrors the n8n "Curate Linkedin jobs" OpenAI node: scores each job listing out of
10 against the candidate's resume, using the same rubric and system prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from .config import ROOT_DIR, Settings

logger = logging.getLogger(__name__)

SCORE_PATTERN = re.compile(r"\d+")


def _load_resume_text() -> str:
    return (ROOT_DIR / "data" / "scoring_resume.txt").read_text().strip()


def build_system_prompt(resume_text: str) -> str:
    return f"""You're an intelligent bot rating how closely a job listing matches the candidate's profile and preferences, on a score out of 10. Add up the points below and return the total.

a) Skill & role fit vs. resume: 5 points if the role is an outstanding match (Engineering Manager / AVP / Director / Head of Engineering / Technical Product Manager, in fintech, e-commerce, or product engineering, overlapping with mobile, full-stack, distributed systems, cloud/AWS, or AI/LLM-agentic work), 3 points if it's a partial match (strong technical overlap but different seniority, e.g. a Staff/Principal IC role, or a good functional match in an unfamiliar domain), 1 point if there's only minor overlap.
b) Location: 2 points if the job is based in Hyderabad, 1 point if it's remote or hybrid with Hyderabad listed as an option, 0 points otherwise.
c) Company type: 2 points if it's a product-based company (not an IT services / staffing / outsourcing firm — e.g. not TCS, Infosys, Wipro, Accenture, Capgemini, Cognizant, HCL), 0 points if it's a services/staffing company, 1 point if unclear from the posting.
d) Seniority: 1 point if the title reflects a management or senior leadership level (Manager, AVP, Director, Head, Principal, Staff) consistent with 17+ years of experience and a current CTC of ~48 LPA, 0 points if it's clearly a junior/entry-level posting.

Add a) + b) + c) + d) for the total out of 10.

For example:
If the role is an outstanding fit, based in Hyderabad, at a product company, and is a manager-level title, the total is: 5+2+2+1 = 10
If the role is a partial fit, remote (not Hyderabad-based), at a services company, but still senior-level, the total is: 3+1+0+1 = 5
###

CANDIDATE RESUME:
{resume_text}

OUTPUT FORMAT:
Respond with only the total score as a number, followed by a one-line breakdown showing how the score was calculated, e.g.:
8 (a:5 b:2 c:0 d:1)"""


def build_user_prompt(job: dict[str, Any]) -> str:
    return (
        "Evaluate this job posting.\n\n"
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('companyName', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Job Description:\n{job.get('descriptionText', '')}"
    )


@dataclass
class ScoreResult:
    score: int
    raw_text: str


def score_job(client: OpenAI, model: str, job: dict[str, Any], resume_text: str | None = None) -> ScoreResult:
    resume_text = resume_text or _load_resume_text()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt(resume_text)},
            {"role": "user", "content": build_user_prompt(job)},
        ],
    )
    raw_text = response.choices[0].message.content.strip()

    match = SCORE_PATTERN.search(raw_text)
    if not match:
        logger.warning("Could not parse a score out of OpenAI response: %r", raw_text)
        return ScoreResult(score=0, raw_text=raw_text)

    return ScoreResult(score=int(match.group(0)), raw_text=raw_text)
