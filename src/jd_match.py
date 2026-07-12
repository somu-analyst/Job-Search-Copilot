"""JD-vs-resume fit analysis — token-free, deterministic.

For Workday-sourced jobs we fetch the FULL job description from the same
public JSON API the careers page uses. The resume (cv.md + article-digest.md)
is then scored against the JD from three lenses:

  ATS/Workday score   — % of JD skill keywords present in the resume
                        (what the parser/knock-out filter sees)
  Recruiter score     — top-of-JD essentials: title alignment, years,
                        headline skills (the 6-second skim)
  Hiring-manager score— domain-depth terms (fraud/AML/CCAR/model work)
                        + quantified achievements
  Overall             — weighted blend

Also returns: highlights (JD keywords you HAVE) and gaps (JD keywords MISSING
from the resume) so you know what to add before applying.
Honest label: keyword-based estimate, not an LLM judgment.
"""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from .resume import load_cv_md, careerops_dir

HDR = {"Accept": "application/json",
       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Skill vocabulary scanned for in JDs (extend freely)
SKILLS = [
    "sas", "sas viya", "viya", "python", "sql", "r ", "tableau", "power bi",
    "excel", "vba", "unix", "linux", "shell", "hive", "hadoop", "spark",
    "pyspark", "snowflake", "databricks", "teradata", "oracle", "bigquery",
    "aws", "azure", "gcp", "git", "autosys", "airflow", "etl", "mainframe",
    "cobol", "jcl", "api", "machine learning", "statistics", "regression",
    "fraud", "aml", "anti-money laundering", "bsa", "kyc", "cdd", "edd",
    "sanctions", "ofac", "transaction monitoring", "sar", "financial crime",
    "credit risk", "market risk", "model risk", "model validation",
    "ccar", "cecl", "stress testing", "basel", "loss forecasting",
    "pd", "lgd", "ead", "regulatory reporting", "10-q", "10-k", "sox",
    "data governance", "data quality", "data lineage", "data management",
    "collections", "loss mitigation", "mortgage", "servicing", "underwriting",
    "dashboards", "visualization", "stakeholder", "agile", "jira",
    "leadership", "mentoring", "project management", "communication",
]

DOMAIN_DEEP = ["fraud", "aml", "bsa", "kyc", "sanctions", "ofac", "sar",
               "credit risk", "ccar", "cecl", "stress testing", "model validation",
               "loss forecasting", "pd", "lgd", "ead", "regulatory reporting",
               "transaction monitoring", "financial crime", "collections",
               "loss mitigation"]


def fetch_jd(url: str) -> str:
    """Full JD text for a Workday job URL ('' if not fetchable)."""
    try:
        u = urlparse(url)
        if "myworkdayjobs.com" not in u.netloc or "/en-US/" not in u.path:
            return ""
        tenant = u.netloc.split(".")[0]
        after = u.path.split("/en-US/")[1]
        site, _, jobpath = after.partition("/")
        api = f"https://{u.netloc}/wday/cxs/{tenant}/{site}/{jobpath}"
        r = requests.get(api, headers=HDR, timeout=15)
        if r.status_code != 200:
            return ""
        html = (r.json().get("jobPostingInfo") or {}).get("jobDescription", "")
        return re.sub(r"<[^>]+>", " ", html)
    except Exception:
        return ""


def _resume_text() -> str:
    txt = load_cv_md()
    digest = careerops_dir() / "article-digest.md"
    if digest.exists():
        txt += "\n" + digest.read_text(encoding="utf-8")
    return txt.lower()


def _hits(text: str, vocab: list[str]) -> set:
    t = " " + re.sub(r"[^a-z0-9+.# ]", " ", text.lower()) + " "
    return {k for k in vocab if k.strip() and f" {k.strip()} " in t or k in text.lower()}


def analyze(url: str, title: str) -> dict:
    jd = fetch_jd(url)
    resume = _resume_text()
    out = {"jd_available": bool(jd.strip())}

    jd_skills = _hits(jd, SKILLS) if jd else _hits(title, SKILLS)
    have = {k for k in jd_skills if k.strip() in resume}
    missing = sorted(jd_skills - have)

    # ATS: pure keyword coverage
    ats = 10 * len(have) / len(jd_skills) if jd_skills else 5.0

    # Recruiter: title terms + headline skills coverage
    title_terms = _hits(title, SKILLS)
    title_have = {k for k in title_terms if k in resume}
    recruiter = 10 * (0.6 * (len(title_have) / len(title_terms) if title_terms else 0.5)
                      + 0.4 * (len(have) / len(jd_skills) if jd_skills else 0.5))

    # Hiring manager: domain depth + quantified achievements
    jd_deep = jd_skills & set(DOMAIN_DEEP)
    deep_have = {k for k in jd_deep if k in resume}
    metrics_bonus = 1.0 if len(re.findall(r"\d+%|\$\d", resume)) >= 5 else 0.5
    hm = 10 * (0.7 * (len(deep_have) / len(jd_deep) if jd_deep else 0.6)
               + 0.3 * metrics_bonus)

    out.update({
        "ats": round(min(10, ats), 1),
        "recruiter": round(min(10, recruiter), 1),
        "hiring_manager": round(min(10, hm), 1),
        "overall": round(min(10, 0.4 * ats + 0.3 * recruiter + 0.3 * hm), 1),
        "highlights": sorted(have),
        "missing": missing,
    })
    return out
