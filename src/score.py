"""Token-free fit scoring (0.0–5.0) — the ai-job-search idea without LLM cost.

Deterministic score from title + company signals:
  +2.0  core-fit title (fraud / credit risk / AML / SAS / CCAR ...)
  +1.0  any positive keyword beyond the first (capped)
  +1.0  seniority match (senior/lead/manager/vp/avp/director/principal)
  +0.5  known H-1B sponsor (strong)   +0.25 moderate
  -1.0  'rare' sponsor
Optional later: overwrite `score` with an LLM judgment (career-ops / OpenRouter).
"""
from __future__ import annotations
from .sources import POSITIVE, CORE
from .sponsors import seed_verdict

SENIOR = ["senior", "sr ", "sr.", "lead", "manager", "vp", "avp",
          "vice president", "director", "principal", "staff", "head"]


def score_title(title: str, company: str) -> float:
    t = (title or "").lower()
    s = 0.0
    hits = sum(1 for p in POSITIVE if p in t)
    if any(c in t for c in CORE):
        s += 2.0
    s += min(hits - 1, 2) * 0.5 if hits > 1 else 0.0
    if any(k in t for k in SENIOR):
        s += 1.0
    v = seed_verdict(company) or ""
    if v.startswith("strong"):
        s += 0.5
    elif v.startswith("moderate"):
        s += 0.25
    elif v.startswith("rare"):
        s -= 1.0
    return round(max(0.0, min(5.0, s)), 2)


def score_all(conn, verbose=True) -> int:
    rows = conn.execute("SELECT rowid, title, company FROM jobs WHERE score IS NULL").fetchall()
    for rowid, title, company in rows:
        conn.execute("UPDATE jobs SET score=? WHERE rowid=?",
                     (score_title(title, company), rowid))
    conn.commit()
    if verbose and rows:
        print(f"  scored {len(rows)} jobs (keyword model, $0)")
    return len(rows)
