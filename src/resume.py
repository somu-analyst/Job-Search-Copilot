"""Resume maker + apply kit — token-free, all inside Streamlit.

Reads your master resume (career-ops cv.md by default) and your career-ops
profile, and produces per-job artifacts:
  - tailored ATS-safe resume as HTML (open → Ctrl+P → save as PDF)
  - templated cover letter (.txt) with job/company merged in
  - copy-paste "apply kit" blocks (contact, visa answer, elevator pitch)
  - one-click queue of a job URL into career-ops' pipeline for AI tailoring

Paths can be overridden in config/profile.yml:
  resume:
    cv_path: "C:/path/to/cv.md"
    careerops_dir: "C:/Users/srini/career-ops/career-ops"
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

import markdown as _md

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
_DEFAULT_CO = Path("C:/Users/srini/career-ops/career-ops")


def _cfg() -> dict:
    if yaml and _CFG.exists():
        try:
            return yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def careerops_dir() -> Path:
    return Path(_cfg().get("resume", {}).get("careerops_dir", _DEFAULT_CO))


def cv_path() -> Path:
    return Path(_cfg().get("resume", {}).get("cv_path", careerops_dir() / "cv.md"))


def load_cv_md() -> str:
    p = cv_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "# Resume not found\nSet resume.cv_path in config/profile.yml"


def load_co_profile() -> dict:
    p = careerops_dir() / "config" / "profile.yml"
    if yaml and p.exists():
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


_STYLE = """
body{font-family:Calibri,Arial,sans-serif;max-width:8.2in;margin:0 auto;
     padding:24px 32px;color:#1a1a1a;font-size:10.6pt;line-height:1.35}
h1{font-size:17pt;margin:0 0 2px;color:#0f2a4a}
h2{font-size:11.5pt;border-bottom:1.5px solid #0f2a4a;color:#0f2a4a;
   margin:14px 0 6px;padding-bottom:2px;text-transform:uppercase;letter-spacing:.4px}
h3{font-size:10.8pt;margin:10px 0 2px}
ul{margin:4px 0 8px;padding-left:18px} li{margin:2px 0}
p{margin:4px 0} strong{color:#0f2a4a}
.target{background:#eef4fb;border-left:3px solid #0f2a4a;padding:6px 10px;
        margin:8px 0;font-size:10.2pt}
@media print{.target{-webkit-print-color-adjust:exact}}
"""


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002190-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0001F1E6-\U0001F1FF]+")


def _ats_clean(text: str) -> str:
    """Strip emojis/symbols ATS parsers choke on; tidy leftover separators."""
    text = _EMOJI_RE.sub("", text)
    text = text.replace("·", "|").replace("★", "").replace("→", "-")
    return re.sub(r"[ \t]{2,}", " ", text)


def tailored_resume_html(job_title: str = "", company: str = "") -> str:
    """Master resume → standalone ATS-safe HTML (no emojis, no gimmicks)."""
    md_text = load_cv_md()
    # strip html comments (TODO markers etc.) and emoji
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)
    md_text = _ats_clean(md_text)
    body = _md.markdown(md_text, extensions=["extra"])
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Resume - {_ats_clean(job_title) or 'Master'}</title>"
            f"<style>{_STYLE}</style></head><body>{body}</body></html>")


def matched_keywords_for(title: str) -> list[str]:
    from .sources import POSITIVE
    t = (title or "").lower()
    return sorted({p.upper() if p in ("sas", "aml", "kyc", "etl", "mis", "bsa", "ccar", "cecl")
                   else p.title() for p in POSITIVE if p in t})


def cover_letter(job_title: str, company: str) -> str:
    co = load_co_profile()
    cand = co.get("candidate", {})
    narr = co.get("narrative", {})
    name = cand.get("full_name", "Srinivasa Rao Somu")
    powers = narr.get("superpowers", [])[:3]
    bullets = "\n".join(f"  - {p}" for p in powers) if powers else ""
    today = datetime.now().strftime("%B %d, %Y")
    return f"""{today}

Dear {company or 'Hiring'} Team,

I am writing to apply for the {job_title or 'open'} position at {company or 'your organization'}.
{narr.get('headline', 'Senior Fraud & Credit Risk Data Analytics professional with 13+ years in Financial Services.')}

What I bring to this role:
{bullets}

My background spans Wells Fargo (AML/fraud compliance analytics), Citi (CCAR/CECL
stress testing, team leadership), HSBC ($23B sub-prime mortgage portfolio,
collections and loss-mitigation analytics) and IBM/Dun & Bradstreet (risk data)
— with deep production experience in SAS, SAS Viya, Python, and SQL, and a track
record of automating regulatory reporting and cutting false positives.

I would welcome the chance to discuss how this experience maps to your team's
goals. Thank you for your consideration.

Sincerely,
{name}
{cand.get('phone', '')} | {cand.get('email', '')}
{cand.get('linkedin', '')}

[NOTE: review before sending — personalize the first paragraph with one company-specific line.]
"""


def apply_kit() -> dict:
    """Copy-paste blocks for filling application forms fast."""
    co = load_co_profile()
    cand = co.get("candidate", {})
    narr = co.get("narrative", {})
    return {
        "Contact block": (
            f"{cand.get('full_name', '')}\n{cand.get('location', '')}\n"
            f"{cand.get('phone', '')}\n{cand.get('email', '')}\n{cand.get('linkedin', '')}"
        ),
        "Work authorization answer": (
            "I am currently employed in the United States on an H-1B visa and "
            "will require H-1B transfer sponsorship. I am available to start "
            "after a standard notice period."
        ),
        "Elevator pitch (about-me box)": (
            narr.get("headline", "") + ". " + narr.get("exit_story", "")
        ).strip(". ") + ".",
        "Current employer line": "Wells Fargo — Senior Consultant, AML/Fraud Compliance Analytics (06/2023–present, contract)",
    }


def queue_for_ai_tailoring(url: str) -> str:
    """Append the job URL to career-ops data/pipeline.md (## Pending) so the
    $0 OpenRouter lane (or a Claude session) evaluates + tailors it."""
    p = careerops_dir() / "data" / "pipeline.md"
    if not p.exists():
        return "career-ops pipeline.md not found — check resume.careerops_dir"
    text = p.read_text(encoding="utf-8")
    if url in text:
        return "Already queued in career-ops."
    text = text.replace("## Pending", f"## Pending\n\n- [ ] {url}", 1)
    p.write_text(text, encoding="utf-8")
    return "Queued ✓ — career-ops will evaluate & tailor on its next run."
