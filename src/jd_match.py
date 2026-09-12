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


def _fetch_jd_workday(url: str) -> tuple[str, str]:
    """(text, title) via the Workday JSON careers API ('', '') if not a Workday URL."""
    try:
        u = urlparse(url)
        if "myworkdayjobs.com" not in u.netloc or "/en-US/" not in u.path:
            return "", ""
        tenant = u.netloc.split(".")[0]
        after = u.path.split("/en-US/")[1]
        site, _, jobpath = after.partition("/")
        api = f"https://{u.netloc}/wday/cxs/{tenant}/{site}/{jobpath}"
        r = requests.get(api, headers=HDR, timeout=15)
        if r.status_code != 200:
            return "", ""
        info = r.json().get("jobPostingInfo") or {}
        html = info.get("jobDescription", "")
        return re.sub(r"<[^>]+>", " ", html), (info.get("title") or "")
    except Exception:
        return "", ""


_JD_MAXLEN = 12000  # matches the cap db.py already applies to stored descriptions


def _fetch_jd_oracle_recruiting_cloud(url: str) -> tuple[str, str]:
    """(text, title) via Oracle Recruiting Cloud's own detail API ('', '') if
    not this platform. JPMorgan Chase runs on it (see src/direct_apply.py's
    `_jpmc`), and other large employers use the same Fusion HCM product under
    their own tenant, so this generalizes past JPMC by URL shape alone.
    The candidate-experience page itself is JS-rendered -- a plain page fetch
    gets an empty shell, so this platform NEEDS its own API call, same reason
    Workday gets one above. Verified live against a real JPMC posting."""
    try:
        u = urlparse(url)
        if "oraclecloud.com" not in u.netloc or "/CandidateExperience/" not in u.path:
            return "", ""
        m = re.search(r"/sites/([^/]+)/job/(\d+)", u.path)
        if not m:
            return "", ""
        site, job_id = m.group(1), m.group(2)
        api = (f"https://{u.netloc}/hcmRestApi/resources/latest/"
               f"recruitingCEJobRequisitionDetails")
        r = requests.get(
            api, params={"onlyData": "true",
                        "finder": f'ById;Id="{job_id}",siteNumber={site}'},
            headers=HDR, timeout=15)
        if r.status_code != 200:
            return "", ""
        items = r.json().get("items") or []
        item = items[0] if items else {}
        html = item.get("ExternalDescriptionStr") or ""
        return re.sub(r"<[^>]+>", " ", html), (item.get("Title") or "")
    except Exception:
        return "", ""


def fetch_jd_generic(url: str) -> str:
    """Best-effort JD text for ANY job-posting URL ('' if not fetchable).
    Plain page fetch + strip boilerplate — not structured like the Workday API,
    but works for postings this pipeline never scraped (paste-a-URL flow)."""
    try:
        if not url or not url.lower().startswith(("http://", "https://")):
            return ""
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=HDR, timeout=15)
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
        return text[:_JD_MAXLEN]
    except Exception:
        return ""


def fetch_jd_and_title(url: str) -> tuple[str, str]:
    """(JD text, employer-listed job title) for a job URL -- ('', '') if not
    fetchable. Tries each known platform's own structured API first (most
    accurate, and the only option for JS-rendered career sites a plain fetch
    can't see into), then falls back to generic page scraping (no title from
    that rung) for everything else."""
    text, title = _fetch_jd_workday(url)
    if text:
        return text, title
    text, title = _fetch_jd_oracle_recruiting_cloud(url)
    if text:
        return text, title
    return fetch_jd_generic(url), ""


def fetch_jd(url: str) -> str:
    """Full JD text for a job URL ('' if not fetchable). See fetch_jd_and_title
    for the version that also recovers the employer's own job title."""
    return fetch_jd_and_title(url)[0]


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


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+.#]+", text.lower())


def _resume_documents(resume_text: str) -> list[str]:
    """Split the resume into independently-scoreable units (bullets + the
    summary paragraph) instead of treating it as one blob -- both BM25 and
    the embedding similarity below need per-unit documents to find the BEST
    matching piece of the resume for each JD requirement, not an average
    over the whole thing."""
    docs = re.findall(r"^-\s+(.+)$", resume_text, re.M)
    m = re.search(r"## Professional Summary\s*\n(.+?)\n## ", resume_text, re.S | re.I)
    if m:
        docs.append(m.group(1).strip())
    return [d for d in docs if d.strip()]


def bm25_coverage(jd_terms: set, resume_text: str) -> float:
    """0..1 coverage using BM25 (term-frequency-saturating, document-length-
    normalized relevance) instead of naive substring presence -- the same
    algorithm real search/retrieval systems use, and a real step up from
    "does this string appear anywhere." Falls back to naive coverage if
    rank_bm25 isn't installed, rather than hard-failing the whole score."""
    if not jd_terms:
        return 0.5
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return sum(1 for k in jd_terms if k.strip() in resume_text) / len(jd_terms)
    docs = _resume_documents(resume_text)
    if not docs:
        return 0.0
    bm25 = BM25Okapi([_tokenize(d) for d in docs])
    covered = sum(1 for term in jd_terms if max(bm25.get_scores(_tokenize(term))) > 0)
    return covered / len(jd_terms)


_EMBED_MODEL = None
SEMANTIC_SIM_THRESHOLD = 0.45   # cosine similarity above which two phrases count as "related"


def _embed_model():
    """Lazy singleton -- loading the model takes ~1-2s once, then it's cached
    for the life of the process (Streamlit keeps the process alive across
    reruns, so this only pays once per app run, not once per score)."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL


def _extract_requirements(jd_text: str, max_n: int = 24) -> list[str]:
    """JD text -> a list of requirement-sized phrases (bullet lines / sentences)
    for the embedding layer to compare against -- semantic similarity needs
    phrase-level meaning, not single keywords, to catch paraphrasing
    ("financial crime prevention" vs "fraud/AML detection")."""
    parts = re.split(r"[\n•·]+|(?<=[.!?])\s+(?=[A-Z])", jd_text)
    parts = [p.strip(" -•·\t") for p in parts]
    parts = [p for p in parts if 15 <= len(p) <= 220]
    return parts[:max_n]


def semantic_coverage(jd_text: str, resume_text: str) -> tuple[float, list[str]]:
    """0..1 coverage using embedding cosine similarity -- catches JD
    requirements the resume satisfies in different WORDS, which BM25/keyword
    matching structurally cannot (it only ever sees spelling, never meaning).
    Returns (coverage, [requirement phrases NOT matched]) so the caller can
    show what's actually semantically missing, same shape as `missing` above.
    Returns (0.5, []) gracefully if sentence-transformers isn't available or
    the JD has nothing extractable -- never hard-fails the whole score."""
    try:
        model = _embed_model()
    except Exception:
        return 0.5, []
    reqs = _extract_requirements(jd_text)
    docs = _resume_documents(resume_text)
    if not reqs or not docs:
        return 0.5, []
    doc_emb = model.encode(docs, convert_to_numpy=True, normalize_embeddings=True)
    req_emb = model.encode(reqs, convert_to_numpy=True, normalize_embeddings=True)
    sims = req_emb @ doc_emb.T   # cosine similarity since both are L2-normalized
    best = sims.max(axis=1)
    covered = int((best >= SEMANTIC_SIM_THRESHOLD).sum())
    gaps = [reqs[i] for i in range(len(reqs)) if best[i] < SEMANTIC_SIM_THRESHOLD]
    return covered / len(reqs), gaps[:8]   # cap gaps shown -- a long JD can have many


def analyze(url: str, title: str, resume_override: str = "", jd_override: str = "") -> dict:
    jd = jd_override or fetch_jd(url)
    resume = resume_override.lower() if resume_override else _resume_text()
    out = {"jd_available": bool(jd.strip())}

    jd_skills = _hits(jd, SKILLS) if jd else _hits(title, SKILLS)
    have = {k for k in jd_skills if k.strip() in resume}
    missing = sorted(jd_skills - have)
    # BM25 replaces naive substring presence for the ATS score itself -- a
    # properly-weighted relevance algorithm, not "does this string appear."
    coverage = bm25_coverage(jd_skills, resume) if jd_skills else 0.5   # 0..1
    semantic, semantic_gaps = semantic_coverage(jd, resume) if jd.strip() else (0.5, [])

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
    semantic_10 = 2 + 8 * semantic
    overall = 0.3 * ats + 0.22 * recruiter + 0.28 * hm + 0.2 * semantic_10

    out.update({
        "ats": round(min(10, ats), 1),
        "recruiter": round(min(10, recruiter), 1),
        "hiring_manager": round(min(10, hm), 1),
        "semantic": round(min(10, semantic_10), 1),
        "overall": round(min(10, overall), 1),
        "highlights": sorted(have),
        "missing": missing,
        "semantic_gaps": semantic_gaps,
    })
    return out
