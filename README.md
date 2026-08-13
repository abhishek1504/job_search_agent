# Job Search Agent

Python port of the "Job Automation" n8n workflow: scrapes LinkedIn jobs via Apify, scores
each one against your resume with OpenAI, and appends/updates matches (score > threshold)
in your Google Sheet.

## Pipeline (matches the n8n node graph 1:1)

| n8n node | Python equivalent |
|---|---|
| Get Linkedin jobs (Apify) | `src/scraper.py` |
| Pick relevant items (Apify dataset) | `src/scraper.py` |
| Loop Over Items | batching loop in `main.py` |
| Curate Linkedin jobs (OpenAI) | `src/scorer.py` |
| Filter (score > 7) | inline check in `main.py` |
| Update Linkedin jobs (Google Sheets appendOrUpdate) | `src/sheets.py` |
| *(manual, outside the workflow)* | `src/resume_generator.py` — optional, off by default |
| *(new)* | `src/scraper_authenticated.py` — optional, logged-in scraping via session cookies |

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt --break-system-packages
   ```

2. **Apify token** — from https://console.apify.com/account/integrations

3. **OpenAI key** — from https://platform.openai.com/api-keys

4. **Google Sheets access** (service account, no browser OAuth needed):
   - In Google Cloud Console, create a project (or reuse one), enable the **Google Sheets API**.
   - Create a **Service Account**, generate a JSON key, save it as `service_account.json` in this folder.
   - Open the JSON file, copy the `client_email` value, and **share your Google Sheet** with that
     email as an Editor.
   - Sheet used: https://docs.google.com/spreadsheets/d/1O_xIDTP54i2nZoUUo47YI-CO52jd08E2lahNEDNlZ5s

5. **Configure credentials**

   ```bash
   cp .env.example .env
   # then fill in APIFY_API_TOKEN, OPENAI_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE
   ```

6. **Run**

   ```bash
   python main.py
   ```

## Two scraper modes

`scraper_mode` in `config.yaml` picks which one runs:

- **`public`** (default) — anonymous, logged-out search via `cheap_scraper/linkedin-job-scraper`. Lower risk to your account, no maintenance. Search keywords/locations/filters live in `apify.actor_input` in `config.yaml`, passed straight through to the actor (see its [input schema](https://apify.com/cheap_scraper/linkedin-job-scraper/input-schema) for every available field — job type, experience level, work type, resume keyword scoring, company filters, etc.). Note: pay-per-result billing on this actor has a 150-result minimum per the actor's docs.
- **`authenticated`** — uses your logged-in LinkedIn session (via exported cookies) through `curious_coder/linkedin-jobs-search-scraper`, so results match what you'd see logged in (recommended jobs, applicant insights, skills, recruiter info). Setup:
  1. Install a cookie-export browser extension (e.g. Cookie-Editor).
  2. Log into linkedin.com normally in that browser.
  3. Export the LinkedIn cookies as JSON and save to a file, e.g. `./linkedin_cookies.json`.
  4. Set `LINKEDIN_COOKIES_FILE` and `LINKEDIN_USER_AGENT` in `.env` (see `.env.example`).
  5. Set `scraper_mode: "authenticated"` in `config.yaml`.

  LinkedIn doesn't support real username/password automation — this cookie-based approach is what these scraping actors use instead. Cookies expire periodically and need re-exporting. Because it's tied to your real account, it carries more risk of LinkedIn flagging/rate-limiting than the public scraper.

  If the authenticated run fails (e.g. expired cookies), the agent automatically falls back to the public scraper for that run when `apify_authenticated.fallback_to_public: true` (default). You can flip `scraper_mode` back to `"public"` at any time to fully revert.

  Note: neither actor's exact output field names are confirmed against a live sample run — `src/job_normalize.py`'s `normalize_job()` maps common variants (`jobTitle`→`title`, `company.name`→`companyName`, etc.) onto the schema the rest of the pipeline expects, and both scrapers share it. If some fields come through empty on your first run, check the raw item (it's preserved alongside the normalized fields) and extend `job_normalize.py`.

## Configuration (`config.yaml`)

- `scraper_mode` — `"public"` or `"authenticated"` (see above).
- `apify.actor_input` — the full input passed to `cheap_scraper/linkedin-job-scraper` (keywords, `startUrls`, `locations`, `jobType`, `experienceLevel`, `workType`, `resumeKeywords`, etc.), used in public mode.
- `apify_authenticated.search_urls` — search URLs, used in authenticated mode.
- `batching.batch_size` — how many jobs are processed per loop iteration (cosmetic here, kept for parity with n8n).
- `scoring.model` / `scoring.score_threshold` — OpenAI model and the score cutoff (jobs with score > threshold get written to the sheet).
- `google_sheets` — spreadsheet ID, worksheet name, and the column used to match existing rows (`Job ID`).
- `resume_generation.enabled` — off by default. Turn on to auto-draft and render a tailored 2-page resume PDF (using OpenAI + reportlab) for every job that clears the threshold, saved to `output/resumes/`. This replaces manually pasting the sheet's `Prompt` column into Gemini/Canvas — same underlying prompt, fully automated. If you'd rather keep doing that manually, leave it off; the `Prompt` column is still populated in the sheet either way.
- `candidate` — your contact details, used in the sheet's `Prompt` column and in resume generation.

## Candidate profile data (`data/`)

- `scoring_resume.txt` — condensed resume used for scoring (matches the n8n system prompt).
- `linkedin_profile.txt` — fuller LinkedIn-style profile used for resume tailoring.
- `resume_instructions.txt` — the tailoring instructions (2-page limit, which projects to
  highlight for AI-related roles, etc.).

Edit these freely — they're plain text, no need to touch the code.

## Running it from GitHub Actions

`.env` and `service_account.json` hold real secrets, so they're gitignored and never get pushed to
GitHub (see `.gitignore`). To run the agent from GitHub itself instead of your own machine, use
GitHub Actions Secrets — the workflow at `.github/workflows/run.yml` writes `.env` and
`service_account.json` from those secrets at the start of each run, then deletes itself along with
the whole runner when the job finishes.

1. On GitHub, go to your repo → **Settings → Secrets and variables → Actions → New repository secret**,
   and add:
   - `APIFY_API_TOKEN`
   - `OPENAI_API_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the **entire contents** of your `service_account.json` file
     (the whole JSON, not a file path)
   - Optional, only if you use `scraper_mode: "authenticated"`: `LINKEDIN_COOKIES_JSON` (entire
     exported cookies JSON) and `LINKEDIN_USER_AGENT`
2. Go to the **Actions** tab → **Run Job Search Agent** → **Run workflow**. It's manual-trigger-only
   (no schedule), so it only runs — and only spends Apify/OpenAI usage — when you click it.
3. Results land in your Google Sheet as usual. If `resume_generation.enabled` is on, the generated
   PDFs are attached to the workflow run as a downloadable artifact (the runner itself is thrown away
   after each run, so nothing persists there otherwise).

## Notes

- Matches the n8n Filter node's threshold exactly: `score > 7` by default (i.e. 8, 9, 10 pass).
- `sheets.append_or_update` mirrors n8n's `appendOrUpdate` operation: it looks for an existing
  row with a matching `Job ID` and updates it in place, otherwise appends a new row.
- Locally, this is a manual-run script — call `python main.py` whenever you want a fresh
  scrape + score + sheet update. From GitHub, use the Actions workflow above the same way.
