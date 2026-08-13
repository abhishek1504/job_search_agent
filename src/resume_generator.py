"""Optional: automated tailored-resume PDF generation.

This is an automated alternative to the manual "paste the Prompt column into
Gemini/Canvas" step. It reuses the exact same Prompt content as the n8n
workflow's Prompt column (see sheets.build_prompt_column), but instead of you
pasting it into a chat UI, it:

1. Asks OpenAI to draft tailored resume content as structured JSON.
2. Renders that JSON into a clean PDF with reportlab.
3. If the PDF exceeds the configured page limit, asks the model to trim it
   down and re-renders (one retry).

Disabled by default (resume_generation.enabled in config.yaml).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI
from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from .sheets import build_prompt_column

logger = logging.getLogger(__name__)

RESUME_JSON_SCHEMA_HINT = """Respond with ONLY a JSON object (no markdown fences) shaped like:
{
  "name": "",
  "title": "",
  "contact": {"email": "", "phone": "", "location": "", "github": ""},
  "summary": "2-3 sentence professional summary tailored to this job",
  "skills": ["skill1", "skill2", "..."],
  "experience": [
    {"role": "", "company": "", "dates": "", "bullets": ["achievement-focused bullet", "..."]}
  ],
  "projects": [
    {"name": "", "description": ""}
  ],
  "education": [
    {"degree": "", "school": "", "dates": ""}
  ],
  "certifications": ["", "..."]
}"""


def _draft_resume_json(client: OpenAI, model: str, prompt_text: str, trim_hint: str = "") -> dict[str, Any]:
    system = (
        "You are an expert resume writer. Tailor the candidate's resume content to the "
        "specific job description provided, using ONLY facts present in their profile "
        "(never invent employers, dates, or credentials). Prioritize the most relevant "
        "experience and skills for this job. " + RESUME_JSON_SCHEMA_HINT
    )
    if trim_hint:
        system += f"\n\n{trim_hint}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt_text},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _render_pdf(resume: dict[str, Any], output_path: Path) -> None:
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle("Name", parent=styles["Title"], fontSize=18, spaceAfter=2)
    title_style = ParagraphStyle("JobTitle", parent=styles["Normal"], fontSize=11, textColor="#444444", spaceAfter=8)
    contact_style = ParagraphStyle("Contact", parent=styles["Normal"], fontSize=9, spaceAfter=10)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=13)
    bullet_style = ParagraphStyle("Bullet", parent=styles["Normal"], fontSize=9.5, leading=12)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
    )

    story = []
    contact = resume.get("contact", {})
    story.append(Paragraph(resume.get("name", ""), name_style))
    if resume.get("title"):
        story.append(Paragraph(resume["title"], title_style))
    contact_line = " | ".join(
        v for v in [contact.get("email"), contact.get("phone"), contact.get("location"), contact.get("github")] if v
    )
    story.append(Paragraph(contact_line, contact_style))

    if resume.get("summary"):
        story.append(Paragraph("Summary", section_style))
        story.append(Paragraph(resume["summary"], body_style))

    if resume.get("skills"):
        story.append(Paragraph("Skills", section_style))
        story.append(Paragraph(" &nbsp;•&nbsp; ".join(resume["skills"]), body_style))

    if resume.get("experience"):
        story.append(Paragraph("Experience", section_style))
        for exp in resume["experience"]:
            header = f"<b>{exp.get('role', '')}</b> — {exp.get('company', '')} ({exp.get('dates', '')})"
            story.append(Paragraph(header, body_style))
            bullets = [ListItem(Paragraph(b, bullet_style)) for b in exp.get("bullets", [])]
            if bullets:
                story.append(ListFlowable(bullets, bulletType="bullet", leftIndent=14))
            story.append(Spacer(1, 4))

    if resume.get("projects"):
        story.append(Paragraph("Projects", section_style))
        for proj in resume["projects"]:
            story.append(Paragraph(f"<b>{proj.get('name', '')}</b> — {proj.get('description', '')}", body_style))

    if resume.get("education"):
        story.append(Paragraph("Education", section_style))
        for edu in resume["education"]:
            story.append(
                Paragraph(f"{edu.get('degree', '')}, {edu.get('school', '')} ({edu.get('dates', '')})", body_style)
            )

    if resume.get("certifications"):
        story.append(Paragraph("Certifications", section_style))
        story.append(Paragraph(", ".join(resume["certifications"]), body_style))

    doc.build(story)


def _page_count(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def generate_resume(
    client: OpenAI,
    job: dict[str, Any],
    candidate: dict[str, str],
    model: str,
    max_pages: int,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    company = (job.get("companyName") or "Unknown").strip().replace("/", "-")
    output_path = output_dir / f"Resume_{company}.pdf"

    prompt_text = build_prompt_column(job, candidate)

    resume_json = _draft_resume_json(client, model, prompt_text)
    _render_pdf(resume_json, output_path)

    if _page_count(output_path) > max_pages:
        logger.info("Resume for %s exceeded %d page(s), asking model to trim...", company, max_pages)
        trim_hint = (
            f"Your previous draft rendered to more than {max_pages} page(s). "
            f"Significantly shorten it: keep only the most relevant 2-3 experience entries, "
            f"trim bullets to the strongest ones, and tighten the summary."
        )
        resume_json = _draft_resume_json(client, model, prompt_text, trim_hint=trim_hint)
        _render_pdf(resume_json, output_path)

    logger.info("Resume saved to %s (%d page(s))", output_path, _page_count(output_path))
    return output_path
