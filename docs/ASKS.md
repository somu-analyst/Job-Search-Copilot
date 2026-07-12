# Ask Tracker — Job Search Copilot

Every request Srinivas makes + every suggestion Claude proposes, with status.
**Update this file whenever a new ask arrives or a status changes.**
Status: ✅ done · 🔄 in progress · ⏳ pending (needs user) · ❌ dropped (with reason)

---

## A. Core system — job discovery & tracking

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| A1 | Standalone app, not Claude every time (no token burn) | ✅ | `run.py` + Streamlit; zero Claude tokens |
| A2 | Streamlit frontend (not Excel) | ✅ | `app.py`, 7 tabs |
| A3 | Auto-pull jobs 2×/day + score | ✅ | Windows Task `CareerOps-JobScan` 9AM/5PM |
| A4 | Pull from ALL sources, not just Workday | ✅ | JobSpy (Indeed/LinkedIn/Google) + Adzuna + Jooble + 29 Workday tenants |
| A5 | Numeric 1–10 score + "must apply" flag | ✅ | `score.py`, `MUST_APPLY_AT=8.0` |
| A6 | Mark applied → moves to Applied tab w/ date; skip flag | ✅ | status + `date_applied` |
| A7 | USA-primary filtering | ✅ | `is_us_location()` + Workday city-path check |
| A8 | Freshness filter (pulled) **and** job-posted-date filter | ✅ | both `date_found` + `date_posted` |
| A9 | Industry column | ✅ | `INDUSTRY_MAP` |
| A10 | Company directory that grows from scraped jobs | ✅ | `companies` table, 385+ companies |
| A11 | Salary shown as FYI (not a filter; blank if unlisted) | ✅ | API fields + JD regex; rejects "$23B portfolio" |

## B. Coverage — employers & keywords

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| B1 | H-1B sponsors first; screen out citizen-only | ✅ | `sponsors.py` (~90 map) + `jd_flags()` |
| B2 | Small institutions, credit unions, prime vendors, consulting | ✅ | in QUERIES |
| B3 | SAS / SAS Viya as primary skill | ✅ | in QUERIES (banks list SAS in JD body, not titles) |
| B4 | Compliance, reporting, data mgmt, leadership roles | ✅ | in QUERIES + `title_ok()` |
| B5 | HSBC, MUFG, SMBC, Mizuho, Prudential, Fidelity, Vanguard, Liberty Mutual | ✅ | Workday tenants / sponsor map |
| B6 | Trading & broking firms | ✅ | Raymond James, Ameriprise, BlackRock… |
| B7 | California / Google-search jobs | ✅ | Google Jobs via JobSpy; US-wide |

## C. Resume maker & Apply center

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| C1 | ATS-clean resume, no emojis, drop odd "Target Role" | ✅ | `_ats_clean()` |
| C2 | Multi-scores: recruiter / ATS-Workday / hiring-mgr / overall | ✅ | `jd_match.analyze()` |
| C3 | Highlights + what's missing from the position | ✅ | |
| C4 | AI-tailored resume with **1–10 strength slider** | ✅ | `tailor_summary(intensity)` |
| C5 | Scores for the tailored version (before/after) | ✅ | |
| C6 | Authenticity / over-claim alerts | ✅ | `authenticity_check()` |
| C7 | User picks WHICH missing keywords to add | ✅ | multiselect |
| C8 | View the JD (inline or sidebar) | ✅ | Workday API + stored descriptions |
| C9 | Sponsorship / location deal-breaker screen | ✅ | `jd_flags()` |
| C10 | Resume header line-wrap looked bad | ✅ | forced break between title + contact |
| C11 | Best FREE AI models, no paid | ✅ | all fast `:free` OpenRouter + Gemini fallback |
| C12 | Automate the Workday application itself | ⏳ | Playwright assisted-apply built; **never auto-submits** (ban risk). Needs your first login session |

## D. Direct apply links (no reposters)

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| D1 | Citizens job opened Lensa, not the real portal | ✅ | direct link found; Citizens = Radancy, not Workday |
| D2 | Do this for ALL jobs automatically after pulling | 🔄 | 4-tier resolver; **911/1395 (65%) linked, 0 reposters**; still running |
| D3 | Auto-discover each employer's ATS into the directory | ✅ | 41 companies mapped (Workday/Greenhouse/Lever/SmartRecruiters/Radancy) |

## E. UI / UX

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| E1 | Job picker: show headers + all columns, scrollable | ✅ | real table picker replaces flat dropdown |
| E2 | Steps in boxes with arrows; Step 1 was eating half the page | ✅ | visual stepper + compact step boxes |
| E3 | Premium/sellable SaaS look, less noise | ✅ | one primary + one accent, hairline borders, type scale |
| E4 | Put Steps 2–4 in sub-tabs for a true single screen | ⏳ | **offered — awaiting your yes/no** |

## F. Repo, sharing, security

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| F1 | Name the project | ✅ | **Job Search Copilot** 🧭 |
| F2 | Own git repo, shareable — any user drops resume + keywords | ✅ | `profile.example.yml`, `cv.example.md` |
| F3 | **Never commit keys; keep them secure** | ✅ | 0 keys in git history; `profile.yml` gitignored; verified on push |
| F4 | Push to GitHub | ✅ | `github.com/somu-analyst/job-search-copilot` (private) |
| F5 | Keep job project separate from NYSE_DATA stock bot | ✅ | verified: no job files in NYSE_DATA |
| F6 | Track my asks + your suggestions in a table, every time | ✅ | **this file**; shown at end of each reply |

---

## Pending — needs YOU

| # | Item | What to do |
|---|------|-----------|
| C12 | First assisted-apply session | Pick a job → Assisted Apply → log into the portal → review & submit yourself |
| E4 | Steps 2–4 as sub-tabs? | Say yes and I'll do it |
| G1 | Target salary range | You chose: show listed salary as FYI, no filter → **closed** ✅ |
| G2 | AI daily cap | Free tiers reset on their own. $10 OpenRouter credit = 1,000/day (optional; you said free-only) |

## Explicitly dropped (by your call)

| Item | Why |
|------|-----|
| Auto-submit LinkedIn appliers | Ban risk — you agreed to skip |
| Resume upload to Dice / HireITPeople | You said don't expose your resume; never happened |
| Paid AI models | You said free only |
