"""Direct-apply link resolver — turn aggregator links into real employer apply URLs.

Problem: Jooble/LinkedIn/Indeed links often bounce you through reposters
(Lensa, Talentify, jobs2careers) instead of the employer's own portal. You end
up clicking 3-4 times and sometimes can't apply at all.

Fix: for every job we resolve an `apply_url` ONCE, at scan time, and cache it.

Strategy (cheap → expensive):
  1. Already direct?  Host is an employer ATS (Workday/Greenhouse/Lever/iCIMS/
     SmartRecruiters/Radancy) → apply_url = url. Zero network calls.
  2. Known portal?    Look up the company's ATS (cached in the companies table,
     auto-discovered on first sight) and search THAT portal for the job title.
  3. Fallback:        the company's careers page, so you at least land on the
     employer's own site rather than a reposter.

All token-free. Nothing here calls a paid API.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse, quote

import requests

from .sources import slugify

HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
       "Accept": "application/json,text/html"}
TIMEOUT = 15

# Hosts that ARE the employer's application system — links here are already good.
DIRECT_HOSTS = (
    "myworkdayjobs.com", "greenhouse.io", "lever.co", "icims.com",
    "smartrecruiters.com", "taleo.net", "successfactors.com", "ashbyhq.com",
    "workable.com", "jobvite.com", "brassring.com", "avature.net",
    "eightfold.ai", "phenompeople.com", "oraclecloud.com", "recruiting.ultipro",
)

# Reposters / aggregators — a link here is NOT an apply link.
REPOSTERS = ("lensa.com", "jooble.org", "talentify.io", "jobs2careers.com",
             "simplyhired.com", "ziprecruiter.com", "glassdoor.com",
             "indeed.com", "linkedin.com", "adzuna.com", "trabajo.org",
             "myjobhelper.com", "jobcase.com", "snagajob.com")


def is_direct(url: str) -> bool:
    host = (urlparse(url or "").netloc or "").lower()
    return any(h in host for h in DIRECT_HOSTS)


def is_reposter(url: str) -> bool:
    host = (urlparse(url or "").netloc or "").lower()
    return any(h in host for h in REPOSTERS)


# ── title matching ────────────────────────────────────────────────────────────
def _norm(t: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())
    return " ".join(t.split())


def _match(want: str, candidates: list[tuple[str, str]]) -> str:
    """Pick the candidate (title, url) whose title best matches `want`."""
    w = _norm(want)
    if not w or not candidates:
        return ""
    wt = set(w.split())
    best, best_score = "", 0.0
    for title, url in candidates:
        c = _norm(title)
        if c == w:                       # exact — done
            return url
        ct = set(c.split())
        if not ct:
            continue
        score = len(wt & ct) / max(len(wt), len(ct))
        if score > best_score:
            best, best_score = url, score
    return best if best_score >= 0.72 else ""


# ── portal adapters: each returns [(title, apply_url), ...] for a search ──────
def _workday(ref: str, title: str) -> list[tuple[str, str]]:
    """ref = 'host|tenant|site'."""
    try:
        host, tenant, site = ref.split("|")
        r = requests.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                          json={"appliedFacets": {}, "limit": 20, "offset": 0,
                                "searchText": title},
                          headers=HDR, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        out = []
        for j in r.json().get("jobPostings", []):
            path = j.get("externalPath", "")
            if path:
                out.append((j.get("title", ""), f"https://{host}/en-US/{site}{path}"))
        return out
    except Exception:
        return []


def _radancy(ref: str, title: str) -> list[tuple[str, str]]:
    """ref = base portal url, e.g. https://jobs.citizensbank.com"""
    try:
        r = requests.get(f"{ref.rstrip('/')}/search-jobs/results",
                         params={"ActiveFacetID": 0, "CurrentPage": 1,
                                 "RecordsPerPage": 25, "Distance": 50,
                                 "RadiusUnitType": 0, "Keywords": title,
                                 "SearchType": 5, "SortCriteria": 0,
                                 "SortDirection": 0,
                                 "SearchResultsModuleName": "Search Results",
                                 "SearchFiltersModuleName": "Search Filters"},
                         headers=HDR, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        html = r.json().get("results", "") or ""
        pairs = re.findall(r'<a href="(/job/[^"]+)"[^>]*>\s*<h2[^>]*>([^<]+)</h2>',
                           html, re.S)
        return [(t.strip(), ref.rstrip("/") + h) for h, t in pairs]
    except Exception:
        return []


def _greenhouse(ref: str, title: str) -> list[tuple[str, str]]:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{ref}/jobs",
                         headers=HDR, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        return [(j.get("title", ""), j.get("absolute_url", ""))
                for j in r.json().get("jobs", [])]
    except Exception:
        return []


def _lever(ref: str, title: str) -> list[tuple[str, str]]:
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{ref}",
                         params={"mode": "json"}, headers=HDR, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        return [(j.get("text", ""), j.get("hostedUrl", "")) for j in r.json()]
    except Exception:
        return []


def _smartrecruiters(ref: str, title: str) -> list[tuple[str, str]]:
    try:
        r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{ref}/postings",
                         params={"q": title, "limit": 25}, headers=HDR, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        out = []
        for j in r.json().get("content", []):
            jid = j.get("id", "")
            nm = j.get("name", "")
            if jid:
                out.append((nm, f"https://jobs.smartrecruiters.com/{ref}/{jid}"))
        return out
    except Exception:
        return []


ADAPTERS = {"workday": _workday, "radancy": _radancy, "greenhouse": _greenhouse,
            "lever": _lever, "smartrecruiters": _smartrecruiters}

# Employers whose portal we already know (grows via discovery below).
KNOWN_PORTALS: dict[str, tuple[str, str]] = {
    "citizens": ("radancy", "https://jobs.citizensbank.com"),
    "citizens bank": ("radancy", "https://jobs.citizensbank.com"),
    "citizens financial group": ("radancy", "https://jobs.citizensbank.com"),
}


def _workday_portals() -> dict[str, tuple[str, str]]:
    """Reuse the verified Workday tenants we already scrape."""
    try:
        from .scrape_workday import TENANTS
    except Exception:
        return {}
    out = {}
    for label, host, tenant, site in TENANTS:
        out[label.lower()] = ("workday", f"{host}|{tenant}|{site}")
    return out


# Legal/marketing suffixes that don't identify the employer
_NOISE = (r"\b(inc|incorporated|corp|corporation|co|company|llc|lp|llp|plc|"
          r"na|n a|group|holdings|holding|the|us|usa|and|&)\b")


def _canon(name: str) -> str:
    """Canonical employer key. 'JPMorgan Chase & Co.' -> 'jpmorgan chase'."""
    n = re.sub(r"[^a-z0-9 &]", " ", (name or "").lower())
    n = re.sub(_NOISE, " ", n)
    return " ".join(n.split())


# Real-world name variants -> the canonical key used in the portal tables.
ALIASES = {
    "citigroup": "citi", "citibank": "citi", "citi bank": "citi",
    "citizens bank": "citizens", "citizens financial": "citizens",
    "jpmorgan chase": "jpmorgan", "jp morgan chase": "jpmorgan",
    "j p morgan": "jpmorgan", "chase": "jpmorgan",
    "bank of america": "bofa", "merrill": "bofa",
    "wells fargo bank": "wells fargo",
}


def _key(name: str) -> str:
    c = _canon(name)
    return ALIASES.get(c, c)


def _probe_ok(kind: str, body) -> bool:
    """A portal only counts if it actually returns POSTINGS (not an empty shell)."""
    try:
        if kind == "greenhouse":
            return bool(body.get("jobs"))
        if kind == "lever":
            return isinstance(body, list) and len(body) > 0
        if kind == "smartrecruiters":
            return bool(body.get("content")) and int(body.get("totalFound", 0)) > 0
    except Exception:
        return False
    return False


def discover_portal(company: str) -> tuple[str, str]:
    """Find a company's ATS. Returns (kind, ref) or ('','').
    EXACT canonical match only — a substring match would send 'Citi' jobs to
    'Citizens' (they share a prefix), which is worse than no link at all."""
    k = _key(company)
    if not k:
        return "", ""
    for table in (KNOWN_PORTALS, _workday_portals()):
        canon = {_key(label): val for label, val in table.items()}
        if k in canon:
            return canon[k]
    # probe the public ATS APIs by slug — must return real postings to count
    dashed = slugify(k)
    slug = dashed.replace("-", "")
    for kind, ref, probe in (
        ("greenhouse", dashed, f"https://boards-api.greenhouse.io/v1/boards/{dashed}/jobs"),
        ("lever", dashed, f"https://api.lever.co/v0/postings/{dashed}?mode=json&limit=5"),
        ("smartrecruiters", slug, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=5"),
    ):
        try:
            r = requests.get(probe, headers=HDR, timeout=10)
            if r.status_code == 200 and _probe_ok(kind, r.json()):
                return kind, ref
        except Exception:
            continue
    return "", ""


# Tier 3 — employers whose APIs are bot-blocked (403) but whose careers site
# accepts a keyword search. Deep-link straight into THEIR search, pre-filled
# with the job title: you land on the employer, never on a reposter.
SEARCH_FALLBACKS = {
    "wells fargo": "https://www.wellsfargojobs.com/en/jobs/?search={q}",
    "jpmorgan": "https://careers.jpmorgan.com/us/en/search-results?keywords={q}",
    "bofa": "https://careers.bankofamerica.com/en-us/job-search?search={q}",
    "citizens": "https://jobs.citizensbank.com/search-jobs/{q}/",
    "american express": "https://aexp.eightfold.ai/careers?query={q}",
    "capital one": "https://www.capitalonecareers.com/search-jobs/{q}/",
    "goldman sachs": "https://higher.gs.com/results?search={q}",
    "hsbc": "https://mycareer.hsbc.com/en_GB/external/SearchJobs?keywords={q}",
}


def search_fallback(company: str, title: str) -> str:
    """Employer careers-search deep link for a company we can't API-scrape."""
    tpl = SEARCH_FALLBACKS.get(_key(company))
    return tpl.format(q=quote(title, safe="")) if tpl else ""


def resolve_one(company: str, title: str, url: str, portal: tuple[str, str] | None = None) -> str:
    """Best apply URL for one job ('' if we can't do better than what we have)."""
    if is_direct(url):
        return url
    kind, ref = portal if portal else discover_portal(company)
    if kind:
        hit = _match(title, ADAPTERS[kind](ref, title))
        if hit:
            return hit
    return search_fallback(company, title)


def resolve_all(conn, limit: int = 2000, verbose: bool = True) -> dict:
    """Give every job the best apply link we can, cached in jobs.apply_url.

    Tier 1  already an employer ATS link      -> use as-is (no network)
    Tier 2  employer portal API               -> exact posting URL
    Tier 3  employer careers search deep-link -> their site, title pre-filled
    Tier 4  company careers page              -> at least the right employer

    Discovers each company's ATS ONCE (cached in-run and persisted to the
    companies directory), not once per job.
    """
    rows = conn.execute(
        """SELECT url, title, company FROM jobs
           WHERE COALESCE(apply_url,'') = '' ORDER BY score DESC"""
    ).fetchall()

    stats = {"direct": 0, "portal": 0, "search": 0, "careers": 0, "unresolved": 0}
    portals: dict[str, tuple[str, str]] = {}
    looked_up = 0

    for url, title, company in rows:
        # Tier 1 — free, no network
        if is_direct(url):
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (url, url))
            stats["direct"] += 1
            continue
        if looked_up >= limit:
            stats["unresolved"] += 1
            continue

        key = _key(company)
        if key not in portals:
            portals[key] = discover_portal(company)
            if portals[key][0]:
                kind, ref = portals[key]
                conn.execute(
                    "UPDATE companies SET ats=?, ats_ref=? WHERE name=?",
                    (kind, ref, company))
                if verbose:
                    print(f"  portal: {company} -> {kind}")

        kind, ref = portals[key]
        found = ""
        if kind:
            looked_up += 1
            found = _match(title, ADAPTERS[kind](ref, title))
        if found:                                    # Tier 2
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (found, url))
            stats["portal"] += 1
            continue

        sf = search_fallback(company, title)         # Tier 3
        if sf:
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (sf, url))
            stats["search"] += 1
            continue

        cr = conn.execute("SELECT careers_url FROM companies WHERE name=?",  # Tier 4
                          (company,)).fetchone()
        if cr and (cr[0] or "").strip():
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (cr[0], url))
            stats["careers"] += 1
        else:
            stats["unresolved"] += 1
        conn.commit()

    conn.commit()
    if verbose:
        print(f"  apply links: {stats['direct']} already direct | "
              f"{stats['portal']} exact employer posting | "
              f"{stats['search']} employer search | "
              f"{stats['careers']} careers page | {stats['unresolved']} none")
    return stats
