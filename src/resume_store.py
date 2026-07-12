"""Resume archive — every version you generate or edit, kept with its job.

Why: six months from now a recruiter calls about a role you applied to in July.
You need the EXACT resume you sent them, not today's. Job postings also vanish
from boards, so we snapshot the title/company alongside the resume rather than
relying on a join that may dangle.

One row per version. `used_to_apply=1` marks the one you actually sent.
"""
from __future__ import annotations
from datetime import datetime

from . import db


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def save(conn, *, job_url: str, job_title: str, company: str, variant: str,
         summary: str, resume_md: str, scores: dict | None = None,
         notes: str = "") -> int:
    """Archive one resume version. Returns its id."""
    s = scores or {}
    cur = conn.execute(
        """INSERT INTO resumes (created_at, job_url, job_title, company, variant,
                                summary, resume_md, ats, recruiter, hiring_manager,
                                overall, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_now(), job_url or "", job_title or "", company or "", variant,
         summary or "", resume_md or "",
         s.get("ats"), s.get("recruiter"), s.get("hiring_manager"), s.get("overall"),
         notes))
    conn.commit()
    return int(cur.lastrowid)


def mark_applied(conn, resume_id: int) -> None:
    """Flag the version you actually sent, and stamp when."""
    conn.execute("UPDATE resumes SET used_to_apply=1, applied_at=? WHERE id=?",
                 (db.today(), int(resume_id)))
    conn.commit()


def for_job(conn, job_url: str):
    return conn.execute(
        """SELECT id, created_at, variant, summary, resume_md, ats, recruiter,
                  hiring_manager, overall, used_to_apply, applied_at
           FROM resumes WHERE job_url=? ORDER BY id DESC""", (job_url,)).fetchall()


def get(conn, resume_id: int):
    return conn.execute("SELECT * FROM resumes WHERE id=?", (int(resume_id),)).fetchone()


def history(conn, applied_only: bool = False, limit: int = 500):
    """The archive view: what you sent, to whom, when, with what scores."""
    q = """SELECT id, created_at, applied_at, company, job_title, variant,
                  overall, ats, recruiter, hiring_manager, used_to_apply, job_url
           FROM resumes"""
    if applied_only:
        q += " WHERE used_to_apply=1"
    q += f" ORDER BY id DESC LIMIT {int(limit)}"
    return conn.execute(q).fetchall()
