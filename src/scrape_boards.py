"""Multi-board scraper via python-jobspy (Indeed, LinkedIn, Google Jobs).

Token-free. For each posting it also records the company into the directory,
so over time you accumulate every BFSI employer that has ever posted a match —
the seed for auto-discovering their careers pages later.

Blocked sites (kept out): ZipRecruiter (403), Glassdoor (400). If you add a
proxy in config/profile.yml (scrape.proxies), those can be re-enabled — JobSpy
round-robins proxies to dodge IP blocks.
"""
from __future__ import annotations
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from . import db
from .sources import QUERIES, title_ok, is_core

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"


def _cfg():
    if yaml and _CFG.exists():
        try:
            return yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def run(conn, *, hours_old=48, results_per_query=25, verbose=True) -> int:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("  [skip] python-jobspy not installed — pip install python-jobspy")
        return 0

    cfg = _cfg().get("scrape", {})
    sites = cfg.get("board_sites", ["indeed", "linkedin", "google"])
    proxies = cfg.get("proxies") or None
    location = _cfg().get("location", {}).get("search", "United States")

    added = 0
    for query in QUERIES:
        for site in sites:
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=query,
                    google_search_term=f"{query} jobs in United States since yesterday",
                    location=location,
                    results_wanted=results_per_query,
                    hours_old=hours_old,
                    country_indeed="USA",
                    proxies=proxies,
                    verbose=0,
                )
            except Exception as e:
                if verbose:
                    print(f"  [warn] {site}/'{query}': {type(e).__name__}")
                continue
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                url = str(r.get("job_url") or "").strip()
                title = str(r.get("title") or "")
                company = str(r.get("company") or "")
                loc = str(r.get("location") or "")
                if not url or not title_ok(title):
                    continue
                core = is_core(title)
                if db.upsert_job(conn, url=url, title=title, company=company,
                                 location=loc, source=site, is_core=core,
                                 date_posted=str(r.get("date_posted") or "")):
                    added += 1
                db.touch_company(conn, company, source=site)
    conn.commit()
    if verbose:
        print(f"  boards: +{added} new jobs")
    return added
