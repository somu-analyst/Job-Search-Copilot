#!/usr/bin/env python
"""Pull freshly-scanned jobs from the Oracle VM down into the local DB, and keep
your own "I applied" marks the same on both sides.

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

THE ONE EXCEPTION TO "NEW ROWS ONLY": your applied mark (user 2026-10-07)
    `jobs.applied_by_me` is the only field that travels BOTH ways for a job both
    sides already have, because you can tick it in either place and both places
    must then agree. The newer `applied_marked_at` wins, and it is written in
    explicit UTC for exactly that comparison -- the laptop's clock is New York
    time and the VM's is UTC, so a local-time stamp from one is not comparable
    with one from the other. Everything else (status, notes, scores) still stays
    local to whichever side made it.

Usage:
    python sync_from_cloud.py               # merge new jobs/companies in
    python sync_from_cloud.py --dry-run      # show counts, write nothing
"""
from __future__ import annotations
import json
import subprocess
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from src import db

VM_HOST = "ubuntu@150.136.41.250"
VM_KEY = str(Path.home() / "oci-nyse.key")
REMOTE_DB = "/home/ubuntu/job-search-copilot/data/jobs.db"
REMOTE_TMP = "/tmp/jobscout_sync_backup.db"
REMOTE_MARK_PATH = "/tmp/jobscout_mark_apply.py"
SSH = ["ssh", "-i", VM_KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=25"]
LOCAL_TMP = db.DB_PATH.parent / ".cloud_sync_tmp.db"   # data/*.db is already gitignored

JOB_COLS = ("url", "title", "company", "location", "source", "is_core",
            "date_found", "date_posted", "score", "status", "notes",
            "date_applied", "description", "salary", "apply_url", "tags", "apply_kind",
            "applied_by_me", "applied_marked_at")
COMPANY_COLS = ("name", "slug", "first_seen", "last_seen", "job_count",
                "careers_url", "workday_url", "sponsors_h1b", "notes",
                "industry", "ats", "ats_ref")


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# Applies the marks this side decided are newer, on the VM. Kept here in full and
# run from a file (never assembled into an ssh command line), with bound
# parameters, and it adds the columns first so an older cloud DB still takes it.
_REMOTE_MARK_APPLY = r'''
import json, sqlite3, sys
rows = json.load(sys.stdin)
c = sqlite3.connect("''' + REMOTE_DB + r'''", timeout=30)
cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
if "applied_by_me" not in cols:
    c.execute("ALTER TABLE jobs ADD COLUMN applied_by_me INTEGER DEFAULT 0")
if "applied_marked_at" not in cols:
    c.execute("ALTER TABLE jobs ADD COLUMN applied_marked_at TEXT DEFAULT ''")
for r in rows:
    c.execute("UPDATE jobs SET applied_by_me=?, applied_marked_at=? WHERE url=?",
              (r["applied_by_me"], r["applied_marked_at"], r["url"]))
c.commit()
c.close()
print(f"applied {len(rows)} mark(s)")
'''


def _instant(stamp):
    """applied_marked_at -> comparable UTC instant; missing/unreadable = the epoch."""
    s = str(stamp or "").strip()
    if not s:
        return _EPOCH
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return _EPOCH
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


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


def trigger_remote_scan(timeout: int = 8) -> bool:
    """Fire-and-forget: starts the cloud scan service and returns immediately
    -- a full scan takes many minutes, so the caller (the sidebar button)
    should NOT block waiting for it. Returns False if the VM isn't reachable
    within `timeout`s, so the caller can fall back to a local scan instead."""
    try:
        subprocess.run(
            ["ssh", "-i", VM_KEY, "-o", "StrictHostKeyChecking=no",
             "-o", f"ConnectTimeout={timeout}", VM_HOST,
             "sudo systemctl start jobscout-scan.service"],
            check=True, timeout=timeout + 5,
        )
        return True
    except Exception:
        return False


def _sync_applied_marks(conn, cloud_jcols, dry_run: bool = False) -> tuple[int, int]:
    """Reconcile YOUR applied marks both ways for jobs both sides already have.

    Newer applied_marked_at wins. A side that has never marked the job (blank
    stamp) loses to one that has, so ticking it anywhere always lands -- and two
    equal stamps mean the row is already agreed, which keeps repeat runs silent.
    Returns (pulled, pushed).
    """
    if "applied_by_me" not in cloud_jcols:
        # An older cloud DB HAS the jobs, it just has nowhere to record a mark yet.
        # Treating that as "no jobs" would silently push nothing (caught in test).
        print("[sync] cloud DB has no applied mark yet -- pushing local marks only")
        cloud_rows = {r[0]: (0, "") for r in conn.execute("SELECT url FROM cloud.jobs")}
    else:
        cloud_rows = {r[0]: (int(r[1] or 0), r[2] or "") for r in conn.execute(
            "SELECT url, applied_by_me, applied_marked_at FROM cloud.jobs")}
    local_rows = {r[0]: (int(r[1] or 0), r[2] or "") for r in conn.execute(
        "SELECT url, COALESCE(applied_by_me,0), COALESCE(applied_marked_at,'') FROM jobs")}

    pull, push = [], []
    for url, (l_flag, l_at) in local_rows.items():
        if url not in cloud_rows:
            continue                                   # new local job: nothing to agree with yet
        c_flag, c_at = cloud_rows[url]
        if (l_flag, l_at) == (c_flag, c_at):
            continue
        if _instant(c_at) > _instant(l_at):
            pull.append((c_flag, c_at, url))
        elif _instant(l_at) > _instant(c_at):
            push.append({"url": url, "applied_by_me": l_flag, "applied_marked_at": l_at})

    if not pull and not push:
        print("[sync] applied marks: already in agreement")
        return 0, 0
    print(f"[sync] applied marks: {len(pull)} to pull down, {len(push)} to push up"
          + (" (dry run)" if dry_run else ""))
    if dry_run:
        return len(pull), len(push)

    if pull:
        conn.executemany(
            "UPDATE jobs SET applied_by_me=?, applied_marked_at=? WHERE url=?", pull)
        conn.commit()
    if push:
        w = subprocess.run(SSH + [VM_HOST, f"cat > {REMOTE_MARK_PATH}"],
                           input=_REMOTE_MARK_APPLY, capture_output=True, text=True,
                           timeout=30)
        if w.returncode != 0:
            print(f"[sync] could not stage the remote mark script: "
                  f"{(w.stderr or w.stdout)[:200]} -- local marks stay unpushed")
            return len(pull), 0
        r = subprocess.run(SSH + [VM_HOST, "python3", REMOTE_MARK_PATH],
                           input=json.dumps(push), capture_output=True, text=True,
                           timeout=60)
        if r.returncode != 0:
            print(f"[sync] push failed: {(r.stderr or r.stdout)[:200]}")
            return len(pull), 0
        print(f"[sync] {r.stdout.strip()}")
    return len(pull), len(push)


def merge(dry_run: bool = False) -> None:
    """Raises RuntimeError on an unreachable VM -- NOT sys.exit(). This is
    called both from the CLI (__main__ below, where sys.exit is fine) and
    from the Streamlit app's sidebar button, where sys.exit(1) would raise
    SystemExit and take the whole running server down, not just show an
    error in the UI (caught live before it shipped)."""
    if not _fetch_remote_snapshot():
        raise RuntimeError("Could not reach the cloud VM")

    conn = db.connect()
    db.init(conn)   # make sure the local schema is current before attaching
    conn.execute("ATTACH DATABASE ? AS cloud", (str(LOCAL_TMP),))

    # A cloud DB that predates a column would make the whole SELECT fail, so only
    # ever copy columns BOTH sides actually have.
    local_jcols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    cloud_jcols = {r[1] for r in conn.execute("PRAGMA cloud.table_info(jobs)")}
    jcols = ", ".join(c for c in JOB_COLS if c in local_jcols and c in cloud_jcols)
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
        total = db.counts(conn)["jobs"]
        db.record_scan("cloud sync", new_jobs, total)
        print(f"[sync] merged. Local DB now has {total} jobs.")
    else:
        print("[sync] --dry-run: nothing written")

    _sync_applied_marks(conn, cloud_jcols, dry_run)

    conn.execute("DETACH DATABASE cloud")
    conn.close()
    LOCAL_TMP.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        merge(dry_run="--dry-run" in sys.argv)
    except RuntimeError as e:
        print(f"[sync] {e} -- skipping this run")
        sys.exit(1)
