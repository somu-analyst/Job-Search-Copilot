"""Check an apply URL actually points at a live posting — and log the verdict.

The resolver's job (src/direct_apply.py) is to GUESS the best apply URL. This
module's job is to CHECK that guess before it's shown to you, and to keep an
audit trail so a wrong link is visible instead of silent — that was the whole
complaint: "check if the url is right or wrong, keep a logger."

Three verdicts:
  exact  — reachable AND looks like ONE specific job posting  → trust it
  weak   — reachable but a careers/search landing page         → usable, not ideal
  dead   — 404 / error / redirected onto a reposter or homepage → do not use

Nothing here scrapes anything private: it fetches the same public pages your
browser would, just to read the status and the shape of the URL you'd land on.
"""
from __future__ import annotations
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
TIMEOUT = 12
AUDIT = Path(__file__).resolve().parent.parent / "data" / "apply_audit.csv"

# Reposters — landing here means the resolver failed, whatever the status code.
REPOSTERS = ("lensa.com", "jooble.org", "talentify.io", "jobs2careers.com",
             "simplyhired.com", "ziprecruiter.com", "glassdoor.com", "adzuna",
             "jobcase.com", "myjobhelper", "whatjobs", "jobrapido", "neuvoo",
             "trovit", "jobg8", "startpage.com", "duckduckgo.com", "google.com")

# URL shapes that denote ONE posting rather than a list. Ordered widest-first;
# any hit means "this is a specific job", which is what we want to confirm.
_POSTING_PATTERNS = re.compile(
    r"/job[-/]|/jobs/\d|job-detail|jobdetail|/postings?/|/requisition|"
    r"/vacanc|/opening|/careers?/\d|[?&](jobid|reqid|req_id|posting_id|gh_jid)=|"
    r"/\d{6,}(?:/|$|\?)", re.I)

# Paths that scream "landing / search / list", never a single job.
_LANDING_PATTERNS = re.compile(
    r"/search|search-results|/results|/jobs/?$|/careers/?$|/en-us/?$|"
    r"job-search|/browse|keyword=|/home/?$|/$", re.I)


def looks_like_posting(url: str) -> bool:
    """URL-only heuristic — does this path name a single job?"""
    u = (url or "").lower()
    if _POSTING_PATTERNS.search(u):
        return True
    return False


def is_reposter(url: str) -> bool:
    d = (urlparse(url or "").netloc or "").lower()
    return any(r in d for r in REPOSTERS)


def classify(url: str, *, fetch: bool = True) -> dict:
    """Return {verdict, http, final_url, reason} for one apply URL.

    The verdict drives one decision: should we RETIRE the job? Only "dead" does,
    and "dead" is reserved for a link that WAS a specific posting and no longer
    resolves — i.e. the posting closed. Everything short of that is "weak": the
    job may well be live, we just don't have its exact page. Retiring a live job
    over a weak link is the worst outcome, so the bar for "dead" is deliberately
    high (this is why a plain search/reposter fallback is weak, never dead).

    `fetch=False` classifies on URL shape alone (no network) — a fast first pass.
    """
    if not url:
        return {"verdict": "weak", "http": 0, "final_url": "", "reason": "no link"}

    posting_shaped = looks_like_posting(url)

    # A search-engine or reposter fallback link. It's a weak link, NOT evidence
    # the job is gone — so it must never retire the job. We flag it weak so the
    # UI can offer to search for the real posting instead.
    if is_reposter(url):
        return {"verdict": "weak", "http": None, "final_url": url,
                "reason": "search/reposter fallback — no exact link"}

    if not fetch:
        return {"verdict": "exact" if posting_shaped else "weak",
                "http": None, "final_url": url, "reason": "shape only"}

    try:
        # HEAD first (cheap); some ATSs reject HEAD, so fall back to a ranged GET.
        r = requests.head(url, headers=HDR, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400 or r.status_code == 405:
            r = requests.get(url, headers=HDR, timeout=TIMEOUT, allow_redirects=True,
                             stream=True)
            r.close()
    except requests.RequestException as e:
        # A network error (timeout, SSL, reset) is usually TRANSIENT — a slow
        # Workday, an anti-bot rule, a flaky moment. It is NOT proof the posting
        # closed, so it never retires the job; worst case it stays weak and gets
        # re-checked next run. Only a definitive HTTP 404/410 counts as closed.
        return {"verdict": "weak", "http": 0, "final_url": url,
                "reason": f"unreachable ({type(e).__name__})"}

    final = r.url or url
    http = r.status_code
    if http in (404, 410):
        # Gone for good. Retire only if it was a real posting URL; a 404 on a
        # careers landing page is just a bad guess, not a closed job.
        v = "dead" if posting_shaped else "weak"
        return {"verdict": v, "http": http, "final_url": final,
                "reason": f"HTTP {http}"}
    if http >= 400:
        # 403/429/5xx — blocked or server hiccup, treat as uncertain, keep the job.
        return {"verdict": "weak", "http": http, "final_url": final,
                "reason": f"HTTP {http} (not retired — may be transient)"}
    if is_reposter(final):
        # Only a posting that BOUNCES to a reposter is dead; a non-posting that
        # happens to sit on one is just a weak link.
        v = "dead" if posting_shaped else "weak"
        return {"verdict": v, "http": http, "final_url": final,
                "reason": "redirected to a reposter"}
    # A specific posting that redirects onto a bare careers/search page = the
    # posting is gone and the site bounced us to its job list. Closed.
    if posting_shaped and _LANDING_PATTERNS.search(urlparse(final).path or "/") \
            and not looks_like_posting(final):
        return {"verdict": "dead", "http": http, "final_url": final,
                "reason": "posting redirected to a landing page (closed)"}
    verdict = "exact" if looks_like_posting(final) else "weak"
    return {"verdict": verdict, "http": http, "final_url": final, "reason": "reached"}


def _log_rows(rows: list[dict]) -> None:
    """Append audit rows to data/apply_audit.csv (created with a header once)."""
    AUDIT.parent.mkdir(exist_ok=True)
    new = not AUDIT.exists()
    with AUDIT.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "company", "title", "apply_url", "verdict",
                        "http", "final_url", "reason"])
        for r in rows:
            w.writerow([r["ts"], r["company"], r["title"], r["apply_url"],
                        r["verdict"], r["http"], r["final_url"], r["reason"]])


def audit_all(conn, limit: int | None = None, workers: int = 12,
              verbose: bool = True) -> dict:
    """Validate every stored apply_url, log each verdict, and flag the dead ones.

    Dead links are NOT silently dropped — the job is marked so you can see the
    posting closed, and the audit CSV records why. This is the backtest across
    the whole board the user asked for.
    """
    q = ("SELECT rowid, company, title, COALESCE(apply_url,'') "
         "FROM jobs WHERE COALESCE(apply_url,'') != '' AND status != 'stale'")
    if limit:
        q += f" LIMIT {int(limit)}"
    jobs = conn.execute(q).fetchall()
    ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    stats = {"exact": 0, "weak": 0, "dead": 0}
    rows: list[dict] = []

    def work(job):
        rowid, company, title, url = job
        res = classify(url, fetch=True)
        return rowid, company, title, url, res

    dead: list[tuple[str, int]] = []          # (reason, rowid) — written in one batch
    kinds: list[tuple[str, int]] = []         # (verdict, rowid) for the app badge
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rowid, company, title, url, res = fut.result()
            stats[res["verdict"]] += 1
            rows.append({"ts": ts, "company": company, "title": title,
                         "apply_url": url, **res})
            kinds.append((res["verdict"], rowid))
            if res["verdict"] == "dead":
                dead.append((f"Apply link failed validation: {res['reason']}.", rowid))
            if verbose and i % 100 == 0:
                print(f"  validated {i}/{len(jobs)} ...")

    # Batch the DB writes AFTER all network work is done, so the write lock is
    # held for a moment instead of across minutes of fetching — that long-held
    # lock is what collided with the running app ("database is locked").
    for verdict, rowid in kinds:
        conn.execute("UPDATE jobs SET apply_kind=? WHERE rowid=?", (verdict, rowid))
    for reason, rowid in dead:
        conn.execute(
            "UPDATE jobs SET status='stale', notes=? WHERE rowid=? AND status='new'",
            (reason, rowid))
    conn.commit()
    _log_rows(rows)
    if verbose:
        print(f"  audit: {stats['exact']} exact | {stats['weak']} weak | "
              f"{stats['dead']} dead (retired) -> logged to {AUDIT.name}")
    return stats
