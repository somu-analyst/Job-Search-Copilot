"""Generate several resume versions for one job, score each, let the user pick.

One tailored summary is a guess. Three, scored side by side, is a decision:
you can SEE what a stronger reframe buys you in ATS points — and what it costs
in authenticity warnings — instead of trusting a slider blind.

Every variant is archived (src/resume_store) so months later you still know
exactly which resume went to which employer.
"""
from __future__ import annotations
import re

from . import ai, jd_match, resume as rz

# (label, intensity, what it's for)
PRESETS = [
    ("Conservative", 3, "Light touch — closest to your master resume. Safest."),
    ("Balanced", 5, "Emphasises the experience this JD asks for. Good default."),
    ("ATS-max", 8, "Strong reframe toward the JD. Highest keyword coverage, "
                   "highest over-claim risk — read the authenticity check."),
]


def _swap_summary(base_md: str, summary: str) -> str:
    return re.sub(r"(## Professional Summary\s*\n).*?(\n## )",
                  r"\1" + summary.strip() + r"\2", base_md, count=1, flags=re.S)


def score_resume(job_url: str, job_title: str, resume_md: str,
                 jd_override: str = "") -> dict:
    return jd_match.analyze(job_url, job_title, resume_override=resume_md,
                            jd_override=jd_override)


def build(job_url: str, job_title: str, company: str, *,
          emphasize: list[str] | None = None, jd_override: str = "",
          presets=None) -> list[dict]:
    """Return [{label, blurb, summary, resume_md, scores, warnings, mode}, ...].

    Always includes your untouched master resume as the baseline to compare
    against. Falls back to offline tailoring when the free models are capped, so
    this never dead-ends.
    """
    base_md = rz.load_cv_md()
    out = [{
        "label": "Master (untouched)",
        "blurb": "Your base resume, no tailoring. The baseline everything is measured against.",
        "summary": "",
        "resume_md": base_md,
        "scores": score_resume(job_url, job_title, base_md, jd_override),
        "warnings": [],
        "mode": "base",
    }]

    for label, intensity, blurb in (presets or PRESETS):
        band = ("Conservative" if intensity <= 3 else
                "Balanced" if intensity <= 7 else "Aggressive")
        s = ai.tailor_summary(job_url, job_title, company, band,
                              intensity=intensity, emphasize=emphasize or [])
        mode = "AI"
        if not s:
            s = ai.tailor_summary_offline(job_url, job_title, company)
            mode = "offline"
        if not s:
            continue
        md = _swap_summary(base_md, s)
        out.append({
            "label": label,
            "blurb": blurb,
            "summary": s,
            "resume_md": md,
            "scores": score_resume(job_url, job_title, md, jd_override),
            "warnings": ai.authenticity_check(s, base_md),
            "mode": mode,
        })
    return out


def rescore_edited(job_url: str, job_title: str, edited_summary: str,
                   jd_override: str = "") -> dict:
    """User hand-edited the summary → re-score and re-check authenticity."""
    base_md = rz.load_cv_md()
    md = _swap_summary(base_md, edited_summary)
    return {
        "resume_md": md,
        "scores": score_resume(job_url, job_title, md, jd_override),
        "warnings": ai.authenticity_check(edited_summary, base_md),
    }
