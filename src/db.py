"""SQLite storage for jobs + the growing company directory.

Single file: data/jobs.db. Two tables:
  jobs      — every discovered posting, with a user-editable `status` (the tracker)
  companies — auto-growing directory: every company we ever see, with careers-page
              and Workday-endpoint info accumulated over time.

The frontend (app.py) reads/writes this DB. Nothing here needs an API key.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

STATUSES = ["new", "interested", "applied", "responded",
            "interview", "offer", "rejected", "skip", "stale"]

STALE_DAYS = 21  # unreviewed 'new' jobs older than this are auto-archived


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            url          TEXT PRIMARY KEY,
            title        TEXT,
            company      TEXT,
            location     TEXT,
            source       TEXT,
            is_core      INTEGER DEFAULT 0,
            date_found   TEXT,
            date_posted  TEXT,
            score        REAL,
            status       TEXT DEFAULT 'new',
            notes        TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS companies (
            name          TEXT PRIMARY KEY,
            slug          TEXT,
            first_seen    TEXT,
            last_seen     TEXT,
            job_count     INTEGER DEFAULT 0,
            careers_url   TEXT DEFAULT '',
            workday_url   TEXT DEFAULT '',
            sponsors_h1b  TEXT DEFAULT '',
            notes         TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        """
    )
    # migrations for older DBs
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "date_applied" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN date_applied TEXT DEFAULT ''")
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(companies)")}
    if "industry" not in ccols:
        conn.execute("ALTER TABLE companies ADD COLUMN industry TEXT DEFAULT ''")
    conn.commit()


def enrich_industries(conn) -> int:
    """Tag every directory company with an industry from the seed map."""
    from .sources import industry_for
    rows = conn.execute(
        "SELECT name FROM companies WHERE industry='' OR industry IS NULL").fetchall()
    n = 0
    for (name,) in rows:
        ind = industry_for(name)
        if ind:
            conn.execute("UPDATE companies SET industry=? WHERE name=?", (ind, name))
            n += 1
    conn.commit()
    return n


def upsert_job(conn, *, url, title, company, location, source,
               is_core=False, date_posted="") -> bool:
    """Insert a job if new. Returns True if it was newly added."""
    if not url:
        return False
    cur = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
    if cur.fetchone():
        return False
    conn.execute(
        """INSERT INTO jobs (url, title, company, location, source, is_core,
                             date_found, date_posted, status)
           VALUES (?,?,?,?,?,?,?,?,'new')""",
        (url, title, company, location, source, 1 if is_core else 0,
         today(), date_posted),
    )
    return True


def touch_company(conn, name, *, source="", careers_url="", workday_url="",
                  sponsors_h1b="") -> None:
    """Record/refresh a company in the directory (auto-grows over time)."""
    from .sources import slugify
    if not name or not name.strip():
        return
    name = name.strip()
    row = conn.execute("SELECT job_count FROM companies WHERE name = ?", (name,)).fetchone()
    if row:
        conn.execute(
            """UPDATE companies SET last_seen=?, job_count=job_count+1,
                   careers_url=COALESCE(NULLIF(careers_url,''), ?),
                   workday_url=COALESCE(NULLIF(workday_url,''), ?),
                   sponsors_h1b=COALESCE(NULLIF(sponsors_h1b,''), ?)
               WHERE name=?""",
            (now(), careers_url, workday_url, sponsors_h1b, name),
        )
    else:
        conn.execute(
            """INSERT INTO companies (name, slug, first_seen, last_seen, job_count,
                                      careers_url, workday_url, sponsors_h1b)
               VALUES (?,?,?,?,1,?,?,?)""",
            (name, slugify(name), now(), now(), careers_url, workday_url, sponsors_h1b),
        )


def archive_stale(conn, days=STALE_DAYS) -> int:
    """JobFunnel-style hygiene: 'new' jobs never reviewed within N days → stale.

    Keeps the inbox fresh; stale rows stay queryable under the 'stale' filter."""
    cur = conn.execute(
        """UPDATE jobs SET status='stale'
           WHERE status='new' AND date_found <= date('now', ?)""",
        (f"-{int(days)} days",))
    conn.commit()
    return cur.rowcount


def counts(conn) -> dict:
    j = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    new = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='new'").fetchone()[0]
    return {"jobs": j, "companies": c, "new": new}
