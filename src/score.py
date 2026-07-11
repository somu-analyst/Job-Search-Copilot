"""Token-free fit scoring on a 1–10 scale + Must-Apply flag.

Deterministic score from title + company signals (max realistic = 10):
  +4.0  core-fit title (fraud / credit risk / AML / SAS / CCAR ...)
  +1.0  per extra positive keyword beyond the first (capped at +2)
  +2.0  seniority match (senior/lead/manager/vp/avp/director/principal)
  +1.5  known strong H-1B sponsor    +0.75 moderate    -3.0 rare
  +0.5  baseline (any job that passed the title filter has some fit)

MUST_APPLY_AT — jobs scoring >= this are flagged 🔥 in the app.
Optional later: overwrite `score` with an LLM judgment (career-ops / OpenRouter).
"""
from __future__ import annotations
from .sources import POSITIVE, CORE
from .sponsors import seed_verdict

MUST_APPLY_AT = 8.0

SENIOR = ["senior", "sr ", "sr.", "lead", "manager", "vp", "avp",
          "vice president", "director", "principal", "staff", "head"]


def score_title(title: str, company: str) -> float:
    t = (title or "").lower()
    s = 0.5
    hits = sum(1 for p in POSITIVE if p in t)
    if any(c in t for c in CORE):
        s += 4.0
    if hits > 1:
        s += min(hits - 1, 2) * 1.0
    if any(k in t for k in SENIOR):
        s += 2.0
    v = seed_verdict(company) or ""
    if v.startswith("strong"):
        s += 1.5
    elif v.startswith("moderate"):
        s += 0.75
    elif v.startswith("rare"):
        s -= 3.0
    return round(max(1.0, min(10.0, s)), 1)


def score_all(conn, verbose=True, rescore=False) -> int:
    where = "" if rescore else "WHERE score IS NULL"
    rows = conn.execute(f"SELECT rowid, title, company FROM jobs {where}").fetchall()
    for rowid, title, company in rows:
        conn.execute("UPDATE jobs SET score=? WHERE rowid=?",
                     (score_title(title, company), rowid))
    conn.commit()
    if verbose and rows:
        print(f"  scored {len(rows)} jobs (1-10 keyword model, $0)")
    return len(rows)
