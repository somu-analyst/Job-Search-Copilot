#!/usr/bin/env python
"""Orchestrator — run all scrapers, store to data/jobs.db, print a summary.

    python run.py              # scrape boards + workday, score, enrich, archive
    python run.py --boards     # boards only
    python run.py --workday    # workday only
    python run.py --sponsors   # also live-lookup H-1B filings for top companies

Token-free end to end. Every job gets a $0 keyword fit-score; optionally hand
top URLs to career-ops for LLM scoring later.
"""
import sys
from src import db, scrape_boards, scrape_workday, score, sponsors


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

    print("Post-processing:")
    score.score_all(conn)
    n_seed = sponsors.enrich_seeds(conn)
    if n_seed:
        print(f"  sponsor seeds applied to {n_seed} companies")
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
