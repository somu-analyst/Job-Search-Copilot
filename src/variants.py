"""Generate several resume versions for one job, score each, let the user pick.

One tailored summary is a guess. Three, scored side by side, is a decision:
you can SEE what a stronger reframe buys you in ATS points — and what it costs
in authenticity warnings — instead of trusting a slider blind.

Every variant is archived (src/resume_store) so months later you still know
exactly which resume went to which employer.
"""
from __future__ import annotations
import re
from concurrent.futures import ThreadPoolExecutor

from . import ai, corpus as cx, grounding, jd_match, resume as rz

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
    refs = grounding.references(base_md)   # parsed once, reused by every variant
    cv = cx.build(base_md)                 # same, for the cited path
    out = [{
        "label": "Master (untouched)",
        "blurb": "Your base resume, no tailoring. The baseline everything is measured against.",
        "summary": "",
        "resume_md": base_md,
        "scores": score_resume(job_url, job_title, base_md, jd_override),
        "warnings": [],
        "fabrication_rate": 0.0,   # by definition — it IS the ground truth
        "mode": "base",
    }]

    def _one(preset):
        label, intensity, blurb = preset
        band = ("Conservative" if intensity <= 3 else
                "Balanced" if intensity <= 7 else "Aggressive")
        # Preferred path: the model cites which resume facts it used, so the
        # check grades the pairing it intended instead of guessing at one.
        s, cited = ai.tailor_summary_cited(job_url, job_title, company, band,
                                           intensity=intensity,
                                           emphasize=emphasize or [], cv_corpus=cv)
        mode = "AI+cited"
        if not s:
            s, cited = ai.tailor_summary(job_url, job_title, company, band,
                                         intensity=intensity,
                                         emphasize=emphasize or []), []
            mode = "AI"
        if not s:
            s, cited = ai.tailor_summary_offline(job_url, job_title, company), []
            mode = "offline"
        if not s:
            return None
        md = _swap_summary(base_md, s)
        # Two guards, different failure modes: authenticity_check catches NEW
        # material (invented skills/numbers/hype), grounding catches claims
        # recombined out of real material — precisely when citations exist,
        # by best-match search when they don't.
        rep = (grounding.check_cited(cited, cv) if cited
               else grounding.check(s, base_md, refs=refs))
        return {
            "label": label,
            "blurb": blurb,
            "summary": s,
            "resume_md": md,
            "scores": score_resume(job_url, job_title, md, jd_override),
            "warnings": ai.authenticity_check(s, base_md) + rep.warnings(),
            "fabrication_rate": rep.rate,
            "claims_checked": rep.checked,
            "citations": cited,
            "mode": mode,
        }

    presets = list(presets or PRESETS)
    # The 3 presets are independent network-bound LLM calls with nothing to
    # share -- running them one after another was the single biggest chunk of
    # "why is this taking so long" (confirmed live: ~30s+ sequential). Threads
    # are the right tool here (not asyncio): each call is blocked on I/O
    # (requests.post), which releases the GIL, so 3 threads genuinely run
    # concurrently instead of taking turns.
    with ThreadPoolExecutor(max_workers=len(presets)) as pool:
        results = list(pool.map(_one, presets))
    out.extend(r for r in results if r is not None)
    return out


def rescore_edited(job_url: str, job_title: str, edited_summary: str,
                   jd_override: str = "") -> dict:
    """User hand-edited the summary → re-score and re-check authenticity."""
    base_md = rz.load_cv_md()
    md = _swap_summary(base_md, edited_summary)
    rep = grounding.check(edited_summary, base_md)
    return {
        "resume_md": md,
        "scores": score_resume(job_url, job_title, md, jd_override),
        "warnings": ai.authenticity_check(edited_summary, base_md) + rep.warnings(),
        "fabrication_rate": rep.rate,
    }
