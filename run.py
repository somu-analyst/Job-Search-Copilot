#!/usr/bin/env python
"""Orchestrator — run all scrapers, store to data/jobs.db, print a summary.

    python run.py              # scrape boards + workday
    python run.py --boards     # boards only
    python run.py --workday    # workday only

Token-free end to end. Scored/tracked via the Streamlit app (app.py) or by
handing new URLs to career-ops for LLM scoring.
"""
import sys
from src import db, scrape_boards, scrape_workday


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

    after = db.counts(conn)
    conn.close()
    print(f"\nDone. +{total_new} new jobs this run.")
    print(f"  Jobs in DB:      {after['jobs']}  ({after['new']} unreviewed)")
    print(f"  Companies known: {after['companies']}  (+{after['companies']-before['companies']} new)")
    print(f"\nOpen the tracker:  streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
