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
from .sources import QUERIES, title_ok, is_core, is_us_location

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
    ("Truist",          "truist.wd1.myworkdayjobs.com",      "truist",      "Careers"),
    ("Fifth Third",     "fifththird.wd5.myworkdayjobs.com",  "fifththird",  "53careers"),
    ("KeyBank",         "keybank.wd5.myworkdayjobs.com",     "keybank",     "External_Career_Site"),
    ("Huntington",      "huntington.wd12.myworkdayjobs.com", "huntington",  "HNBcareers"),
    ("Fannie Mae",      "fanniemae.wd1.myworkdayjobs.com",   "fanniemae",   "FannieMaeCareers"),
    ("TransUnion",      "transunion.wd5.myworkdayjobs.com",  "transunion",  "TransUnion"),
    ("Newrez",          "newrez.wd1.myworkdayjobs.com",      "newrez",      "NRZ"),
    ("MUFG",            "mufgub.wd3.myworkdayjobs.com",      "mufgub",      "MUFG-Careers"),
    ("Mizuho Americas", "mizuho.wd1.myworkdayjobs.com",      "mizuho",      "mizuhoamericas"),
    ("Travelers",       "travelers.wd5.myworkdayjobs.com",   "travelers",   "External"),
    ("Nationwide",      "nationwide.wd1.myworkdayjobs.com",  "nationwide",  "Nationwide_Career"),
    ("GEICO",           "geico.wd1.myworkdayjobs.com",       "geico",       "External"),
    ("Prudential/PGIM", "pru.wd5.myworkdayjobs.com",         "pru",         "Careers"),
    ("AIG",             "aig.wd1.myworkdayjobs.com",         "aig",         "aig"),
    ("Voya",            "godirect.wd5.myworkdayjobs.com",    "godirect",    "voya_jobs"),
    ("MassMutual",      "massmutual.wd1.myworkdayjobs.com",  "massmutual",  "MMAscendCareers"),
    ("The Hartford",    "thehartford.wd5.myworkdayjobs.com", "thehartford", "Careers_External"),
    ("Vanguard",        "vanguard.wd5.myworkdayjobs.com",    "vanguard",    "vanguard_external"),
    ("BlackRock",       "blackrock.wd1.myworkdayjobs.com",   "blackrock",   "BlackRock_Professional"),
    ("Raymond James",   "raymondjames.wd1.myworkdayjobs.com","raymondjames","RaymondJamesCareers"),
    ("Ameriprise",      "ameriprise.wd5.myworkdayjobs.com",  "ameriprise",  "Ameriprise"),
]

# Search terms sent to each tenant's API (broad; title filter does the rest)
WD_TERMS = ["fraud", "AML", "credit risk", "compliance", "risk analytics",
            "SAS", "data analytics", "CCAR", "financial crime", "reporting",
            "SQL", "Python", "Tableau", "data governance", "KYC",
            "regulatory reporting"]

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
                # externalPath lacks the site segment — without /en-US/{site}
                # the link 404s on the bank's careers page
                url = f"https://{host}/en-US/{site}{path}"
                loc = p.get("locationsText", "")
                # "2 Locations"-style text is uninformative; the path's city
                # segment (/job/{City-State-Country}/...) is the real signal
                seg = ""
                if "/job/" in path:
                    seg = path.split("/job/")[1].split("/")[0].replace("-", " ")
                test_loc = loc if loc and "location" not in loc.lower() else seg
                if not is_us_location(test_loc):   # primary search = USA
                    continue
                if seg and (not loc or "location" in loc.lower()):
                    loc = seg.title()
                if db.upsert_job(conn, url=url, title=title, company=label,
                                 location=loc, source="workday", is_core=is_core(title),
                                 date_posted=p.get("postedOn", "")):
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
