# Apply Jobs Guru

A **local, token-free** BFSI job-discovery engine + application tracker, built for a
fraud / credit-risk / analytics job search in the US (H-1B aware). It scrapes fresh
postings from job boards **and directly from banks' Workday APIs**, auto-grows a
directory of hiring companies, and gives you a Streamlit dashboard to track every
application (new → applied → interview → offer).

No API keys. No monthly fees. No cloud. Your data stays in `data/jobs.db`.

## Why the Workday lane matters
Most scrapers only hit Indeed/LinkedIn (and get blocked by Glassdoor/ZipRecruiter).
Every Workday customer also exposes a **public JSON careers API**
(`/wday/cxs/{tenant}/{site}/jobs`) — the same endpoint the bank's own careers page
calls. It isn't bot-blocked and costs nothing. One run already pulls **400+ real jobs**
straight from Citi, PNC, Mastercard, Fiserv, Morgan Stanley, State Street, FIS, Nasdaq.

## Quick start
```bash
pip install -r requirements.txt
python run.py            # scrape boards + Workday → data/jobs.db
streamlit run app.py     # open the tracker dashboard
```

## How it works
```
 job boards (JobSpy)  ─┐
 Indeed / LinkedIn /   │
 Google Jobs          │
                       ├─►  filter titles (config/profile.yml)  ─►  data/jobs.db
 Workday JSON API     │        + register every company             │
 (banks, verified)   ─┘          in the directory                   │
                                                                     ▼
                                                       Streamlit app (app.py)
                                              Jobs table · Company directory · Funnel
```

- **`run.py`** — orchestrator. `--boards` or `--workday` to run one lane.
- **`src/scrape_boards.py`** — JobSpy multi-site scraper (proxy-ready).
- **`src/scrape_workday.py`** — Workday JSON feeder. Add banks by appending to
  `TENANTS`; use `python -m src.scrape_workday --probe <host> <tenant>` to find the site slug.
- **`src/db.py`** — SQLite schema: `jobs` (with editable `status` = your tracker) + `companies` (auto-growing directory).
- **`config/profile.yml`** — all keywords, search terms, sites, proxies. No code edits needed.

## The company directory
Every company seen in any scrape is recorded once, with its careers page and Workday
API URL when known. Over time this becomes your own map of who hires for BFSI
analytics — so you can check an employer directly even on days the boards miss it.
Export to CSV from the Companies tab.

## Ideas adapted from existing projects
This repo deliberately borrows the good parts of the open-source job-hunt ecosystem
and leaves out the risky parts (see table). It is **not** a fork of any of them.

| Repo | What it does well | Adapted here? |
|------|-------------------|---------------|
| [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) | Battle-tested multi-board scraper (Indeed/LinkedIn/Google), proxy rotation | ✅ Used as our board-scraping engine (`scrape_boards.py`) |
| [emredurukn/awesome-job-boards](https://github.com/emredurukn/awesome-job-boards) | Curated master list of job boards | ✅ Sourced extra finance/data boards (eFinancialCareers, DataJobs, icrunchdata…) for the roadmap |
| [PaulMcInnis/JobFunnel](https://github.com/PaulMcInnis/JobFunnel) | Local CSV pipeline, dedup, block-list of stale jobs | ✅ Local-first DB + dedup-on-insert + status tracker |
| [DaKheera47/job-ops](https://github.com/DaKheera47/job-ops) | End-to-end "job ops" pipeline with a UI | ✅ Inspired the run→store→dashboard split |
| [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) | AI relevance scoring of scraped jobs | ⚠️ Partial — we keep a `score` column; LLM scoring is optional (hand URLs to career-ops) to stay $0 |
| [amusi/AI-Job-Recommend](https://github.com/amusi/AI-Job-Recommend) | Curated role recommendations | ⚠️ Concept only — our "core-fit ★" ranking is the lightweight version |
| [AndrewStetsenko/tech-jobs-with-relocation](https://github.com/AndrewStetsenko/tech-jobs-with-relocation) | Relocation/visa-friendly listings | ⚠️ Repurposed as the H-1B **sponsor-priority** flag in the directory (not relocation) |
| [GodsScion/Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn) | Auto-fills & submits LinkedIn Easy Apply | ❌ **Not adapted** — auto-submitting violates LinkedIn ToS and risks a permanent ban. We assist, you press submit. |
| [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) | Agent for BOSS Zhipin (China board) | ❌ Not relevant to a US search |

## Roadmap (easy next steps for your frontend)
1. **More Workday banks** — probe & add tenants (BofA, Truist, Capital One use non-obvious host numbers).
2. **Careers-page auto-resolve** — for each new company in the directory, look up its careers URL.
3. **Optional AI scoring** — fill the `score` column via a free model (OpenRouter) or career-ops.
4. **Resume tailoring / cover letters** — hand a chosen job to career-ops (`/career-ops pdf`).
5. **Richer frontend** — the SQLite DB is your API; swap Streamlit for React/Next if you like.

## Safety
- Local-first: everything runs on your machine.
- Never auto-submits an application — assist only.
- Only reads **public** job data (the same endpoints careers pages already call).
