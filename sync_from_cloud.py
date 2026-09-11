#!/usr/bin/env python
"""Pull freshly-scanned jobs from the Oracle VM down into the local DB.

The cloud VM (deploy/) now runs the daily scan (jobscout-scan.timer, 10:00 UTC).
This script is what the LOCAL scheduled task runs instead of its own scan --
running both would double-spend the free-tier API quotas and let the two
DBs drift apart. This is a MERGE, never an overwrite: any job/company URL
already known locally is left untouched, so status edits you made locally
("applied", "interested", notes, ...) are never clobbered by a sync. Only
genuinely new rows come across.

Uses SQLite's own online backup API on the remote end (`.backup`), not a
raw file copy, so a sync is safe even while the cloud dashboard has the DB
open.

Usage:
    python sync_from_cloud.py               # merge new jobs/companies in
    python sync_from_cloud.py --dry-run      # show counts, write nothing
"""
from __future__ import annotations
import subprocess
import sqlite3
import sys
from pathlib import Path

from src import db

VM_HOST = "ubuntu@150.136.41.250"
VM_KEY = str(Path.home() / "oci-nyse.key")
REMOTE_DB = "/home/ubuntu/job-search-copilot/data/jobs.db"
REMOTE_TMP = "/tmp/jobscout_sync_backup.db"
LOCAL_TMP = db.DB_PATH.parent / ".cloud_sync_tmp.db"   # data/*.db is already gitignored

JOB_COLS = ("url", "title", "company", "location", "source", "is_core",
            "date_found", "date_posted", "score", "status", "notes",
            "date_applied", "description", "salary", "apply_url", "tags", "apply_kind")
COMPANY_COLS = ("name", "slug", "first_seen", "last_seen", "job_count",
                "careers_url", "workday_url", "sponsors_h1b", "notes",
                "industry", "ats", "ats_ref")


def _ssh(cmd: str) -> None:
    subprocess.run(
        ["ssh", "-i", VM_KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=25",
         VM_HOST, cmd],
        check=True, timeout=60,
    )


def _fetch_remote_snapshot() -> bool:
    """Online-backup the remote DB to a temp file and scp it down. False if unreachable."""
    try:
        _ssh(f"sqlite3 {REMOTE_DB} \".backup {REMOTE_TMP}\"")
        subprocess.run(
            ["scp", "-i", VM_KEY, "-o", "StrictHostKeyChecking=no",
             f"{VM_HOST}:{REMOTE_TMP}", str(LOCAL_TMP)],
            check=True, timeout=60,
        )
        _ssh(f"rm -f {REMOTE_TMP}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[sync] could not reach the VM ({e}) -- skipping this run")
        return False
    except subprocess.TimeoutExpired:
        print("[sync] VM connection timed out -- skipping this run")
        return False


def merge(dry_run: bool = False) -> None:
    if not _fetch_remote_snapshot():
        sys.exit(1)

    conn = db.connect()
    db.init(conn)   # make sure the local schema is current before attaching
    conn.execute("ATTACH DATABASE ? AS cloud", (str(LOCAL_TMP),))

    jcols = ", ".join(JOB_COLS)
    ccols = ", ".join(COMPANY_COLS)

    new_jobs = conn.execute(
        f"SELECT COUNT(*) FROM cloud.jobs WHERE url NOT IN (SELECT url FROM jobs)"
    ).fetchone()[0]
    new_companies = conn.execute(
        f"SELECT COUNT(*) FROM cloud.companies WHERE name NOT IN (SELECT name FROM companies)"
    ).fetchone()[0]

    print(f"[sync] {new_jobs} new job(s), {new_companies} new compan(y/ies) on the cloud side")

    if not dry_run:
        conn.execute(
            f"INSERT INTO jobs ({jcols}) "
            f"SELECT {jcols} FROM cloud.jobs WHERE url NOT IN (SELECT url FROM jobs)"
        )
        conn.execute(
            f"INSERT INTO companies ({ccols}) "
            f"SELECT {ccols} FROM cloud.companies WHERE name NOT IN (SELECT name FROM companies)"
        )
        conn.commit()
        print(f"[sync] merged. Local DB now has {db.counts(conn)['jobs']} jobs.")
    else:
        print("[sync] --dry-run: nothing written")

    conn.execute("DETACH DATABASE cloud")
    conn.close()
    LOCAL_TMP.unlink(missing_ok=True)


if __name__ == "__main__":
    merge(dry_run="--dry-run" in sys.argv)
