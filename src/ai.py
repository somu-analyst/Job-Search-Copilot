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


def _free_models() -> list[str]:
    """Every free (:free) text model live on OpenRouter — maximizes the number
    of fallbacks so a per-model rate-limit rarely exhausts all options."""
    global _model_cache
    if _model_cache:
        return _model_cache
    try:
        r = requests.get(MODELS_URL, timeout=15)
        ids = [m["id"] for m in r.json().get("data", [])
               if m.get("id", "").endswith(":free")
               and "image" not in m.get("id", "")
               and "lyria" not in m.get("id", "")]
        # keep the known-good ones first, then the rest
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


_last_error = ""


def last_error() -> str:
    return _last_error


def _chat(prompt: str, max_tokens=1400, passes=3) -> str:
    """Try every free model; repeat the sweep `passes` times before giving up.
    Free models are frequently busy (429) or return empty — retrying clears it."""
    global _last_error
    _last_error = ""
    key = _key()
    if not key:
        _last_error = "No OpenRouter key found in career-ops/.env"
        return ""
    models = _free_models()
    for attempt in range(passes):
        for model in models:
            try:
                r = requests.post(API, timeout=90,
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
            time.sleep(4)
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


def tailor_summary(url: str, title: str, company: str) -> str:
    """Rewritten 4-line Professional Summary targeted at this job ('' on failure)."""
    jd = fetch_jd(url) or f"(Job title: {title} at {company})"
    resume = load_cv_md()
    prompt = f"""Rewrite this resume's Professional Summary for the specific job below.
Rules: max 4 lines, factual (use ONLY facts present in the resume — never invent),
lead with the candidate's strongest matches to THIS job's requirements, plain text,
no emojis, no buzzword padding. Respond with ONLY the rewritten summary text.

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
