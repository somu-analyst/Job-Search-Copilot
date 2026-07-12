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
        CREATE TABLE IF NOT EXISTS resumes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT,      -- YYYY-MM-DD HH:MM  (when this version was made)
            job_url      TEXT,      -- FK-ish -> jobs.url  ('' = generic/base version)
            job_title    TEXT,      -- snapshotted: the JD may vanish from the board
            company      TEXT,
            variant      TEXT,      -- e.g. 'Balanced', 'ATS-max', 'Edited by me'
            summary      TEXT,      -- the tailored Professional Summary
            resume_md    TEXT,      -- full resume markdown as sent
            ats          REAL, recruiter REAL, hiring_manager REAL, overall REAL,
            used_to_apply INTEGER DEFAULT 0,   -- 1 once you actually applied with it
            applied_at   TEXT DEFAULT '',
            notes        TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_res_job      ON resumes(job_url);
        CREATE INDEX IF NOT EXISTS idx_res_applied  ON resumes(used_to_apply);
        """
    )
    # migrations for older DBs
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "date_applied" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN date_applied TEXT DEFAULT ''")
    if "description" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN description TEXT DEFAULT ''")
    if "salary" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN salary TEXT DEFAULT ''")
    if "apply_url" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN apply_url TEXT DEFAULT ''")
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(companies)")}
    if "industry" not in ccols:
        conn.execute("ALTER TABLE companies ADD COLUMN industry TEXT DEFAULT ''")
    if "ats" not in ccols:      # which system the employer applies through
        conn.execute("ALTER TABLE companies ADD COLUMN ats TEXT DEFAULT ''")
    if "ats_ref" not in ccols:  # tenant/slug/portal handle for that ATS
        conn.execute("ALTER TABLE companies ADD COLUMN ats_ref TEXT DEFAULT ''")
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
               is_core=False, date_posted="", description="", salary="") -> bool:
    """Insert a job if new. Returns True if it was newly added.
    salary is FYI only (shown when the posting lists one) — never a filter."""
    if not url:
        return False
    cur = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
    if cur.fetchone():
        return False
    desc = (description or "")[:12000]
    if not salary and desc:
        from .sources import salary_from_text
        salary = salary_from_text(desc)
    conn.execute(
        """INSERT INTO jobs (url, title, company, location, source, is_core,
                             date_found, date_posted, status, description, salary)
           VALUES (?,?,?,?,?,?,?,?,'new',?,?)""",
        (url, title, company, location, source, 1 if is_core else 0,
         today(), date_posted, desc, salary or ""),
    )
    return True


def backfill_salary(conn) -> int:
    """Fill salary (FYI) for existing rows that have a description but no salary."""
    from .sources import salary_from_text
    rows = conn.execute(
        "SELECT url, description FROM jobs "
        "WHERE (salary='' OR salary IS NULL) AND description!=''").fetchall()
    n = 0
    for url, desc in rows:
        s = salary_from_text(desc or "")
        if s:
            conn.execute("UPDATE jobs SET salary=? WHERE url=?", (s, url))
            n += 1
    conn.commit()
    return n


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
