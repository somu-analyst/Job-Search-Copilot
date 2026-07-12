"""Shared keyword filters and search terms for all scrapers.

Edit config/profile.yml to change these without touching code — this module
loads that file and falls back to sensible BFSI/analytics defaults.
"""
from __future__ import annotations
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"

# ── Defaults (used if config/profile.yml is missing keys) ───────────────────
DEFAULT_QUERIES = [
    "fraud analytics", "AML analytics", "financial crimes analyst",
    "credit risk analytics SAS", "CCAR CECL analyst", "compliance analytics KYC",
    "SAS Viya", "data governance banking", "risk reporting analyst bank",
    "mortgage default servicing analytics", "banking analytics consultant",
    "financial services data analytics", "BFSI analytics",
    "SAS programmer analyst", "SQL data analyst banking",
    "Python data analyst financial services", "Tableau developer banking",
    "compliance analyst bank", "regulatory reporting analyst",
    "KYC AML analyst", "MIS reporting analyst banking",
]

DEFAULT_POSITIVE = [
    "fraud", "aml", "anti-money", "financial crime", "bsa", "compliance",
    "sanction", "kyc", "cdd", "transaction monitoring", "ofac", "surveillance",
    "credit risk", "risk analy", "risk manager", "risk report", "model risk",
    "model validation", "stress test", "ccar", "cecl", "loss forecast",
    "loss mitigation", "portfolio risk", "portfolio analy", "collections",
    "recovery", "default", "mortgage", "servicing", "regulatory report",
    "sec report", "external report", "call center", "contact center",
    "quantitative", "data analy", "analytics", "business analyst",
    "business intelligence", "decision science", "data scientist", "sas",
    "reporting", "mis", "data engineer", "etl", "consultant", "advisory",
    "consulting", "data management", "data governance", "data quality",
    "data steward", "master data", "metadata", "data lineage", "insights",
    "data strategy", "migration", "modernization", "remediation",
    "sql", "python", "tableau", "power bi", "viya",
]

DEFAULT_NEGATIVE = [
    "junior", "intern", "entry level", "ios", "android", "frontend",
    "front end", "php", "ruby", "embedded", "firmware", "blockchain", "web3",
    "salesforce admin", "physical security", "nurse", "recruiter", "driver",
    "warehouse", "retail store", "cashier",
    "java ", "java,", "javascript", ".net", "c++", "golang", "software engineer",
    "software developer", "full stack", "fullstack", "devops", "sre",
]

# Core-fit markers — win the per-run cap over broad "analytics" roles
DEFAULT_CORE = [
    "fraud", "aml", "financial crime", "credit risk", "ccar", "cecl",
    "compliance", "sas", "bsa", "kyc", "risk analy", "stress test",
]


def _load():
    q, pos, neg, core = DEFAULT_QUERIES, DEFAULT_POSITIVE, DEFAULT_NEGATIVE, DEFAULT_CORE
    if yaml and _CFG.exists():
        try:
            cfg = yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
            f = cfg.get("filters", {})
            q = f.get("queries", q)
            pos = [s.lower() for s in f.get("positive", pos)]
            neg = [s.lower() for s in f.get("negative", neg)]
            core = [s.lower() for s in f.get("core", core)]
        except Exception:
            pass
    return q, pos, neg, core


QUERIES, POSITIVE, NEGATIVE, CORE = _load()


def title_ok(title: str) -> bool:
    t = (title or "").lower()
    return any(p in t for p in POSITIVE) and not any(n in t for n in NEGATIVE)


def is_core(title: str) -> bool:
    t = (title or "").lower()
    return any(c in t for c in CORE)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


# ── Industry classification (substring match on company name) ──────────────
INDUSTRY_MAP = {
    "banking": ["citi", "pnc", "truist", "fifth third", "keybank", "huntington",
                "jpmorgan", "chase", "bank of america", "wells fargo", "morgan stanley",
                "goldman", "barclays", "deutsche", "hsbc", "ubs", "mufg", "mizuho",
                "smbc", "santander", "bmo", "rbc", "state street", "bny", "northern trust",
                "regions", "citizens", "m&t", "ally", "synchrony", "discover",
                "american express", "capital one", "us bank", "u.s. bank", "credit union"],
    "brokerage/asset mgmt": ["vanguard", "blackrock", "fidelity", "schwab",
                             "raymond james", "ameriprise", "lpl", "edward jones",
                             "invesco", "t. rowe", "franklin", "interactive brokers",
                             "robinhood", "morningstar", "msci", "factset", "pgim"],
    "insurance": ["travelers", "nationwide", "geico", "prudential", "aig", "voya",
                  "massmutual", "hartford", "metlife", "chubb", "tiaa", "usaa",
                  "new york life", "liberty mutual", "allstate", "state farm"],
    "payments/cards": ["mastercard", "visa", "fiserv", "fis", "paypal", "stripe",
                       "block", "square", "adyen", "marqeta", "global payments",
                       "jack henry", "aci worldwide", "early warning"],
    "credit bureau/data": ["transunion", "experian", "equifax", "fico", "moody",
                           "s&p global", "lexisnexis", "bloomberg", "nasdaq", "dtcc",
                           "broadridge", "ice", "nyse"],
    "gse/mortgage": ["fannie mae", "freddie mac", "newrez", "mr. cooper", "rocket",
                     "pennymac", "flagstar"],
    "consulting": ["deloitte", "ey", "kpmg", "pwc", "accenture", "ibm", "capgemini",
                   "cognizant", "tcs", "tata", "infosys", "wipro", "hcl", "genpact",
                   "exl", "capco", "synechron", "fractal", "tiger analytics",
                   "protiviti", "guidehouse", "crowe", "rsm", "fti", "oliver wyman",
                   "mckinsey", "general dynamics"],
    "fintech/vendor": ["sofi", "affirm", "chime", "plaid", "socure", "feedzai",
                       "sardine", "unit21", "alloy", "sift", "datavisor", "forter",
                       "signifyd", "riskified", "biocatch", "nice", "verafin",
                       "pega", "temenos", "finastra", "ncino", "wolters kluwer",
                       "symphonyai", "oracle", "intuit", "featurespace"],
}


def industry_for(company: str) -> str:
    c = (company or "").lower()
    for industry, keys in INDUSTRY_MAP.items():
        if any(k in c for k in keys):
            return industry
    return ""


# ── US location detection (primary search is USA) ──────────────────────────
_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
}
_US_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR",
}


def is_us_location(loc: str) -> bool:
    """True if a job's location text looks US-based (or is unknown/remote).

    Positive detection: 'USA'/'United States', a state name, or a 2-letter
    state abbreviation. Empty, 'Remote', and generic 'N Locations' strings
    pass (don't drop jobs for missing data)."""
    l = (loc or "").strip()
    if not l:
        return True
    low = l.lower()
    if "united states" in low or "usa" in low or "remote" in low or "location" in low:
        return True
    if any(s in low for s in _US_STATES):
        return True
    return bool(_US_ABBR & set(re.findall(r"\b([A-Z]{2})\b", l)))
