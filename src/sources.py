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
]

DEFAULT_NEGATIVE = [
    "junior", "intern", "entry level", "ios", "android", "frontend",
    "front end", "php", "ruby", "embedded", "firmware", "blockchain", "web3",
    "salesforce admin", "physical security", "nurse", "recruiter", "driver",
    "warehouse", "retail store", "cashier",
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
