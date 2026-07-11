"""Official aggregator APIs — Adzuna + Jooble (free keys, no scraping fragility).

These are true consolidators: they aggregate thousands of boards and company
sites and serve them over stable JSON APIs — no bot-blocking, no HTML breakage.

Keys (both free) go in config/profile.yml:
    api_keys:
      adzuna_app_id:  "..."     # https://developer.adzuna.com  (instant signup)
      adzuna_app_key: "..."
      jooble_key:     "..."     # https://jooble.org/api/about  (emailed key)

Each source is skipped silently when its key is absent.
"""
from __future__ import annotations
import requests
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from . import db
from .sources import QUERIES, title_ok, is_core, is_us_location

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
_HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _keys() -> dict:
    if yaml and _CFG.exists():
        try:
            return (yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}).get("api_keys", {}) or {}
        except Exception:
            return {}
    return {}


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
                                 date_posted=(j.get("created", "") or "")[:10]):
                    added += 1
                db.touch_company(conn, comp, source="adzuna")
        except Exception as e:
            if verbose:
                print(f"  [warn] adzuna/'{query}': {type(e).__name__}")
    return added


def _jooble(conn, key, verbose=True) -> int:
    added = 0
    for query in QUERIES:
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
                                 date_posted=(j.get("updated", "") or "")[:10]):
                    added += 1
                db.touch_company(conn, comp, source="jooble")
        except Exception as e:
            if verbose:
                print(f"  [warn] jooble/'{query}': {type(e).__name__}")
    return added


def run(conn, verbose=True) -> int:
    k = _keys()
    added = 0
    if k.get("adzuna_app_id") and k.get("adzuna_app_key"):
        n = _adzuna(conn, k["adzuna_app_id"], k["adzuna_app_key"], verbose)
        added += n
        if verbose:
            print(f"  adzuna: +{n} new jobs")
    elif verbose:
        print("  adzuna: skipped (no key — free at developer.adzuna.com)")
    if k.get("jooble_key"):
        n = _jooble(conn, k["jooble_key"], verbose)
        added += n
        if verbose:
            print(f"  jooble: +{n} new jobs")
    elif verbose:
        print("  jooble: skipped (no key — free at jooble.org/api/about)")
    conn.commit()
    return added
