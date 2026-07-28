# Contributing

Thanks for taking a look. This started as a personal tool and is MIT-licensed
specifically so other people can fork it, bend it to their own job search, or
send back improvements.

## Running it locally

```bash
pip install -r requirements.txt
cp config/profile.example.yml config/profile.yml   # your keywords + API keys
cp resume/cv.example.md       resume/cv.md         # your resume, in markdown

python run.py            # scrape → score → resolve apply links → data/jobs.db
streamlit run app.py     # open the app
```

No account/API key is required to try it — see the **Live demo** and **Screenshots**
sections in the README, which run on the committed `config/profile.demo.yml` +
`resume/cv.demo.md` + `data/demo_jobs.db` (a fictional candidate against real, public
job postings). If you skip your own `config/profile.yml`/`resume/cv.md`, the app falls
back to those same demo files automatically — so you can poke at the UI immediately.

## Ground rules

- **`config/profile.yml`, `resume/cv.md`, `data/*.db` are gitignored on purpose.** They
  hold a real person's keywords, resume, and job pipeline. Never force-add or PR a
  change that would commit real personal data. If you're adding a new demo/fallback
  path, sanitize it the way `data/demo_jobs.db` is sanitized (see `src/db.py`'s
  `display_db_path()` for the pattern) — public postings only, no resume archive, no
  personal status/notes fields.
- **No paid AI models.** `src/ai.py` intentionally only calls free-tier
  OpenRouter/Gemini models and degrades to deterministic scoring when they're capped —
  keep it that way, don't wire in a paid API by default.
- **No auto-submit, no LinkedIn scraping.** Both are deliberately not built — see
  "On the things this deliberately does *not* do" in the README for why. PRs that add
  either will be declined regardless of how well-built they are.
- **Direct apply links only.** `src/direct_apply.py` resolves the employer's own
  application page — new ATS adapters (Workday/Greenhouse/Lever/SmartRecruiters/
  Radancy-style) are welcome; reposter/aggregator links are not the goal.

## Where to start

Check the **Roadmap** section in README.md, or look for issues tagged
`good first issue`. Adding a new employer to the Workday tenant list
(`src/scrape_workday.py`) or a new ATS adapter to `src/direct_apply.py` are the
easiest high-value contributions — both are additive (a new row/function), don't touch
shared logic, and are easy to verify (the module has a `--probe` CLI for exactly this).

## Before opening a PR

- Run `python run.py --workday` (or whichever lane you touched) against real data and
  confirm it doesn't error.
- If you touched `app.py`/`ui/`, actually open the Streamlit app and click through the
  screen you changed — this is a Streamlit app, so nothing here is caught by a type
  checker alone.
- Keep the diff scoped to the thing you're fixing/adding. This repo favors small,
  reviewable PRs over drive-by refactors.

## Reporting a bug / suggesting an idea

Open an issue. For bugs, include what you expected vs. what happened and, if it's a
scraping/apply-link issue, which employer/job URL triggered it (redacted if it's from
your private `data/jobs.db`).
