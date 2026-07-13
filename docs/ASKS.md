# Ask Tracker — Job Search Copilot

Every request Srinivas makes + every suggestion Claude proposes, with status.
**Update whenever a new ask arrives or a status changes.**
✅ done · 🔄 in progress · ⏳ waiting on user · ❌ dropped (with reason)

---

## A. Core system

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| A1 | Standalone app, no Claude tokens per run | ✅ | `run.py` + Streamlit |
| A2 | Streamlit frontend (not Excel) | ✅ | 8 tabs |
| A3 | Auto-pull 2×/day + score | ✅ | Windows Task 9AM/5PM |
| A4 | Pull from ALL sources | ✅ | Indeed/LinkedIn/Google + 29 Workday tenants + Adzuna + Jooble |
| A5 | Numeric 1–10 score + must-apply flag | ✅ | `MUST_APPLY_AT = 8.0` |
| A6 | Mark applied → Applied tab w/ date | ✅ | |
| A7 | USA-primary filtering | ✅ | |
| A8 | Freshness (pulled) **and** posted-date filter | ✅ | both |
| A9 | Industry column | ✅ | |
| A10 | Company directory grows from scrapes | ✅ | 385+ companies |
| A11 | Salary shown as FYI, never a filter | ✅ | rejects notional figures ("$23B portfolio") |

## B. Coverage

| # | Ask | Status |
|---|-----|--------|
| B1 | H-1B sponsors first; screen citizen-only | ✅ |
| B2 | Small institutions, credit unions, vendors, consulting | ✅ |
| B3 | SAS / SAS Viya as primary skill | ✅ |
| B4 | Compliance, reporting, data mgmt, leadership | ✅ |
| B5 | HSBC, MUFG, SMBC, Mizuho, Prudential, Fidelity, Vanguard… | ✅ |
| B6 | Trading & broking firms | ✅ |
| B7 | Google-search / California jobs | ✅ |

## C. Resume

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| C1 | ATS-clean, no emojis | ✅ | |
| C2 | Recruiter / ATS / hiring-mgr / overall scores | ✅ | |
| C3 | Highlights + what's missing | ✅ | |
| C4 | AI tailoring, 1–10 strength slider | ✅ | |
| C5 | Scores for the tailored version | ✅ | before/after deltas |
| C6 | Authenticity / over-claim alerts | ✅ | |
| C7 | Pick WHICH missing keywords to add | ✅ | |
| C8 | View the JD | ✅ | |
| C9 | Sponsorship / location deal-breaker screen | ✅ | |
| C10 | Header line-wrap looked bad | ✅ | |
| C11 | Free AI models only, no paid | ✅ | all `:free`, Gemini fallback, offline fallback |
| C12 | Resume too much bold; cut "Won sponsorship"; cause→effect | ✅ | 25→17 bullets, 25→7 bolds, word "sponsorship" gone entirely |
| C13 | New resume layout | ✅ | green rules, print-safe, still ATS-parseable |
| C14 | Store every resume used, w/ timestamp + job | ✅ | `resumes` table + 🗂 My Resumes tab |
| C15 | Multiple versions, pick best, preview all | ✅ | Master/Conservative/Balanced/ATS-max, scored |
| C16 | Edit points myself, then re-score | ✅ | edit → re-score → archived as its own version |
| C17 | Over-claim flags must show WHAT they are | ✅ | popover lists each claim; **fixed 3 checker bugs** |

## D. Apply links

| # | Ask | Status |
|---|-----|--------|
| D1 | Citizens opened Lensa, not the real portal | ✅ direct link found (Citizens = Radancy) |
| D2 | Do it for ALL jobs, automatically | ✅ **1,395/1,395 (100%), 0 reposters** |
| D3 | Auto-discover each employer's ATS into the directory | ✅ Workday/Greenhouse/Lever/SmartRecruiters/Radancy |

## E. Outreach

| # | Ask | Status | Notes |
|---|-----|--------|-------|
| E1 | Email recruiter / HR / hiring manager | ✅ | JD-published contacts + email-pattern guess + LinkedIn people-search + `mailto:` draft you review |
| E2 | Scrape LinkedIn for contacts | ❌ | **Declined.** Breaks ToS, risks the account you need to job-hunt, and guessed-address cold email performs worse than a hand-sent connection request. Hunter.io hook built as the legal alternative. |

## F. UI

| # | Ask | Status |
|---|-----|--------|
| F1 | Premium, sellable SaaS look | ✅ rebuilt; `ui/` layer split from logic |
| F2 | Job picker: headers + all columns, scrollable | ✅ real table picker |
| F3 | Steps in boxes with arrows | ✅ step rail |
| F4 | Steps 2–4 on one screen | ✅ sub-tabs |
| F5 | Not a monotone blue page | ✅ **Glassdoor green shell + Swiggy orange Apply** |
| F6 | Title too small | ✅ 42px + logo |
| F7 | Blank right side of hero | ✅ 5-stage system flow |
| F8 | Logo: bow + trishoolam (Rudrarjun) | ✅ hand-drawn; Arjuna at full draw, one trishoolam |
| F9 | Try Nano Banana / AI logo | ❌ **Dropped by user.** Gemini key 429s on *everything* (even free text); free FLUX generated 8 candidates but **none drew the trishoolam**. |

## G. Repo & security

| # | Ask | Status |
|---|-----|--------|
| G1 | Name the project | ✅ Job Search Copilot |
| G2 | Generic + shareable, not BFSI-specific | ✅ all BFSI copy stripped from app + README |
| G3 | **Never commit keys** | ✅ 0 keys in history; `profile.yml` + `cv.md` gitignored; verified on every push |
| G4 | Push to GitHub | ✅ `github.com/somu-analyst/job-search-copilot` (private) |
| G5 | Keep separate from the NYSE_DATA stock bot | ✅ verified clean |
| G6 | Track my asks + your suggestions in a table | ✅ this file, shown each reply |

---

## ⏳ Waiting on Srinivas (nothing is blocked on Claude)

| # | Item | What to do |
|---|------|-----------|
| 1 | **Regenerate the Gemini key** | Current key 429s on even the free text model — that's why AI tailoring stays capped. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → **"Create API key in a new project"**. Free. Fixes AI tailoring. |
| 2 | **First assisted-apply run** | Resume Studio → pick a job → Step 4 → *Launch assisted apply* → sign in once → review → **you** press Submit. |
| 3 | **Hunter.io key** (optional) | hunter.io free tier (~25/mo) → real verified recruiter contacts. |

## ❌ Deliberately not built

| Item | Why |
|------|-----|
| Auto-submit (LinkedIn Easy Apply etc.) | Permanent-ban risk on the account he needs most |
| LinkedIn contact scraping | Same ban risk; also performs worse than a hand-sent note |
| Paid AI models | He said free-only |
| Resume upload to Dice / HireITPeople | He said don't expose the resume — never happened |

## Session — 2026-07-12

| # | Ask | Status |
|---|-----|--------|
| G1 | Clean the repo — stop name-dropping other brands/projects everywhere | ✅ Brand names out of `theme.py`, `config.toml`, `app.py`, README prose. Dead `tools/gen_logo_ai.py` deleted. |
| G2 | Move "inspired by" to one small section at the end, not the front page | ✅ 7-row prior-art table → one `<sub>` Credits line at the very bottom of README. |
| G3 | Logo: make the bow small, or switch to a smiley | ✅ **Both** — the smile IS the bow, string drawn back on an orange arrow (`make_logo.py 7`). Reads as a face at 32px, a loaded bow at 512px. |
| G4 | Bank of America "company website" opened the full job list, not the job | ✅ Root cause: BoA reads `search=` as a **mode** (`getAllJobs`), not a query — so `?search={title}` renders everything. Added a real `_bofa` adapter (pulls all ~1,800 live jobs, matches to the exact `job-detail` URL). |
| G5 | …and get me the right link for *that* VP AML role | ⚠️ **The posting is closed.** Not in BoA's 1,797 live jobs; Jooble's own URL says `jobAge=92`. Web search finds only aggregator echoes. Nothing to link to. |

**New capability that fell out of G4/G5:** for employers whose portal returns their *whole* live feed, absence now proves closure — those jobs are auto-retired to `stale` with a reason, instead of being handed a link that goes nowhere. 4 dead BoA jobs retired on the first run.

| # | Ask | Status |
|---|-----|--------|
| H1 | Queue must not scroll horizontally | ✅ 14 cols → **8**. Page h-scroll measured at **0px** in the live browser. |
| H2 | Important columns first; source/posted-date aren't important | ✅ New order: 🔥 · Fit · **Apply** · Status · Title · Company · **Skills** · Location. Source, posted/pulled dates, industry and notes moved into the row dialog. |
| H3 | Apply in the first few columns | ✅ Column **3**. |
| H4 | A column showing the job's keywords (SAS, Credit Risk, AML…) | ✅ New **Skills** column, from new `src/tags.py` (21 tags: domain → technique → tool). |
| H5 | Filter by those keywords | ✅ **Skills** multiselect in the top bar (not buried in the popover) + "Match ALL" toggle in Filters. |

**Judgement calls made (say if you disagree):**
- **Salary cut from the grid** — only **6 of 1,395** postings (0.4%) list one, so it was a blank column charging full width. It survives as a chip in the row dialog.
- **41% of jobs get no Skills tags** — 576 of them have *no description at all* and a generic title ("Data Analytics Senior Analyst"). Only **3** are genuine tagger misses. 1,257 of 1,395 jobs ship no description, so most tags come from the title alone.

| # | Ask | Status |
|---|-----|--------|
| I1 | Same column positions in every tab | ✅ One `JOB_COLS` + `job_columns()` in app.py. Today, Jobs, Applied and the Resume Studio picker all use it. Tabs may APPEND (Applied adds "Applied on") but never reorder. |
| I2 | Resume Studio option alongside Apply, in Jobs + Today | ✅ New **📄** column in every queue: tick it and the job is queued to Resume Studio, which then opens with that job already selected. Today's cards get a **📄 Tailor** button next to Apply. |
| I3 | "You only fixed BoA — Truist has the same issue. Fix ALL job links." | ✅ Root cause was general, see below. |

### The apply-link bug was never about one bank

An ATS `searchText` is an **AND over every word**. Feeding it the raw job title
means one stray token kills the search:
`"Senior Regulatory Reporting Data Analyst (CCAR Y14)"` → **0 results** at Truist.
Drop the `(CCAR Y14)` → **32 results**. Zero results → the resolver fell back to a
careers landing page. That is the link you kept landing on, and it explains
**690 of 1,391 links (50%)**, not just BoA and Truist.

Fixes, all at the adapter layer so they apply to every employer:
- `_query_variants()` — try the exact title, then de-punctuated, then the first
  N words. Widens the SEARCH; `_match` still has to agree, so it never loosens
  the MATCH.
- **Full board = the authority.** Keyword search can't prove a negative. Every
  portal kind now has a full-board puller (Workday paged, BoA, Greenhouse,
  Lever). Search first (cheap); if it misses, pull the whole board. On it → exact
  link. Not on it → the posting is **closed**, so retire it instead of faking a link.

Two bugs caught only because I checked the numbers instead of trusting them:
- `limit=50` on Workday returns a flat **400**. Its max is 20. Silently looked
  like "no such job".
- Workday reports `total` **only on the first page** (later pages say `total:0`).
  Overwriting it made a **1,050-job board look like 40** — and a truncated board
  would have declared *live* jobs closed. It now refuses to cache, or trust, a
  board it didn't finish pulling.
