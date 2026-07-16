"""Find a job's real posting URL by searching the web — the way you would.

Every other resolver in direct_apply.py is deterministic: it knows an employer's
ATS and queries it. This one is the fallback for everything else — the long tail
of small firms and staffing agencies with no discoverable ATS, which is where
~40% of the board lands. Those used to get a bare search LINK you had to click
through; this actually runs the search and picks the posting out of the results.

Why it works now when a hand-rolled scraper didn't: it uses `ddgs` (deedy5/ddgs,
the maintained successor to duckduckgo-search), a metasearch library that
rotates across DuckDuckGo/Bing/Brave/Google backends and handles the anti-bot
dance. A raw request to any one of those endpoints gets a 202/403; ddgs doesn't.

The result is only trusted after link_check confirms it actually resolves, so a
stale cached search hit can't put a dead link in front of you.
"""
from __future__ import annotations
import re
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from . import link_check as LC
from .direct_apply import is_reposter, _canon

try:
    from ddgs import DDGS
except Exception:            # library optional — resolver degrades to "no result"
    DDGS = None

# Real ATS / careers hosts. A hit here is the employer's OWN application page and
# outranks a specific posting that merely sits on a third-party job board.
_ATS_HOST = re.compile(
    r"myworkdayjobs\.com|greenhouse\.io|lever\.co|smartrecruiters\.com|icims\.com|"
    r"oraclecloud\.com|eightfold\.ai|phenompeople\.com|taleo\.net|jobvite\.com|"
    r"ashbyhq\.com|workable\.com|bamboohr\.com|jobs\.|careers\.|/careers", re.I)

# Third-party job boards: a specific posting there beats a search, but loses to
# the employer's own page. Kept separate from REPOSTERS (which we never accept).
_AGGREGATOR = re.compile(
    r"builtin\.com|theladders\.com|dice\.com|monster\.com|indeed\.com|"
    r"glassdoor\.com|wellfound\.com|angel\.co", re.I)

# Tracking cruft that search results tack on — strip so the stored URL is clean
# and two links to the same job compare equal.
_JUNK_PARAM = re.compile(r"^(utm_|trk|src|source|ref|referer|referrer|gh_src|"
                         r"recruiter|linkedin|fbclid|gclid)", re.I)


def _clean(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if not _JUNK_PARAM.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(kept), ""))


def _employer_domain(url: str, company: str) -> bool:
    """Does this URL sit on the EMPLOYER's own domain? 'Barclays' -> barclays in
    search.jobs.barclays. Guards against a specific posting that happens to live
    on some aggregator we haven't blocklisted."""
    host = (urlsplit(url).netloc or "").lower()
    # company canonical words, minus generic filler, as domain-ish tokens
    words = [w for w in _canon(company).split() if len(w) >= 4]
    joined = "".join(_canon(company).split())
    return any(w in host for w in words) or (len(joined) >= 5 and joined in host)


def _owned(url: str, company: str) -> bool:
    """A link we'll call 'exact': the employer's own site, or a known ATS host.
    Anything else (jobleads, builtin, wallstreetcareers, …) is NOT the employer,
    so at best it's a weak candidate — a wrong 'exact' badge is worse than none."""
    return bool(_ATS_HOST.search(url)) or _employer_domain(url, company)


def _rank(url: str, company: str) -> int:
    """Lower is better. Employer ATS/own site < other posting < aggregator."""
    if _owned(url, company):
        return 0
    if _AGGREGATOR.search(url):
        return 2
    return 1


def search_results(query: str, max_results: int = 10) -> list[str]:
    """Raw result URLs for a query ('' list if ddgs is unavailable or errors)."""
    if DDGS is None:
        return []
    try:
        with DDGS() as d:
            return [r.get("href", "") for r in d.text(query, max_results=max_results)]
    except Exception:
        return []


def find_posting(company: str, title: str, *, validate: bool = True,
                 results: list[str] | None = None) -> tuple[str, str]:
    """(url, outcome) for one job.

    outcome: 'exact' = a specific posting we verified reachable ·
             'candidate' = a specific posting we couldn't verify (kept anyway) ·
             '' = nothing usable found.

    `results` lets a caller that already searched (e.g. the bulk pass, which
    needs the raw hits to detect rate-limiting) avoid a second query.
    """
    if results is None:
        results = search_results(f'"{title}" {company} careers apply')
    seen, cands = set(), []
    for raw in results:
        if not raw or is_reposter(raw):
            continue
        u = _clean(raw)
        if u in seen or not LC.looks_like_posting(u):
            continue
        seen.add(u)
        cands.append(u)
    cands.sort(key=lambda u: _rank(u, company))    # employer's own page first

    # 'exact' is reserved for the EMPLOYER's own posting that also validates. A
    # specific posting on some aggregator is only ever a 'candidate' — better
    # than a search, but never badged as the real thing.
    owned = [u for u in cands if _owned(u, company)]
    if not validate:
        return (owned[0], "exact") if owned else \
               ((cands[0], "candidate") if cands else ("", ""))
    for u in owned[:5]:
        if LC.classify(u, fetch=True)["verdict"] == "exact":
            return u, "exact"
    return (cands[0], "candidate") if cands else ("", "")


def upgrade_weak_links(conn, limit: int = 400, sleep: float = 1.5,
                       verbose: bool = True) -> dict:
    """Try to replace weak (search-fallback) links with real postings found on
    the web. Rate-limited on purpose — ddgs will start refusing if hammered, and
    a slower pass that finishes beats a fast one that gets blocked halfway.
    """
    if DDGS is None:
        if verbose:
            print("  web upgrade skipped — `pip install ddgs` to enable")
        return {"upgraded": 0, "kept": 0, "tried": 0}

    jobs = conn.execute(
        "SELECT rowid, company, title FROM jobs "
        "WHERE apply_kind='weak' AND status='new' ORDER BY score DESC LIMIT ?",
        (limit,)).fetchall()
    stats = {"upgraded": 0, "kept": 0, "tried": 0}
    fixes: list[tuple[str, int]] = []
    misses = 0                      # consecutive empty searches → probably blocked
    for rowid, company, title in jobs:
        stats["tried"] += 1
        results = search_results(f'"{title}" {company} careers apply')
        if not results:
            # Empty could mean "no hits" OR "rate-limited". If it keeps happening,
            # back off hard rather than burn the rest of the list against a wall.
            misses += 1
            if misses >= 8:
                if verbose:
                    print(f"  backing off — {misses} empty searches in a row "
                          f"(rate limited). Stopping; re-run later to continue.")
                break
            time.sleep(sleep * 4)
            stats["kept"] += 1
            continue
        misses = 0
        url, outcome = find_posting(company, title, validate=True, results=results)
        if outcome == "exact":
            fixes.append((url, rowid))
            stats["upgraded"] += 1
        else:
            stats["kept"] += 1
        if verbose and stats["tried"] % 25 == 0:
            print(f"  web-searched {stats['tried']}/{len(jobs)} "
                  f"(+{stats['upgraded']} exact) ...")
        time.sleep(sleep)

    for url, rowid in fixes:              # one short write burst, not per-row
        conn.execute("UPDATE jobs SET apply_url=?, apply_kind='exact' WHERE rowid=?",
                     (url, rowid))
    conn.commit()
    if verbose:
        print(f"  web upgrade: {stats['upgraded']} weak links -> exact postings "
              f"(of {stats['tried']} tried)")
    return stats
