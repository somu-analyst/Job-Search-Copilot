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

import requests

from .resume import careerops_dir, load_cv_md
from .jd_match import fetch_jd

API = "https://openrouter.ai/api/v1/chat/completions"
# free-model fallback order (verified available on this key)
MODELS = ["qwen/qwen3-next-80b-a3b-instruct:free",
          "openai/gpt-oss-120b:free",
          "google/gemma-4-26b-a4b-it:free",
          "openai/gpt-oss-20b:free"]


def _key() -> str:
    env = careerops_dir() / ".env"
    if env.exists():
        m = re.search(r"OPENROUTER_API_KEY=(sk-or-[^\s]+)", env.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def _chat(prompt: str, max_tokens=1400) -> str:
    key = _key()
    if not key:
        return ""
    for model in MODELS:
        try:
            r = requests.post(API, timeout=90,
                              headers={"Authorization": f"Bearer {key}",
                                       "Content-Type": "application/json"},
                              json={"model": model, "max_tokens": max_tokens,
                                    "messages": [{"role": "user", "content": prompt}]})
            if r.status_code != 200:
                continue
            txt = r.json()["choices"][0]["message"]["content"]
            if txt and txt.strip():
                return txt.strip()
        except Exception:
            continue
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
    out = _chat(prompt, max_tokens=400)
    # sanity: reject if model returned junk or invented headers
    return out if out and len(out) < 1200 and "##" not in out else ""
