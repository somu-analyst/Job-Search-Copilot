"""H-1B sponsorship intelligence (adapted from tech-jobs-with-relocation's
visa-tagging idea, re-aimed at H-1B transfer priority).

Two layers:
  1. KNOWN — curated BFSI sponsor-history map, applied instantly to the directory.
  2. lookup_h1b(company) — live count of public H-1B filings (h1bdata.info,
     which indexes DOL disclosure data). Used by the app's Sponsors tab
     on demand, and by `python run.py --sponsors` for the top companies.

Verdicts stored in companies.sponsors_h1b:
  "strong (seed)" / "moderate (seed)" / "rare (seed)"  — from the curated map
  "N filings (h1bdata)"                                — from live lookup
"""
from __future__ import annotations
import re
import time
import requests

# Curated seed: BFSI employers with well-known H-1B posture (lowercased keys
# are matched as substrings of the directory company name).
KNOWN = {
    # strong sponsors
    "citi": "strong", "jpmorgan": "strong", "morgan stanley": "strong",
    "goldman": "strong", "bank of america": "strong", "wells fargo": "strong",
    "capital one": "strong", "american express": "strong", "barclays": "strong",
    "deutsche": "strong", "ubs": "strong", "hsbc": "strong", "bnp": "strong",
    "mizuho": "strong", "mufg": "strong", "smbc": "strong", "nomura": "strong",
    "rbc": "strong", "santander": "strong", "bmo": "strong", "bny": "strong",
    "state street": "strong", "northern trust": "strong", "dtcc": "strong",
    "broadridge": "strong", "bloomberg": "strong", "nasdaq": "strong",
    "mastercard": "strong", "visa": "strong", "fis": "strong", "fiserv": "strong",
    "paypal": "strong", "intuit": "strong", "fico": "strong", "experian": "strong",
    "transunion": "strong", "equifax": "strong", "moody": "strong",
    "s&p global": "strong", "discover": "strong", "synchrony": "strong",
    "deloitte": "strong", "ey": "strong", "kpmg": "strong", "pwc": "strong",
    "accenture": "strong", "ibm": "strong", "capgemini": "strong",
    "cognizant": "strong", "tcs": "strong", "tata consultancy": "strong",
    "infosys": "strong", "wipro": "strong", "hcl": "strong", "genpact": "strong",
    "exl": "strong", "capco": "strong", "synechron": "strong",
    "fractal": "strong", "tiger analytics": "strong", "oracle": "strong",
    "pnc": "moderate", "truist": "moderate", "u.s. bank": "moderate",
    "us bank": "moderate", "fifth third": "moderate", "keybank": "moderate",
    "m&t": "moderate", "citizens": "moderate", "regions": "moderate",
    "ally": "moderate", "prudential": "moderate", "metlife": "moderate",
    "chubb": "moderate", "aig": "moderate", "tiaa": "moderate",
    "fannie mae": "moderate", "freddie mac": "moderate", "sofi": "moderate",
    "affirm": "moderate", "chime": "moderate", "robinhood": "moderate",
    "fidelity": "moderate", "schwab": "moderate", "blackrock": "strong",
    # rarely sponsor
    "usaa": "rare", "vanguard": "rare", "navy federal": "rare",
}

_H1B_URL = "https://h1bdata.info/index.php"
_HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def seed_verdict(company: str) -> str | None:
    c = (company or "").lower()
    for key, verdict in KNOWN.items():
        if key in c:
            return f"{verdict} (seed)"
    return None


def lookup_h1b(company: str, timeout=15) -> int | None:
    """Approximate count of public H-1B filings for an employer name.
    Returns None on failure. Be polite: callers should rate-limit."""
    try:
        r = requests.get(_H1B_URL, params={"em": company, "job": "", "city": "", "year": "all"},
                         headers=_HDR, timeout=timeout)
        if r.status_code != 200:
            return None
        # count data rows in the results table
        n = len(re.findall(r"<td class=", r.text)) // 6  # ~6 cells per row
        return n
    except Exception:
        return None


def enrich_seeds(conn) -> int:
    """Apply curated verdicts to every directory company missing one."""
    rows = conn.execute(
        "SELECT name FROM companies WHERE sponsors_h1b = '' OR sponsors_h1b IS NULL"
    ).fetchall()
    n = 0
    for (name,) in rows:
        v = seed_verdict(name)
        if v:
            conn.execute("UPDATE companies SET sponsors_h1b=? WHERE name=?", (v, name))
            n += 1
    conn.commit()
    return n


def enrich_live(conn, limit=15, delay=2.0, verbose=True) -> int:
    """Live-lookup filing counts for the top companies still unverified."""
    rows = conn.execute(
        """SELECT name FROM companies
           WHERE sponsors_h1b = '' OR sponsors_h1b IS NULL
           ORDER BY job_count DESC LIMIT ?""", (limit,)).fetchall()
    n = 0
    for (name,) in rows:
        cnt = lookup_h1b(name)
        if cnt is not None:
            verdict = f"{cnt} filings (h1bdata)" if cnt else "0 filings (h1bdata)"
            conn.execute("UPDATE companies SET sponsors_h1b=? WHERE name=?", (verdict, name))
            n += 1
            if verbose:
                print(f"  h1b {name}: {cnt} filings")
        time.sleep(delay)
    conn.commit()
    return n
