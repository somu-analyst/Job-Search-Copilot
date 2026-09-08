"""Official aggregator APIs — Adzuna + Jooble + JSearch (free keys, no scraping fragility).

These are true consolidators: they aggregate thousands of boards and company
sites and serve them over stable JSON APIs — no bot-blocking, no HTML breakage.

Keys (all free tiers) go in config/profile.yml:
    api_keys:
      adzuna_app_id:  "..."     # https://developer.adzuna.com  (instant signup)
      adzuna_app_key: "..."
      jooble_key:     "..."     # https://jooble.org/api/about  (emailed key)
      jsearch_key:    "..."     # RapidAPI key, https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

Each source is skipped silently when its key is absent.
"""
from __future__ import annotations
import datetime as _dt
import requests
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from . import db
from .sources import QUERIES, title_ok, is_core, is_us_location, fmt_salary

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
_HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _cfg() -> dict:
    if yaml and _CFG.exists():
        try:
            return yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _keys() -> dict:
    return _cfg().get("api_keys", {}) or {}


def _adzuna(conn, app_id, app_key, verbose=True) -> int:
    added = 0
    for query in QUERIES:
        try:
            r = requests.get(
                "https://api.adzuna.com/v1/api/jobs/us/search/1",
                params={"app_id": app_id, "app_key": app_key, "what": query,
                        "results_per_page": 30, "max_days_old": 3,
                        "sort_by": "date", "content-type": "application/json"},
                headers=_HDR, timeout=20)
            if r.status_code != 200:
                continue
            for j in r.json().get("results", []):
                title = j.get("title", "")
                url = j.get("redirect_url", "")
                loc = ", ".join((j.get("location", {}) or {}).get("area", [])[-2:])
                comp = (j.get("company", {}) or {}).get("display_name", "")
                if not url or not title_ok(title) or not is_us_location(loc or "US"):
                    continue
                if db.upsert_job(conn, url=url, title=title, company=comp,
                                 location=loc, source="adzuna", is_core=is_core(title),
                                 date_posted=(j.get("created", "") or "")[:10],
                                 description=j.get("description", ""),
                                 salary=fmt_salary(j.get("salary_min"), j.get("salary_max"))):
                    added += 1
                db.touch_company(conn, comp, source="adzuna")
        except Exception as e:
            if verbose:
                print(f"  [warn] adzuna/'{query}': {type(e).__name__}")
    return added


def _jooble(conn, key, verbose=True) -> int:
    added = 0
    # Jooble's free key has a ~500-request default cap — spend it on the
    # 8 highest-yield queries only (16 requests/day at 2 runs)
    for query in QUERIES[:8]:
        try:
            r = requests.post(f"https://jooble.org/api/{key}",
                              json={"keywords": query, "location": "USA"},
                              headers=_HDR, timeout=20)
            if r.status_code != 200:
                continue
            for j in r.json().get("jobs", []):
                title = j.get("title", "")
                url = j.get("link", "")
                if not url or not title_ok(title) or not is_us_location(j.get("location", "")):
                    continue
                comp = j.get("company", "")
                if db.upsert_job(conn, url=url, title=title, company=comp,
                                 location=j.get("location", ""), source="jooble",
                                 is_core=is_core(title),
                                 date_posted=(j.get("updated", "") or "")[:10],
                                 description=j.get("snippet", ""),
                                 salary=(j.get("salary", "") or "").strip()):
                    added += 1
                db.touch_company(conn, comp, source="jooble")
        except Exception as e:
            if verbose:
                print(f"  [warn] jooble/'{query}': {type(e).__name__}")
    return added


# ── JSearch (RapidAPI) ──────────────────────────────────────────────────────
# Aggregates Google for Jobs, so it reaches LinkedIn/Indeed/Glassdoor/ZipRecruiter
# and employer ATS pages in one call. Its real value here is `apply_options`: it
# hands back the EMPLOYER's own apply link, pre-labelled `is_direct` — exactly what
# direct_apply.py otherwise spends network calls rediscovering.
# Sold two ways by the same vendor (OpenWeb Ninja) — set api_keys.jsearch_via to
# match where you got the key, because the auth header differs:
#   rapidapi     (default)  X-RapidAPI-Key   rapidapi.com/.../api/jsearch
#   openwebninja            X-API-Key        app.openwebninja.com
_JS_HOST = "jsearch.p.rapidapi.com"
_JS_ENDPOINTS = {
    # the old /search 404s now ("Endpoint '/search' does not exist"); the live
    # search path is /search-v2 on both vendors. Response is {"data": {"jobs": [...]}}
    # — _js_rows() already accepts that shape.
    "rapidapi":     (f"https://{_JS_HOST}/search-v2",
                     {"X-RapidAPI-Key": "{k}", "X-RapidAPI-Host": _JS_HOST}),
    "openwebninja": ("https://api.openwebninja.com/jsearch/search-v2",
                     {"X-API-Key": "{k}"}),
}
_JS_REQUESTS = 1   # keyword-GROUPS to cover per run (see _js_groups). Free tier is
                   # ~150 req/MONTH, so 1 group/run ≈ 62/mo at 2 runs/day.
_JS_GROUPS = 3     # split the lane-ordered query list into this many OR-groups;
                   # ONE group runs per call, rotating by an AM/PM bucket so all
                   # three cycle every 3 runs (~1.5 days at 2 runs/day).


def _js_link(j: dict) -> tuple[str, bool]:
    """Best apply link for a JSearch job -> (url, is_direct_employer_link)."""
    for opt in (j.get("apply_options") or []):
        if opt.get("is_direct") and opt.get("apply_link"):
            return opt["apply_link"], True
    return (j.get("job_apply_link", "") or ""), bool(j.get("job_apply_is_direct"))


def _js_location(j: dict) -> str:
    loc = (j.get("job_location") or "").strip()   # newer API versions
    if not loc:
        loc = ", ".join([p for p in (j.get("job_city"), j.get("job_state")) if p])
    if not loc and j.get("job_is_remote"):
        loc = "Remote"
    return loc


def _js_posted(j: dict) -> str:
    d = (j.get("job_posted_at_datetime_utc") or "")[:10]
    if d:
        return d
    ts = j.get("job_posted_at_timestamp")
    try:
        return (_dt.datetime.fromtimestamp(float(ts), _dt.timezone.utc)
                .strftime("%Y-%m-%d")) if ts else ""
    except Exception:
        return ""


def _js_rows(payload: dict) -> list:
    """The two endpoints disagree: RapidAPI's `data` is the job list, OpenWeb
    Ninja's is {'jobs': [...]}. Accept either."""
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get("jobs") or []
    return data if isinstance(data, list) else []


def _js_groups() -> list[list[str]]:
    """Split the lane-ordered QUERIES into _JS_GROUPS contiguous chunks — each
    becomes one OR query. Lane order matters: a chunk is meant to be a coherent
    lane so its ~6 clauses compete for the 10-result page with *similar* roles,
    and a rare term is never buried behind a high-volume one from another lane."""
    if not QUERIES:
        return []
    n = -(-len(QUERIES) // _JS_GROUPS)          # ceil div -> ~equal chunk size
    return [QUERIES[i:i + n] for i in range(0, len(QUERIES), n)]


def _jsearch(conn, key, budget=_JS_REQUESTS, via="rapidapi", verbose=True) -> int:
    added = 0
    groups = _js_groups()
    if not groups:
        return 0
    endpoint, hdr_tpl = _JS_ENDPOINTS.get(via, _JS_ENDPOINTS["rapidapi"])
    # Rotate ONE keyword-group per RUN (not per day): an AM/PM bucket advances the
    # index every run, so the groups cycle every len(groups) runs (~1.5 days at
    # 2 runs/day) and every lane refreshes ~21x/month — all on 1 request/run.
    now = _dt.datetime.now()
    run_seq = now.toordinal() * 2 + (1 if now.hour >= 12 else 0)
    budget = max(1, min(int(budget or _JS_REQUESTS), len(groups)))
    hdr = {**_HDR, **{h: v.format(k=key) for h, v in hdr_tpl.items()}}
    for i in range(budget):
        gi = (run_seq + i) % len(groups)
        group = groups[gi]
        query = " OR ".join(f'"{q}"' for q in group)
        try:
            r = requests.get(
                endpoint,
                params={"query": f"{query} in USA", "page": "1", "num_pages": "1",
                        "country": "us", "date_posted": "week"},
                headers=hdr, timeout=25)
            if r.status_code != 200:
                if verbose and r.status_code in (401, 403, 429):
                    # 401/403 = bad or unsubscribed key, 429 = monthly quota spent
                    print(f"  [warn] jsearch: HTTP {r.status_code} — check key/quota")
                continue
            for j in _js_rows(r.json()):
                title = j.get("job_title", "")
                url, direct = _js_link(j)
                loc = _js_location(j)
                if not url or not title_ok(title) or not is_us_location(loc or "US"):
                    continue
                comp = j.get("employer_name", "") or ""
                if db.upsert_job(conn, url=url, title=title, company=comp,
                                 location=loc, source="jsearch", is_core=is_core(title),
                                 date_posted=_js_posted(j),
                                 description=j.get("job_description", "") or "",
                                 salary=fmt_salary(j.get("job_min_salary"),
                                                   j.get("job_max_salary"),
                                                   j.get("job_salary_period", "") or "")):
                    added += 1
                    if direct:
                        # Employer's own link — skip direct_apply's resolver entirely
                        conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (url, url))
                db.touch_company(conn, comp, source="jsearch",
                                 careers_url=(j.get("employer_website") or ""))
        except Exception as e:
            if verbose:
                print(f"  [warn] jsearch/group{gi + 1}: {type(e).__name__}")
    return added


def run(conn, verbose=True) -> int:
    k = _keys()
    scrape = _cfg().get("scrape", {}) or {}
    # Cascade: the sources are ordered cheapest-quota-first, and the scarce ones
    # only run when the abundant ones came up short. Adzuna is effectively
    # unmetered for this volume; Jooble is ~500 requests and JSearch ~150 per
    # MONTH, so spending them on a run that already found plenty is pure waste.
    # Set scrape.cascade_min to 0 to always run every source.
    cascade_min = int(scrape.get("cascade_min", 5))
    added = 0
    if k.get("adzuna_app_id") and k.get("adzuna_app_key"):
        n = _adzuna(conn, k["adzuna_app_id"], k["adzuna_app_key"], verbose)
        added += n
        if verbose:
            print(f"  adzuna: +{n} new jobs")
    elif verbose:
        print("  adzuna: skipped (no key — free at developer.adzuna.com)")
    if added >= cascade_min > 0:
        if verbose:
            print(f"  jooble/jsearch: skipped — {added} new jobs already "
                  f"(cascade_min={cascade_min}); monthly quota saved")
        conn.commit()
        return added
    if k.get("jooble_key"):
        n = _jooble(conn, k["jooble_key"], verbose)
        added += n
        if verbose:
            print(f"  jooble: +{n} new jobs")
    elif verbose:
        print("  jooble: skipped (no key — free at jooble.org/api/about)")
    if added >= cascade_min > 0:
        if verbose:
            print(f"  jsearch: skipped — {added} new jobs already; quota saved")
    elif k.get("jsearch_key"):
        budget = scrape.get("jsearch_requests", _JS_REQUESTS)
        n = _jsearch(conn, k["jsearch_key"], budget,
                     k.get("jsearch_via", "rapidapi"), verbose)
        added += n
        if verbose:
            print(f"  jsearch: +{n} new jobs")
    elif verbose:
        print("  jsearch: skipped (no key — free tier on rapidapi.com/.../jsearch)")
    conn.commit()
    return added
