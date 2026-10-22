# 🏹 Job Search Copilot

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/SQLite-local--first-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Source](https://img.shields.io/badge/source-private-lightgrey)](#source-code)
[![Status](https://img.shields.io/badge/status-active-brightgreen)]()

**find · tailor · apply · track**: a local job-search engine that costs nothing to run.

It finds roles across every source it can reach and scores each one against *your*
resume. It writes tailored versions of that resume for each job and scores those too.
It links you **straight to the employer's own application page** (never a reposter), and
it tracks everything you sent and when.

Everything runs on your own machine: a SQLite database and a Streamlit app. The AI uses
**free** models, and when they hit their limits it falls back to rule-based scoring, so
it never dead-ends.

> This repository is the public showcase: what the project does, how it works, and
> what it looks like. The source code is private. See [Source code](#source-code).

## ▶ Walkthrough video

[![Watch the walkthrough](assets/screenshots/01_today.png)](assets/walkthrough.mp4)

**[▶ Play the walkthrough (MP4)](assets/walkthrough.mp4)**: clicking through all
8 tabs against a live database of 1,395 jobs.

## Screenshots

| | |
|---|---|
| **🎯 Today**: highest-fit picks, apply straight to the employer's own portal | **📋 Jobs**: every job found, filter/sort/status inline |
| ![Today](assets/screenshots/01_today.png) | ![Jobs](assets/screenshots/02_jobs.png) |
| **✅ Applied**: every application, its status and when it was sent | **📄 Resume Studio**: pick a job, score fit, AI-tailor, generate docs |
| ![Applied](assets/screenshots/03_applied.png) | ![Resume Studio](assets/screenshots/04_resume_studio.png) |
| **🗂 My Resumes**: every version archived, timestamped, tied to its job | **🏢 Companies**: employer directory, finds each employer's hiring system automatically |
| ![My Resumes](assets/screenshots/05_my_resumes.png) | ![Companies](assets/screenshots/06_companies.png) |
| **🎫 Sponsors**: H-1B sponsor priority from public disclosure data | **📊 Insights**: what the search is turning up, over time |
| ![Sponsors](assets/screenshots/07_sponsors.png) | ![Insights](assets/screenshots/08_insights.png) |

## The pipeline

```
  job boards           ─┐
  (Indeed / LinkedIn /  │
   Google Jobs)         │
                        │        title + location filter          ┌────────────────┐
  employer career-site ─┼──────► drop duplicates           ─────►│  SQLite DB     │
  APIs (direct)         │        fit score 1–10                   │  jobs          │
                        │        H-1B sponsor tag                 │  companies     │
  job-search APIs      ─┤        salary (FYI)                     │  resumes       │
                        │                                         └────────┬───────┘
  email job alerts      │        find the REAL apply link                  ▼
  (opt-in)            ──┘                                        Streamlit app
```

## What makes it different

**Direct apply links.** Job aggregators bounce you through third-party reposters that
often can't even take an application. Copilot finds the employer's real link for **every**
job. It works out which hiring system each employer uses (Workday, Greenhouse, Lever,
Ashby, SmartRecruiters and others), queries that employer's own job listings, and
remembers the answer. The company directory gets smarter with every scan.

**Employer career sites, read directly.** Most job scrapers only hit Indeed and LinkedIn
and get blocked elsewhere. Copilot also reads the public job listings that employers' own
career pages load. They don't block automated requests, cost nothing, and yield hundreds
of jobs with full descriptions.

**Resume versions, scored.** For each job it writes several tailored versions
(Conservative / Balanced / ATS-max) and keeps your untouched master resume as a
baseline. It scores every version three ways: keyword coverage for the applicant
tracking system (ATS), how it reads to a recruiter skimming it, and how much depth it
shows a hiring manager. You *see* how many points a stronger rewrite gains and what it
costs in authenticity, instead of guessing.

**It never invents your experience.** Every tailored version is checked against your
real resume for skills it doesn't support, numbers you never had, and hype it added. It
also catches a subtler failure: a sentence built from *real* material that was never true
together, such as a tool from one employer paired with a result from another. Every word
is genuinely yours, so a simple word check would pass it. Copilot traces each claim back
to the specific resume facts behind it. It flags any claim it can't back up, and any
sentence that credits the wrong employer. When two facts together could cover a claim,
it asks you to confirm rather than accusing you. Each version gets a fabrication rate
you can compare. Over-claiming fails interviews and background checks, so this catches
it before you send.

**A resume archive.** Every version you generate or edit is stored with a timestamp and
the job it was for. Six months later, when a recruiter calls, you can pull up the exact
resume they're holding.

## What it deliberately does *not* do

- **It never submits an application for you.** Assisted apply opens the page and fills
  in what it can, then you read it and press Submit. Auto-submitters break site terms of
  service and risk a permanent ban on the account you need most.
- **It doesn't scrape LinkedIn for recruiter emails.** It uses contacts the employer
  **published**, plus optional Hunter.io lookups.
- **It only reads public job data:** the same listings career pages already load.

## Tech stack

Python · Streamlit · SQLite · keyword-relevance (BM25) and local meaning-based
(embedding) resume scoring · free LLMs (OpenRouter / Gemini) · Playwright · runs on
an Oracle Cloud VM with daily scheduled scans · offline test suite

## Source code

The source code is in a **private repository**. I'm happy to walk through it, or to give
access for interviews, code review or collaboration. Reach out through my
[GitHub profile](https://github.com/somu-analyst).

## License

© [somu-analyst](https://github.com/somu-analyst). All rights reserved. The text, screenshots and video in this repository
may not be reproduced without permission.
