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
_PARENS = re.compile(r"\([^)]*\)")
_TAIL = re.compile(r"\s*[-–—|,:]\s*"
                   r"(hybrid|remote|onsite|on-site|contract|w2|c2c|usa?|full[- ]time)"
                   r"\b.*$", re.I)


def _query_variants(title: str) -> list[str]:
    """Progressively looser search strings for one job title.

    THE bug this exists to kill: an ATS `searchText` is an AND over every word you
    give it. So "Senior Regulatory Reporting Data Analyst (CCAR Y14)" returns
    ZERO — not because the job is missing, but because no posting body contains
    the literal token "Y14)". Drop the parenthetical and the same search returns
    32 hits. Feeding the raw title into search silently produced a dead end for
    any title carrying a suffix — "(AVP)", "— Hybrid", "Sr." — and the resolver
    then fell back to a careers landing page, which is the link you complained
    about. Half the board was landing pages because of this one line.

    So: try the exact title, then a de-punctuated one, then the first N words.
    First variant that returns anything wins; `_match` still has to agree it's the
    right job, so widening the SEARCH never loosens the MATCH.
    """
    t = (title or "").strip()
    out, seen = [], set()

    def add(x: str) -> None:
        x = " ".join(x.split())
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)

    add(t)
    clean = _TAIL.sub("", _PARENS.sub(" ", t))       # kill "(CCAR Y14)" / "— Hybrid"
    clean = re.sub(r"[^\w\s&/-]", " ", clean)        # kill stray punctuation
    add(clean)
    words = clean.split()
    for n in (6, 5, 4, 3):                           # then just the head of the title
        if len(words) > n:
            add(" ".join(words[:n]))
    return out[:5]


def _workday(ref: str, title: str) -> list[tuple[str, str]]:
    """ref = 'host|tenant|site'."""
    try:
        host, tenant, site = ref.split("|")
    except ValueError:
        return []
    for q in _query_variants(title):
        try:
            # limit=20 is Workday's hard max — 50 gets a flat 400, which silently
            # looked like "no such job" and sent you to a careers landing page.
            r = requests.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                              json={"appliedFacets": {}, "limit": 20, "offset": 0,
                                    "searchText": q},
                              headers=HDR, timeout=TIMEOUT)
            if r.status_code != 200:
                return []
            out = []
            for j in r.json().get("jobPostings", []):
                path = j.get("externalPath", "")
                if path:
                    out.append((j.get("title", ""),
                                f"https://{host}/en-US/{site}{path}"))
            if out:
                return out
        except Exception:
            return []
    return []


def _radancy(ref: str, title: str) -> list[tuple[str, str]]:
    """ref = base portal url, e.g. https://jobs.citizensbank.com"""
    for q in _query_variants(title):        # same AND-over-words trap as Workday
        try:
            r = requests.get(f"{ref.rstrip('/')}/search-jobs/results",
                             params={"ActiveFacetID": 0, "CurrentPage": 1,
                                     "RecordsPerPage": 50, "Distance": 50,
                                     "RadiusUnitType": 0, "Keywords": q,
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
            if pairs:
                return [(t.strip(), ref.rstrip("/") + h) for h, t in pairs]
        except Exception:
            return []
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
        for q in _query_variants(title):    # same AND-over-words trap as Workday
            r = requests.get(
                f"https://api.smartrecruiters.com/v1/companies/{ref}/postings",
                params={"q": q, "limit": 50}, headers=HDR, timeout=TIMEOUT)
            if r.status_code != 200:
                return []
            out = []
            for j in r.json().get("content", []):
                jid = j.get("id", "")
                nm = j.get("name", "")
                if jid:
                    out.append((nm, f"https://jobs.smartrecruiters.com/{ref}/{jid}"))
            if out:
                return out
        return []
    except Exception:
        return []


_FEED_CACHE: dict[str, list[tuple[str, str]]] = {}


def _workday_all(ref: str) -> list[tuple[str, str]]:
    """Every live posting at a Workday employer, by paging searchText=''.

    Keyword search can't prove a NEGATIVE: "no results" might mean the job is
    gone, or that the query was bad. Only the full board can tell those apart —
    and telling them apart is the difference between retiring a dead posting and
    dumping you on a careers landing page.

    Costs one pass per employer (20 rows/page, Workday's hard max), cached for
    the run, and only ever reached when the cheap keyword search already failed.
    """
    if ref in _FEED_CACHE:
        return _FEED_CACHE[ref]
    out: list[tuple[str, str]] = []
    complete = False
    try:
        host, tenant, site = ref.split("|")
        offset, total = 0, None
        while offset < 6000:
            r = requests.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                              json={"appliedFacets": {}, "limit": 20,
                                    "offset": offset, "searchText": ""},
                              headers=HDR, timeout=TIMEOUT)
            if r.status_code != 200:
                break
            d = r.json()
            # Workday reports `total` ONLY on the first page; every later page
            # says total:0. Overwriting it made the loop exit after 2 pages, so a
            # 1,050-job board looked like 40 — and a truncated board would have
            # declared live jobs "closed". Keep the first total; never re-read it.
            if total is None:
                total = d.get("total") or 0
            page = d.get("jobPostings") or []
            if not page:
                break
            for j in page:
                path = j.get("externalPath", "")
                if path:
                    out.append((j.get("title", ""), f"https://{host}/en-US/{site}{path}"))
            offset += 20
            if offset >= total:
                complete = True
                break
    except Exception:
        pass
    # A PARTIAL board is worse than none: absence from it would look like proof
    # the job is closed when we simply stopped early. Only cache (and therefore
    # only ever trust) a board we actually finished pulling.
    _FEED_CACHE[ref] = out if complete else []
    return _FEED_CACHE[ref]


_BOFA_FEED: list[tuple[str, str]] | None = None


def _bofa(ref: str, title: str) -> list[tuple[str, str]]:
    """Bank of America (AEM careers servlet).

    BoA's `search` parameter is a MODE, not a query — the only value it accepts
    is `getAllJobs`. Passing a job title there (which is what a naive
    `?search={title}` fallback does) is an invalid mode, so the site silently
    ignores it and renders the unfiltered job list. That is exactly the useless
    "all jobs" page you land on from an aggregator link.

    So there is nothing to query: we pull the entire live feed once (~1.8k rows,
    one request) and match against it in memory. `jcrURL` on each row is the real
    job-detail path, which is what we actually want.
    """
    global _BOFA_FEED
    if _BOFA_FEED is None:
        _BOFA_FEED = []
        try:
            r = requests.get(
                "https://careers.bankofamerica.com/services/jobssearchservlet",
                params={"start": 0, "rows": 2500, "search": "getAllJobs"},
                headers={**HDR, "Accept": "application/json",
                         "Referer": "https://careers.bankofamerica.com/en-us/job-search"},
                timeout=TIMEOUT * 3)
            if r.status_code == 200:
                for j in r.json().get("jobsList", []):
                    path = j.get("jcrURL") or ""
                    nm = j.get("postingTitle") or ""
                    if path and nm:
                        _BOFA_FEED.append(
                            (nm, f"https://careers.bankofamerica.com{path}"))
        except Exception:
            pass
    return _BOFA_FEED


ADAPTERS = {"workday": _workday, "radancy": _radancy, "greenhouse": _greenhouse,
            "lever": _lever, "smartrecruiters": _smartrecruiters, "bofa": _bofa}

# For each portal kind, how to pull the employer's ENTIRE live board.
#
# This is the backbone of the whole resolver. Keyword search is a cheap guess: it
# is brittle (an ATS ANDs every word, so one stray "(CCAR Y14)" returns nothing)
# and it can never prove a negative. The full board is authoritative on both
# counts — it always contains the job if the job exists, and if it doesn't
# contain the job, the posting is CLOSED.
#
# So the resolver asks two questions in order:
#   1. cheap keyword search  -> found it? done, one request.
#   2. full board            -> found it? done. NOT in it? the job is dead, and
#                               we retire it instead of inventing a link.
# Greenhouse and Lever ignore the query anyway and hand back the whole board, so
# for them step 1 already IS step 2.
FULL_FEEDS = {
    "bofa": lambda ref: _bofa(ref, ""),
    "workday": _workday_all,
    "greenhouse": lambda ref: _greenhouse(ref, ""),
    "lever": lambda ref: _lever(ref, ""),
}


def find_posting(kind: str, ref: str, title: str) -> tuple[str, str]:
    """(url, outcome) for one job at a known portal.

    outcome: 'portal' = exact posting found · 'gone' = employer's full board
    doesn't have it, so it's closed · '' = we couldn't tell.
    """
    hit = _match(title, ADAPTERS[kind](ref, title))          # cheap search first
    if hit:
        return hit, "portal"
    puller = FULL_FEEDS.get(kind)
    if not puller:
        return "", ""                                        # can't prove anything
    feed = puller(ref)
    if not feed:
        return "", ""                                        # network/parse failure
    hit = _match(title, feed)
    return (hit, "portal") if hit else ("", "gone")

# Employers whose portal we already know (grows via discovery below).
KNOWN_PORTALS: dict[str, tuple[str, str]] = {
    "citizens": ("radancy", "https://jobs.citizensbank.com"),
    "citizens bank": ("radancy", "https://jobs.citizensbank.com"),
    "citizens financial group": ("radancy", "https://jobs.citizensbank.com"),
    "cvs health": ("workday",
                   "cvshealth.wd1.myworkdayjobs.com|cvshealth|CVS_Health_Careers"),
    "bofa": ("bofa", "careers.bankofamerica.com"),
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
    "jpmorganchase": "jpmorgan", "j p morgan": "jpmorgan", "chase": "jpmorgan",
    "jpmorgan chase bank": "jpmorgan",
    "bank of america": "bofa", "merrill": "bofa",
    "wells fargo bank": "wells fargo",
    "u s bank": "us bank", "us bancorp": "us bank", "usbank": "us bank",
    "cvs": "cvs health", "cvs pharmacy": "cvs health",
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
#
# NOTE there is deliberately no Bank of America entry. Its careers page reads
# `search` as a MODE (`getAllJobs`), not a query, so `?search={title}` renders
# the unfiltered list — a link that looks like it worked and didn't. BoA is
# handled by the `_bofa` adapter above instead; if that finds no match, the
# posting is gone and we say so rather than fake a link.
SEARCH_FALLBACKS = {
    "wells fargo": "https://www.wellsfargojobs.com/en/jobs/?search={q}",
    "jpmorgan": "https://careers.jpmorgan.com/us/en/search-results?keywords={q}",
    "citizens": "https://jobs.citizensbank.com/search-jobs/{q}/",
    "american express": "https://aexp.eightfold.ai/careers?query={q}",
    "capital one": "https://www.capitalonecareers.com/search-jobs/{q}/",
    "goldman sachs": "https://higher.gs.com/results?search={q}",
    "hsbc": "https://mycareer.hsbc.com/en_GB/external/SearchJobs?keywords={q}",
    "us bank": "https://careers.usbank.com/global/en/search-results?keywords={q}",
    "deloitte": "https://apply.deloitte.com/careers/SearchJobs/{q}",
    "cvs health": "https://jobs.cvshealth.com/search-jobs/{q}/",
}


def search_fallback(company: str, title: str) -> str:
    """Employer careers-search deep link for a company we can't API-scrape."""
    tpl = SEARCH_FALLBACKS.get(_key(company))
    return tpl.format(q=quote(title, safe="")) if tpl else ""


def web_fallback(company: str, title: str) -> str:
    """Last resort for a job whose source is a REPOSTER (Lensa/Jooble/…) and
    whose employer we can't map: a web search for the posting on the employer's
    own site. Beats sending you to a reposter that may not even accept an
    application."""
    q = quote(f'"{title}" {company} careers apply', safe="")
    return f"https://duckduckgo.com/?q={q}"


def resolve_one(company: str, title: str, url: str, portal: tuple[str, str] | None = None) -> str:
    """Best apply URL for one job ('' if we can't do better than what we have)."""
    if is_direct(url):
        return url
    kind, ref = portal if portal else discover_portal(company)
    if kind:
        hit, _ = find_posting(kind, ref, title)
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

    stats = {"direct": 0, "portal": 0, "search": 0, "careers": 0,
             "websearch": 0, "gone": 0, "unresolved": 0}
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
        found, outcome = "", ""
        if kind:
            looked_up += 1
            found, outcome = find_posting(kind, ref, title)
        if found:                                    # Tier 2 — the exact posting
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?", (found, url))
            stats["portal"] += 1
            continue

        # 'gone' means we pulled the employer's ENTIRE live board and the job
        # wasn't on it. That's proof, not a guess — so retire it rather than hand
        # over a careers landing page that can't take an application. Only
        # find_posting() can say this, and only when the board actually loaded.
        if outcome == "gone":
            conn.execute(
                "UPDATE jobs SET status='stale', notes=? WHERE url=? AND status='new'",
                (f"Not on {company}'s live careers board — posting closed.", url))
            stats["gone"] += 1
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
        elif is_reposter(url) and company.strip():   # Tier 5 — never leave a reposter
            conn.execute("UPDATE jobs SET apply_url=? WHERE url=?",
                         (web_fallback(company, title), url))
            stats["websearch"] += 1
        else:
            stats["unresolved"] += 1
        conn.commit()

    conn.commit()
    if verbose:
        print(f"  apply links: {stats['direct']} already direct | "
              f"{stats['portal']} exact employer posting | "
              f"{stats['search']} employer search | "
              f"{stats['careers']} careers page | "
              f"{stats['websearch']} web-search (was reposter) | "
              f"{stats['unresolved']} none")
    return stats
