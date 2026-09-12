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
_DEMO_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.demo.yml"
_DEFAULT_CO = Path("C:/Users/srini/career-ops/career-ops")


def _cfg() -> dict:
    # profile.yml is gitignored (your real keywords/keys/candidate info). A
    # fresh clone/cloud deploy with none falls back to the committed
    # profile.demo.yml (synthetic candidate) so the app isn't blank.
    p = _CFG if _CFG.exists() else _DEMO_CFG
    if yaml and p.exists():
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


_LOCAL_CV = Path(__file__).resolve().parent.parent / "resume" / "cv.md"
_DEMO_CV = Path(__file__).resolve().parent.parent / "resume" / "cv.demo.md"


def careerops_dir() -> Path:
    return Path(_cfg().get("resume", {}).get("careerops_dir", _DEFAULT_CO))


def cv_path() -> Path:
    """Resolve the resume file. Priority:
    1. resume.cv_path in config/profile.yml (explicit override)
    2. ./resume/cv.md  (this repo — where any user drops their own)
    3. career-ops/cv.md (if this is running alongside career-ops)
    """
    cfg = _cfg().get("resume", {}).get("cv_path", "")
    if cfg:
        return Path(cfg)
    if _LOCAL_CV.exists():
        return _LOCAL_CV
    co_cv = careerops_dir() / "cv.md"
    if co_cv.exists():
        return co_cv
    return _DEMO_CV


def load_cv_md() -> str:
    p = cv_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ("# Add your resume\nSave your resume as Markdown to `resume/cv.md` "
            "(or set resume.cv_path in config/profile.yml).")


def load_co_profile() -> dict:
    """Candidate/narrative data. Prefers this repo's config/profile.yml
    ('candidate:' block); falls back to a co-located career-ops profile."""
    local = _cfg()
    if local.get("candidate"):
        return local
    p = careerops_dir() / "config" / "profile.yml"
    if yaml and p.exists():
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return local


# ATS-safe by construction: single column, no tables, no floats, no graphics,
# no text in images, no headers/footers. Everything a parser needs is plain
# semantic HTML — the styling only affects how a HUMAN sees it.
_DENSITY = {
    #            pad,                 body,     line-height, h2margin,    h3margin,   ulmargin,  limargin, page-margin, h1
    "normal": ("26px 34px 30px", "10.4pt", "1.42", "17px 0 7px", "11px 0 1px", "5px 0 9px", "3px 0", "0.5in", "20pt"),
    "compact": ("18px 28px 20px", "9.3pt", "1.28", "10px 0 4px", "7px 0 1px", "3px 0 6px", "1px 0", "0.4in", "17pt"),
    # Only used by one_page_resume() as the last lever after content
    # trimming, never the general "compact" download people already use --
    # this is measurably tighter, on purpose, since it only kicks in when
    # trimming down to the bullet floor still wasn't enough on its own.
    "ultra": ("12px 22px 14px", "8.6pt", "1.16", "7px 0 2px", "5px 0 1px", "2px 0 4px", "0px 0", "0.32in", "15pt"),
}


def _style(compact: bool = False, density: str | None = None) -> str:
    """compact=True (legacy bool, kept for existing callers) == density
    "compact". density="ultra" is tighter still -- see _DENSITY. A genuinely
    tighter layout (smaller type, less white space, no gap before each new
    employer), not just a smaller font on the same spacing, which barely
    helps. Content is untouched by this function either way; squeezing
    truly long history onto one page also needs trimming which bullets to
    include -- see one_page_resume() for the function that does both."""
    key = density or ("compact" if compact else "normal")
    (pad, body_size, line_height, h2_margin, h3_margin, ul_margin, li_margin,
     page_margin, h1_size) = _DENSITY[key]
    return f"""
@page{{margin:{page_margin}}}
body{{font-family:Calibri,Carlito,Arial,sans-serif;max-width:8.0in;margin:0 auto;
     padding:{pad};color:#1F2328;font-size:{body_size};line-height:{line_height}}}

/* Name + contact line */
h1{{font-size:{h1_size};margin:0;color:#111418;font-weight:700;letter-spacing:-.4px}}
h1 + p{{margin:3px 0 0;font-size:{'8.4pt' if key == 'ultra' else '9pt' if key == 'compact' else '10pt'};color:#3A4048}}
h1 + p strong{{color:#111418;font-weight:600;letter-spacing:.2px}}
h1 + p a{{color:#3A4048;text-decoration:none;border-bottom:1px solid #C9CFD6}}

/* Section headings: a rule the eye can lock onto while skimming.
   Plain black on purpose — no accent color, so it reads identically after
   any portal re-saves/re-prints it, and never looks "off" on a screen that
   renders color differently. */
h2{{font-size:{'8.6pt' if key == 'ultra' else '9.8pt'};color:#111418;font-weight:700;text-transform:uppercase;
   letter-spacing:1.1px;margin:{h2_margin};padding-bottom:3px;
   border-bottom:1px solid #D7DCE2}}

/* Employer — role */
h3{{font-size:{'9.4pt' if key == 'ultra' else '10.2pt' if key == 'compact' else '11pt'};margin:{h3_margin};color:#111418;font-weight:700}}
/* Dates line (italic in the markdown) */
h3 + p em{{color:#5B6472;font-size:{'8.4pt' if key == 'ultra' else '9.4pt'};font-style:normal;letter-spacing:.2px}}

ul{{margin:{ul_margin};padding-left:{'13px' if key == 'ultra' else '16px'}}}
li{{margin:{li_margin};padding-left:2px}}
p{{margin:{'2px 0' if key == 'ultra' else '3px 0' if key == 'compact' else '5px 0'}}}

/* Bold is EARNED, not decoration: only the strongest outcome per role carries
   it, so a skimming recruiter's eye lands on results instead of wallpaper. */
strong{{color:#111418;font-weight:700}}

@media print{{
  body{{padding:0}}
  h2{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  h3{{page-break-after:avoid}} ul{{page-break-inside:avoid}}
}}
"""


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002190-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0001F1E6-\U0001F1FF]+")


def _ats_clean(text: str) -> str:
    """Strip emojis/symbols ATS parsers choke on; tidy leftover separators."""
    text = _EMOJI_RE.sub("", text)
    text = text.replace("·", "|").replace("★", "").replace("→", "-")
    return re.sub(r"[ \t]{2,}", " ", text)


def _html_from_md(md_text: str, job_title: str = "", compact: bool = False,
                  density: str | None = None) -> str:
    """Shared by tailored_resume_html() (loads cv.md itself) and
    one_page_resume() (passes already-bullet-trimmed text, density="ultra")
    -- one rendering path, so trimmed and untrimmed resumes are never a
    second copy to drift."""
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)   # TODO markers etc.
    md_text = _ats_clean(md_text)
    # Header fix: in cv.md the **title** line and the contact line are adjacent,
    # so Markdown merges them into one paragraph that wraps mid-phrase. Force a
    # hard break (two trailing spaces) after the first bold line that is
    # immediately followed by a non-blank line, so they stack cleanly.
    md_text = re.sub(r"(\*\*[^\n]+\*\*)\n(?=\S)", r"\1  \n", md_text, count=1)
    body = _md.markdown(md_text, extensions=["extra"])
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Resume - {_ats_clean(job_title) or 'Master'}</title>"
            f"<style>{_style(compact, density)}</style></head><body>{body}</body></html>")


def _pdf_from_html(html_doc: str) -> bytes:
    from io import BytesIO
    from xhtml2pdf import pisa
    buf = BytesIO()
    result = pisa.CreatePDF(html_doc, dest=buf)
    return b"" if result.err else buf.getvalue()


def tailored_resume_html(job_title: str = "", company: str = "",
                         summary_override: str = "", compact: bool = False) -> str:
    """Master resume → standalone ATS-safe HTML (no emojis, no gimmicks).
    summary_override replaces the Professional Summary section (AI tailoring).
    compact=True fits more onto one page via tighter spacing/type -- content
    is unchanged, so a genuinely long history may still run past one page.
    (For a GENUINE one-page guarantee that trims content, see one_page_resume().)"""
    md_text = load_cv_md()
    if summary_override:
        md_text = re.sub(r"(## Professional Summary\s*\n).*?(\n## )",
                         r"\1" + "\n" + summary_override.strip() + "\n" + r"\2",
                         md_text, count=1, flags=re.S)
    return _html_from_md(md_text, job_title, compact)


def tailored_resume_pdf(job_title: str = "", company: str = "",
                        summary_override: str = "", compact: bool = False) -> bytes:
    """Same resume as tailored_resume_html(), rendered straight to PDF bytes --
    a real download instead of the HTML-then-Ctrl+P-yourself step. xhtml2pdf
    (pure Python, no external binary/browser needed -- works the same locally
    and on the Oracle VM) reads the identical HTML+CSS, so this is always in
    sync with the HTML version by construction, never a second copy to drift."""
    return _pdf_from_html(tailored_resume_html(job_title, company, summary_override, compact))


def tailored_resume_docx(job_title: str = "", company: str = "",
                         summary_override: str = "", compact: bool = False) -> bytes:
    """Same resume, as a real .docx -- some ATS portals and recruiters still
    specifically ask for Word, not PDF. htmldocx converts the identical
    HTML+CSS this file already produces, so it's the same single source of
    truth as the HTML/PDF versions, not a second copy that can drift."""
    from io import BytesIO
    from docx import Document
    from htmldocx import HtmlToDocx
    html_doc = tailored_resume_html(job_title, company, summary_override, compact)
    document = Document()
    HtmlToDocx().add_html_to_document(html_doc, document)
    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()


def _pdf_page_count(pdf_bytes: bytes) -> int:
    """Count real page objects (/Type /Page) in the raw PDF bytes -- NOT
    /Type /Pages, the page-tree root, hence the negative lookahead. Avoids
    adding a PDF-parsing dependency (pypdf/pdfplumber) just to count pages;
    xhtml2pdf's reportlab backend writes one /Type/Page object per page,
    reliably, for documents this simple (no page-object reuse/XObjects)."""
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf_bytes))


def _parse_experience_bullets(md_text: str) -> list[dict]:
    """['## Experience'] -> [{header, dates, bullets: [str, ...]}, ...], in
    document order (most recent role first, as cv.md already lists it)."""
    m = re.search(r"## Experience\s*\n(.*?)(?=\n## |\Z)", md_text, re.S)
    if not m:
        return []
    roles = []
    for block in re.split(r"(?=^### )", m.group(1), flags=re.M):
        if not block.strip().startswith("###"):
            continue
        hm = re.match(r"(### .+?)\n(\*.+?\*)?\n?", block)
        if not hm:
            continue
        bullets = re.findall(r"^- .+$", block, re.M)
        roles.append({"header": hm.group(1), "dates": hm.group(2) or "",
                      "bullets": bullets})
    return roles


def _section_bullets(md_text: str, heading: str) -> list[str]:
    m = re.search(rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)", md_text, re.S)
    return re.findall(r"^- .+$", m.group(1), re.M) if m else []


def _jd_relevance(bullet: str, jd_words: set) -> float:
    """Higher = keep first. Reuses the same SKILLS vocabulary jd_match.py
    already scores JDs against, so "relevant to THIS job" means the same
    thing here as it does everywhere else in the app."""
    from .jd_match import SKILLS
    t = bullet.lower()
    hits = sum(1 for k in SKILLS if k.strip() in t and k.strip() in jd_words)
    has_metric = bool(re.search(r"\d+%|\$\d", bullet))
    return hits * 2 + (1 if has_metric else 0)


def one_page_resume(job_title: str, company: str, jd_text: str = "",
                    summary_override: str = "") -> tuple[bytes, list[str], bool]:
    """A GENUINELY one-page PDF, not just tighter CSS -- trims bullets, JD-
    least-relevant first within a fixed safety order, re-rendering and
    re-counting pages until it actually fits (or the floor is hit).

    Cut order (safest first, never touches Summary/Skills/Education/header):
      1. Awards & Achievements (whole section)
      2. Projects (whole section)
      3. Oldest 2 roles' bullets, down to a floor of 2 each
      4. Newest 2 roles' bullets, down to a floor of 3 each
    Within each tier, the least JD-relevant bullet goes first -- keeping
    whatever actually matches THIS job's requirements longest.

    Returns (pdf_bytes, trimmed_bullet_texts, fits_one_page). fits_one_page
    is False only if even the floor wasn't enough -- the resume is
    genuinely that long; the caller should say so rather than claim success.
    """
    md_text = load_cv_md()
    if summary_override:
        md_text = re.sub(r"(## Professional Summary\s*\n).*?(\n## )",
                         r"\1" + "\n" + summary_override.strip() + "\n" + r"\2",
                         md_text, count=1, flags=re.S)

    jd_words = (jd_text or "").lower()
    roles = _parse_experience_bullets(md_text)
    awards = _section_bullets(md_text, "Awards & Achievements")
    projects = _section_bullets(md_text, "Projects")

    # Priority queue of (tier, bullet_text, role_header_or_None).
    # Tiers 1-4 stop at a comfortable floor (2 bullets/oldest role, 3/newest)
    # -- a resume that fits there never touches tiers 5/6, which push to an
    # absolute floor of 1/2 as a genuine last resort, only reached if even
    # ultra-tight typography plus tiers 1-4 still isn't enough.
    FLOOR_OLD, FLOOR_NEW = 2, 3
    LAST_RESORT_OLD, LAST_RESORT_NEW = 1, 2
    queue: list[tuple[int, float, str, str | None]] = []
    for b in awards:
        queue.append((1, _jd_relevance(b, jd_words), b, None))
    for b in projects:
        queue.append((2, _jd_relevance(b, jd_words), b, None))
    n = len(roles)
    for i, role in enumerate(roles):
        oldest_half = i >= (n + 1) // 2   # later in the list = older role
        tier = 3 if oldest_half else 4
        floor = FLOOR_OLD if oldest_half else FLOOR_NEW
        last_floor = LAST_RESORT_OLD if oldest_half else LAST_RESORT_NEW
        bullets = role["bullets"]
        for b in bullets[floor:]:
            queue.append((tier, _jd_relevance(b, jd_words), b, role["header"]))
        for b in bullets[last_floor:floor]:
            queue.append((tier + 4, _jd_relevance(b, jd_words), b, role["header"]))
    queue.sort(key=lambda x: (x[0], x[1]))   # tier first, then least-relevant first

    trimmed: list[str] = []
    dropped: set[str] = set()
    qi = 0
    for _ in range(len(queue) + 1):   # +1: always render at least once, untrimmed
        candidate = md_text
        for line in dropped:
            candidate = candidate.replace(line + "\n", "", 1)
        html_doc = _html_from_md(candidate, job_title, density="ultra")
        pdf_bytes = _pdf_from_html(html_doc)
        if _pdf_page_count(pdf_bytes) <= 1 or qi >= len(queue):
            return pdf_bytes, trimmed, _pdf_page_count(pdf_bytes) <= 1
        _, _, line, _ = queue[qi]
        qi += 1
        dropped.add(line)
        trimmed.append(line.lstrip("- ").strip())
    return pdf_bytes, trimmed, _pdf_page_count(pdf_bytes) <= 1


def matched_keywords_for(title: str) -> list[str]:
    from .sources import POSITIVE
    t = (title or "").lower()
    return sorted({p.upper() if p in ("sas", "aml", "kyc", "etl", "mis", "bsa", "ccar", "cecl")
                   else p.title() for p in POSITIVE if p in t})


def cover_letter(job_title: str, company: str) -> str:
    co = load_co_profile()
    cand = co.get("candidate", {})
    narr = co.get("narrative", {})
    name = cand.get("full_name", "Your Name")
    powers = narr.get("superpowers", [])[:3]
    bullets = "\n".join(f"  - {p}" for p in powers) if powers else ""
    today = datetime.now().strftime("%B %d, %Y")
    return f"""{today}

Dear {company or 'Hiring'} Team,

I am writing to apply for the {job_title or 'open'} position at {company or 'your organization'}.
{narr.get('headline', 'Add your headline in config/profile.yml (narrative.headline).')}

What I bring to this role:
{bullets}

{narr.get('exit_story', 'Add your background summary in config/profile.yml (narrative.exit_story).')}

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
        "Current employer line": cand.get("current_employer_line", ""),
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
