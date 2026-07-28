#!/usr/bin/env python
"""Orchestrator — run all scrapers, store to data/jobs.db, print a summary.

    python run.py              # scrape boards + workday, score, enrich, archive
    python run.py --boards     # boards only
    python run.py --workday    # workday only
    python run.py --gmail      # also pull job-alert digest emails (see src/scrape_gmail.py)
    python run.py --sponsors   # also live-lookup H-1B filings for top companies

Token-free end to end. Every job gets a $0 keyword fit-score; optionally hand
top URLs to career-ops for LLM scoring later.
"""
import sys
from src import (db, scrape_boards, scrape_workday, scrape_apis, scrape_gmail, score,
                 sponsors, direct_apply, tags, link_check, web_search)


def main() -> int:
    args = set(sys.argv[1:])
    only_boards = "--boards" in args
    only_wd = "--workday" in args

    conn = db.connect()
    db.init(conn)
    before = db.counts(conn)

    print(f"[{db.now()}] bfsi-job-hunter — scanning...")
    total_new = 0
    if not only_wd:
        print("Boards (Indeed / LinkedIn / Google):")
        total_new += scrape_boards.run(conn)
    if not only_boards:
        print("Workday JSON API (banks):")
        total_new += scrape_workday.run(conn)
    if not (only_boards or only_wd):
        print("Aggregator APIs (Adzuna / Jooble):")
        total_new += scrape_apis.run(conn)
    if "--gmail" in args:   # opt-in: needs one-time Google OAuth setup, see src/scrape_gmail.py
        print("Gmail (job-alert digests):")
        total_new += scrape_gmail.run(conn)

    print("Post-processing:")
    score.score_all(conn)
    tags.tag_all(conn)          # Skills column + Skills filter in the app
    n_seed = sponsors.enrich_seeds(conn)
    if n_seed:
        print(f"  sponsor seeds applied to {n_seed} companies")
    n_ind = db.enrich_industries(conn)
    if n_ind:
        print(f"  industry tagged for {n_ind} companies")
    db.backfill_salary(conn)
    direct_apply.resolve_all(conn)   # every job gets a real employer apply link
    if "--novalidate" not in args:   # verify each link resolves BEFORE you click it
        link_check.audit_all(conn)
    if "--websearch" in args:        # upgrade weak links via web search (slow; opt-in)
        web_search.upgrade_weak_links(conn)
    if "--sponsors" in args:
        sponsors.enrich_live(conn)
    n_stale = db.archive_stale(conn)
    if n_stale:
        print(f"  archived {n_stale} stale unreviewed jobs (> {db.STALE_DAYS} days)")

    after = db.counts(conn)
    conn.close()
    print(f"\nDone. +{total_new} new jobs this run.")
    print(f"  Jobs in DB:      {after['jobs']}  ({after['new']} unreviewed)")
    print(f"  Companies known: {after['companies']}  (+{after['companies']-before['companies']} new)")
    print(f"\nOpen the tracker:  streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
