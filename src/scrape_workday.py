"""Workday JSON-API feeder — the token-free, un-blockable lane.

Every Workday customer exposes a public JSON endpoint:
    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets":{},"limit":20,"offset":0,"searchText":"fraud"}

This is the official careers-site API (what the bank's own site calls), so it
isn't bot-blocked. We query each seeded tenant with our search terms, filter
titles, store matches, and register the tenant in the company directory.

TENANTS below are verified-working seeds. Add more by finding a bank's careers
page (…myworkdayjobs.com/…), reading its host/tenant/site from the URL, and
appending a row. `python -m src.scrape_workday --probe host tenant` helps test.
"""
from __future__ import annotations
import sys
import requests

from . import db
from .sources import QUERIES, title_ok, is_core

# (label, host, tenant, site) — all verified returning HTTP 200
TENANTS = [
    ("Citi",            "citi.wd5.myworkdayjobs.com",        "citi",        "2"),
    ("PNC",             "pnc.wd5.myworkdayjobs.com",         "pnc",         "External"),
    ("Mastercard",      "mastercard.wd1.myworkdayjobs.com",  "mastercard",  "CorporateCareers"),
    ("Fiserv",          "fiserv.wd5.myworkdayjobs.com",      "fiserv",      "EXT"),
    ("Morgan Stanley",  "ms.wd5.myworkdayjobs.com",          "ms",          "External"),
    ("State Street",    "statestreet.wd1.myworkdayjobs.com", "statestreet", "Global"),
    ("FIS",             "fis.wd5.myworkdayjobs.com",         "fis",         "SearchJobs"),
    ("Nasdaq",          "nasdaq.wd1.myworkdayjobs.com",      "nasdaq",      "Global_External_Site"),
]

# Search terms sent to each tenant's API (broad; title filter does the rest)
WD_TERMS = ["fraud", "AML", "credit risk", "compliance", "risk analytics",
            "SAS", "data analytics", "CCAR", "financial crime", "reporting"]

HDR = {"Content-Type": "application/json", "Accept": "application/json",
       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _fetch(host, tenant, site, term, limit=20, offset=0):
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    r = requests.post(url, headers=HDR, timeout=15, json={
        "appliedFacets": {}, "limit": limit, "offset": offset, "searchText": term})
    r.raise_for_status()
    return r.json()


def run(conn, *, verbose=True) -> int:
    added = 0
    for label, host, tenant, site in TENANTS:
        careers = f"https://{host}/en-US/{site}"
        seen_here = 0
        for term in WD_TERMS:
            try:
                data = _fetch(host, tenant, site, term)
            except Exception as e:
                if verbose:
                    print(f"  [warn] {label}/'{term}': {type(e).__name__}")
                continue
            for p in data.get("jobPostings", []):
                title = p.get("title", "")
                path = p.get("externalPath", "")
                if not title_ok(title) or not path:
                    continue
                url = f"https://{host}{path}"
                loc = p.get("locationsText", "")
                if db.upsert_job(conn, url=url, title=title, company=label,
                                 location=loc, source="workday", is_core=is_core(title)):
                    added += 1
                    seen_here += 1
        db.touch_company(conn, label, source="workday",
                         careers_url=careers,
                         workday_url=f"https://{host}/wday/cxs/{tenant}/{site}/jobs")
        if verbose and seen_here:
            print(f"  workday {label}: +{seen_here}")
    conn.commit()
    if verbose:
        print(f"  workday: +{added} new jobs total")
    return added


def _probe(host, tenant):
    """Try common site slugs against a host/tenant to find the working one."""
    slugs = ["External", "ExternalCareerSite", "External_Career_Site", "Careers",
             "careers", "en-US", "EXT", "Global", "Global_External_Site",
             "CorporateCareers", "SearchJobs", "External_Careers", "2", "1"]
    for site in slugs:
        try:
            d = _fetch(host, tenant, site, "", limit=1)
            print(f"OK  site={site}  total={d.get('total','?')}")
            return
        except Exception:
            continue
    print("no slug worked")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--probe":
        _probe(sys.argv[2], sys.argv[3])
    else:
        c = db.connect(); db.init(c); run(c)
