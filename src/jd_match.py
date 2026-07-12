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


def jd_flags(jd: str) -> dict:
    """Scan a JD for deal-breakers a visa-dependent, US-based candidate cares about.
    Returns {'block': [...red flags...], 'note': [...things to check...]}."""
    t = (jd or "").lower()
    block, note = [], []
    if not t.strip():
        return {"block": [], "note": ["Full JD not available for this source — verify on the posting."]}

    # ── Sponsorship / work-authorization blockers ──
    spons_block = [
        "no sponsorship", "not able to sponsor", "unable to sponsor",
        "will not sponsor", "without sponsorship", "no visa sponsorship",
        "sponsorship is not", "not provide sponsorship", "not offer sponsorship",
        "must be authorized to work in the united states without",
        "no relocation or visa", "us citizens only", "u.s. citizens only",
        "must be a us citizen", "must be a u.s. citizen", "citizenship is required",
        "security clearance", "active clearance", "public trust clearance",
        "green card holder", "gc holder only",
    ]
    for phrase in spons_block:
        if phrase in t:
            block.append(f"Sponsorship/authorization blocker: “{phrase}”")
            break
    if "clearance" in t and not any("clearance" in b for b in block):
        note.append("Mentions a security clearance — often citizen-only.")

    # ── Location / onsite constraints ──
    if any(w in t for w in ["fully onsite", "100% onsite", "on-site 5 days",
                            "in office 5", "onsite daily", "must relocate"]):
        note.append("Appears fully onsite / relocation required — confirm it fits NJ.")
    elif "hybrid" in t:
        note.append("Hybrid role — check the office location and days/week.")
    if "remote" in t and "not remote" not in t:
        note.append("Mentions remote — may be flexible on location.")

    return {"block": block, "note": note}


def _resume_text() -> str:
    from pathlib import Path
    txt = load_cv_md()
    for digest in (Path(__file__).resolve().parent.parent / "resume" / "article-digest.md",
                   careerops_dir() / "article-digest.md"):
        if digest.exists():
            txt += "\n" + digest.read_text(encoding="utf-8")
            break
    return txt.lower()


def _hits(text: str, vocab: list[str]) -> set:
    t = " " + re.sub(r"[^a-z0-9+.# ]", " ", text.lower()) + " "
    return {k for k in vocab if k.strip() and f" {k.strip()} " in t or k in text.lower()}


def analyze(url: str, title: str, resume_override: str = "", jd_override: str = "") -> dict:
    jd = jd_override or fetch_jd(url)
    resume = resume_override.lower() if resume_override else _resume_text()
    out = {"jd_available": bool(jd.strip())}

    jd_skills = _hits(jd, SKILLS) if jd else _hits(title, SKILLS)
    have = {k for k in jd_skills if k.strip() in resume}
    missing = sorted(jd_skills - have)
    coverage = len(have) / len(jd_skills) if jd_skills else 0.5   # 0..1

    # broad title-word overlap with the resume (not just tech tokens)
    stop = {"and", "the", "of", "for", "senior", "lead", "analyst", "manager",
            "vp", "svp", "associate", "director", "officer", "specialist",
            "junior", "sr", "jr", "hybrid", "remote"}
    title_words = {w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in stop}
    title_overlap = (sum(1 for w in title_words if w in resume) / len(title_words)
                     if title_words else 0.5)

    # domain-depth coverage + quantified-achievement density
    jd_deep = jd_skills & set(DOMAIN_DEEP)
    deep_cov = (len({k for k in jd_deep if k in resume}) / len(jd_deep)) if jd_deep else 0.6
    metrics = min(1.0, len(re.findall(r"\d+%|\$\d", resume)) / 8)

    # all floored at 2/10 so a transferable candidate never reads as "zero"
    ats = 2 + 8 * coverage
    recruiter = 2 + 8 * (0.55 * title_overlap + 0.45 * coverage)
    hm = 2 + 8 * (0.6 * deep_cov + 0.4 * metrics)
    overall = 0.35 * ats + 0.3 * recruiter + 0.35 * hm

    out.update({
        "ats": round(min(10, ats), 1),
        "recruiter": round(min(10, recruiter), 1),
        "hiring_manager": round(min(10, hm), 1),
        "overall": round(min(10, overall), 1),
        "highlights": sorted(have),
        "missing": missing,
    })
    return out
