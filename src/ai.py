"""Free-model AI layer for the app — OpenRouter, $0 models, no Claude tokens.

Reads OPENROUTER_API_KEY from career-ops/.env (where it already lives) or
config/profile.yml api_keys.openrouter_key. Provides:
  analyze_job()    — LLM judgment of JD vs resume: score, strengths, gaps,
                     concrete resume tweaks
  tailor_summary() — rewrites the resume's Professional Summary for one job
"""
from __future__ import annotations
import json
import re
import time

import requests

from .resume import careerops_dir, load_cv_md
from .jd_match import fetch_jd

API = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
# static fallback order (used if the live list can't be fetched)
MODELS = ["qwen/qwen3-next-80b-a3b-instruct:free",
          "openai/gpt-oss-120b:free",
          "google/gemma-4-26b-a4b-it:free",
          "openai/gpt-oss-20b:free"]

_model_cache: list[str] = []


_SLOW = ("405b", "70b", "72b", "lyria", "image", "vision", "qwq", "reasoning",
         "thinking", "r1")  # giant/slow/rate-limited models — skip for speed


def _free_models() -> list[str]:
    """Fast free (:free) text models on OpenRouter, known-good ones first.
    Excludes giant/slow models that dominate rate-limits and add latency."""
    global _model_cache
    if _model_cache:
        return _model_cache
    try:
        r = requests.get(MODELS_URL, timeout=12)
        ids = [m["id"] for m in r.json().get("data", [])
               if m.get("id", "").endswith(":free")
               and not any(s in m["id"].lower() for s in _SLOW)]
        ordered = [m for m in MODELS if m in ids] + [m for m in ids if m not in MODELS]
        _model_cache = ordered or MODELS
    except Exception:
        _model_cache = MODELS
    return _model_cache


def _key() -> str:
    env = careerops_dir() / ".env"
    if env.exists():
        m = re.search(r"OPENROUTER_API_KEY=(sk-or-[^\s]+)", env.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def _gemini_key() -> str:
    """Gemini API key from config/profile.yml (api_keys.gemini_key) or the
    career-ops .env (GEMINI_API_KEY)."""
    from pathlib import Path
    import yaml as _yaml
    cfg = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
    if cfg.exists():
        try:
            k = ((_yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
                 .get("api_keys", {}) or {}).get("gemini_key", "")
            if k:
                return k
        except Exception:
            pass
    env = careerops_dir() / ".env"
    if env.exists():
        m = re.search(r"GEMINI_API_KEY=([A-Za-z0-9_\-]+)", env.read_text(encoding="utf-8"))
        if m and "your_" not in m.group(1):
            return m.group(1)
    return ""


def _gemini_chat(prompt: str, max_tokens=1400) -> str:
    """Google Gemini free tier (~1500 req/day) — used when OpenRouter is capped."""
    global _last_error
    key = _gemini_key()
    if not key:
        return ""
    for model in ("gemini-2.0-flash", "gemini-2.0-flash-lite"):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                timeout=90, headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens}})
            if r.status_code != 200:
                _last_error = f"gemini/{model}: HTTP {r.status_code}"
                continue
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            if txt and txt.strip():
                return txt.strip()
        except Exception as e:
            _last_error = f"gemini/{model}: {type(e).__name__}"
    return ""


_last_error = ""


def last_error() -> str:
    return _last_error


def _chat(prompt: str, max_tokens=1400, passes=2) -> str:
    """Try the best free models; repeat the sweep `passes` times before giving up.
    Capped to the top few models with a short timeout so it stays fast even when
    the free tier is busy (falls through to Gemini, then gives up gracefully)."""
    global _last_error
    _last_error = ""
    key = _key()
    # Use ALL fast free (:free) models — no paid ones. Giant/slow models are
    # already excluded in _free_models(), and we return on the first success,
    # so a wide list only helps: when the top models are rate-limited (429s
    # come back fast), it keeps falling through to the next free model.
    models = _free_models() if key else []
    for attempt in range(passes):
        for model in models:
            try:
                r = requests.post(API, timeout=40,
                                  headers={"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"},
                                  json={"model": model, "max_tokens": max_tokens,
                                        "messages": [{"role": "user", "content": prompt}]})
                if r.status_code == 429:
                    _last_error = f"{model}: rate-limited"
                    continue
                if r.status_code != 200:
                    _last_error = f"{model}: HTTP {r.status_code}"
                    continue
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and txt.strip():
                    return txt.strip()
                _last_error = f"{model}: empty response"
            except Exception as e:
                _last_error = f"{model}: {type(e).__name__}"
                continue
        if attempt < passes - 1:
            time.sleep(1.5)
    # OpenRouter exhausted/absent → try Gemini's separate free quota
    g = _gemini_chat(prompt, max_tokens)
    if g:
        return g
    if not key and not _gemini_key():
        _last_error = "No AI key found (OpenRouter in career-ops/.env or gemini_key in profile.yml)"
    return ""


def _json_block(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def analyze_job(url: str, title: str, company: str) -> dict:
    """LLM judgment. Returns {} if no key/JD problems; caller falls back."""
    jd = fetch_jd(url) or f"(Full JD unavailable. Job title: {title} at {company})"
    resume = load_cv_md()
    prompt = f"""You are a bank hiring panel simulator. Evaluate this candidate's resume
against the job. Respond with ONLY a JSON object, no prose:
{{"score_10": <float 1-10 overall fit>,
 "recruiter_view": "<1 sentence: 6-second skim impression>",
 "hiring_manager_view": "<1 sentence: domain-depth impression>",
 "strengths": ["<top 3 matches>"],
 "gaps": ["<top 3 things JD wants that resume lacks>"],
 "resume_tweaks": ["<3 concrete edits to this resume for THIS job>"]}}

JOB ({title} at {company}):
{jd[:6000]}

RESUME:
{resume[:6000]}"""
    return _json_block(_chat(prompt))


_LEVELS = {
    "Conservative": "Reword minimally — only reorder and lightly rephrase facts already "
                    "in the summary to surface the most relevant ones first. Change as "
                    "little as possible.",
    "Balanced": "Emphasize the candidate's experience that best matches this job's "
                "requirements, drawing only on facts stated anywhere in the resume.",
    "Aggressive": "Strongly reframe the summary around this job's top requirements, "
                  "foregrounding every relevant matching fact from the resume — but "
                  "still use ONLY facts present in the resume; invent nothing.",
}


def tailor_summary(url: str, title: str, company: str, level: str = "Balanced",
                   intensity: int = 5, emphasize: list | None = None) -> str:
    """Rewritten 4-line Professional Summary targeted at this job ('' on failure).
    intensity 1-10 = how hard to reframe. emphasize = user-chosen skills to weave in."""
    jd = fetch_jd(url) or f"(Job title: {title} at {company})"
    resume = load_cv_md()
    style = _LEVELS.get(level, _LEVELS["Balanced"])
    emph = ""
    if emphasize:
        emph = ("\nThe candidate CONFIRMS they have real experience with: "
                + ", ".join(emphasize)
                + ". Weave these in naturally where truthful — but if the resume gives "
                "no basis for one, leave it out rather than fabricate.")
    prompt = f"""Rewrite this resume's Professional Summary for the specific job below.
Tailoring intensity: {intensity} on a 1-10 scale ({level}). {style}
At intensity 1 change almost nothing; at 10 reframe the whole summary around the
job's top requirements. Scale your edits to match {intensity}.{emph}
Hard rules: max 4 lines; factual (use ONLY facts present in the resume — NEVER invent
skills, numbers, employers, or titles); plain text; no emojis; no hype words
(expert, world-class, guru, rockstar, 10x). Respond with ONLY the rewritten summary.

JOB ({title} at {company}):
{jd[:5000]}

RESUME:
{resume[:6000]}"""
    out = _chat(prompt, max_tokens=500)
    if not out:
        return ""
    # strip any accidental markdown header/label the model prepended
    out = re.sub(r"^\s*#+.*\n", "", out)
    out = re.sub(r"^\s*(professional summary|summary)\s*:?\s*\n", "", out, flags=re.I)
    return out.strip() if len(out) < 1500 else out[:1500]


def authenticity_check(tailored_summary: str, base_resume: str = "") -> list[str]:
    """Guard against over-claiming: flag skills/numbers/hype in the tailored
    summary that are NOT supported by the base resume. Empty list = clean."""
    from .jd_match import SKILLS
    base = (base_resume or load_cv_md()).lower()
    tl = (tailored_summary or "").lower()
    warns = []

    added = [s.strip() for s in SKILLS
             if s.strip() and s.strip() in tl and s.strip() not in base]
    if added:
        warns.append("Adds skills not found in your base resume — remove or verify: "
                     + ", ".join(sorted(set(added))[:8]))

    base_nums = set(re.findall(r"\d+\s?%|\$\s?\d[\d,.]*\s?[kmb]?", base))
    tl_nums = set(re.findall(r"\d+\s?%|\$\s?\d[\d,.]*\s?[kmb]?", tl))
    new_nums = tl_nums - base_nums
    if new_nums:
        warns.append("Introduces numbers/metrics not in your base resume — verify: "
                     + ", ".join(sorted(new_nums)[:8]))

    hype = ["expert", "world-class", "world class", "best-in-class", "guru", "ninja",
            "rockstar", "unparalleled", "revolutionary", "10x", "visionary",
            "genius", "unmatched", "flawless"]
    found = [h for h in hype if h in tl]
    if found:
        warns.append("Overhyped language a recruiter distrusts — soften: " + ", ".join(found))

    wc = len(tl.split())
    if wc > 90:
        warns.append(f"Summary is long ({wc} words) — trim to ~50-70 for a 6-second skim.")
    return warns


def tailor_summary_offline(url: str, title: str, company: str) -> str:
    """Deterministic ($0, always works) fallback when free models are capped.
    Front-loads the JD's matched skills into a one-line targeting sentence
    prepended to the resume's existing summary — factual, no fabrication."""
    from .jd_match import fetch_jd, SKILLS
    import re as _re
    resume = load_cv_md()
    m = _re.search(r"## Professional Summary\s*\n(.+?)(\n## )", resume, _re.S)
    base = (m.group(1).strip() if m else "").split("\n")[0]
    jd = (fetch_jd(url) or title).lower()
    resume_l = resume.lower()
    # skills the JD wants AND the resume proves
    matched = [s.upper() if s in ("sas", "sql", "aml", "kyc", "ccar", "cecl", "etl")
               else s.title()
               for s in SKILLS
               if s.strip() and s.strip() in jd and s.strip() in resume_l][:8]
    lead = (f"Targeting {title} at {company}: "
            f"direct match on {', '.join(matched)}. " if matched else "")
    return (lead + base).strip()
