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


def gemini_key_problem(k: str) -> str:
    """'' if the key is usable, else a note explaining what's up with it.

    Google issues TWO key formats now:
      AIzaSy…  legacy, 39 chars — works everywhere
      AQ.…     new format — legitimate, but widely reported to fail against
               third-party integrations and to come back 429 RESOURCE_EXHAUSTED
               ('check your plan and billing details') even on a free-tier
               project that has used nothing.
    We do NOT reject AQ. keys — plenty of them work, and rejecting by prefix
    would lock out users whose key is fine. We just don't let the misleading
    billing error stand unexplained: this is a key-format issue, not a billing
    one, and no amount of billing fixes it.
    """
    if not k:
        return ""
    if k.startswith("AQ."):
        return ("New-format ('AQ.') Gemini key. These often return 429 "
                "RESOURCE_EXHAUSTED even on an unused free tier — a known "
                "compatibility issue, NOT a billing problem. If Gemini keeps "
                "failing, generate a legacy 'AIzaSy…' key from a different "
                "Google Cloud project. OpenRouter is the primary lane anyway; "
                "Gemini is only the fallback.")
    return ""


def _gemini_key() -> str:
    """Gemini API key from config/profile.yml (api_keys.gemini_key) or the
    career-ops .env (GEMINI_API_KEY). Any format is accepted — we try the key
    and let it speak for itself."""
    from pathlib import Path
    import yaml as _yaml
    raw = ""
    cfg = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
    if cfg.exists():
        try:
            raw = ((_yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
                   .get("api_keys", {}) or {}).get("gemini_key", "") or ""
        except Exception:
            raw = ""
    if not raw:
        env = careerops_dir() / ".env"
        if env.exists():
            m = re.search(r"GEMINI_API_KEY=([A-Za-z0-9_.\-]+)",
                          env.read_text(encoding="utf-8"))
            if m and "your_" not in m.group(1):
                raw = m.group(1)
    return raw


def _kimchi_key() -> str:
    from pathlib import Path
    try:
        import yaml
        cfg = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
        return ((yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
                .get("api_keys", {}) or {}).get("kimchi_key", "") or ""
    except Exception:
        return ""


# Kimchi (Cast AI) — OpenAI-compatible, PAID per token. Ordered cheapest/fastest
# first: we only get here when every free model is capped, so spend the credit
# conservatively. Some models return empty content (reasoning-only), so the
# caller must fall through on empty rather than treating it as success.
KIMCHI_URL = "https://llm.kimchi.dev/openai/v1/chat/completions"
KIMCHI_MODELS = ["deepseek-v4-flash", "minimax-m3", "kimi-k2.7"]


def _kimchi_chat(prompt: str, max_tokens: int = 1400) -> str:
    key = _kimchi_key()
    if not key:
        return ""
    global _last_error
    for model in KIMCHI_MODELS:
        try:
            r = requests.post(KIMCHI_URL, timeout=60,
                              headers={"Authorization": f"Bearer {key}",
                                       "Content-Type": "application/json"},
                              json={"model": model, "max_tokens": max_tokens,
                                    "messages": [{"role": "user",
                                                  "content": prompt}]})
            if r.status_code != 200:
                _last_error = f"kimchi/{model}: HTTP {r.status_code}"
                continue
            txt = (r.json()["choices"][0]["message"].get("content") or "").strip()
            if txt:
                return txt
            _last_error = f"kimchi/{model}: empty"
        except Exception as e:
            _last_error = f"kimchi/{model}: {type(e).__name__}"
    return ""


def gemini_status() -> str:
    """Human-readable state of the Gemini fallback lane ('' when it's fine)."""
    from pathlib import Path
    import yaml as _yaml
    cfg = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
    try:
        raw = ((_yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
               .get("api_keys", {}) or {}).get("gemini_key", "") or ""
    except Exception:
        raw = ""
    return gemini_key_problem(raw)


def _gemini_chat(prompt: str, max_tokens=1400) -> str:
    """Google Gemini free tier (~1500 req/day).

    Uses the "-latest" model aliases, not a pinned version -- gemini-2.0-flash
    and gemini-2.0-flash-lite (the previously hardcoded names) were BOTH gone
    from Google's live model catalog (confirmed live via the ListModels API,
    2026-09-11: key auth was fine, 200 OK, the models just don't exist
    anymore -- every call was silently 404ing, not the "AQ. key" issue the
    old comment blamed). The alias tracks whatever Google currently serves as
    its recommended flash model, so this can't go stale the same way again."""
    global _last_error
    key = _gemini_key()
    if not key:
        return ""
    for model in ("gemini-flash-latest", "gemini-flash-lite-latest"):
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


def _openrouter_chat(prompt: str, max_tokens: int, passes: int, key: str) -> str:
    global _last_error
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
    return ""


def _chat(prompt: str, max_tokens=1400, passes=2) -> str:
    """Gemini first, then the OpenRouter free sweep, then paid Kimchi as a last
    resort. Gemini first by explicit choice (2026-09-11): Google's free tier
    trains on submitted prompts (resume content included) -- putting it first
    means MORE traffic goes through a training-enabled free tier, not less;
    this was a known, flagged trade-off, not an oversight."""
    global _last_error
    _last_error = ""
    key = _key()

    g = _gemini_chat(prompt, max_tokens)
    if g:
        return g

    out = _openrouter_chat(prompt, max_tokens, passes, key)
    if out:
        return out

    # Kimchi (Cast AI) — PAID, prepaid credit. Only reached when both free
    # tiers above are genuinely exhausted, so it's a safety net, not the default.
    k = _kimchi_chat(prompt, max_tokens)
    if k:
        return k

    if not key and not _gemini_key() and not _kimchi_key():
        _last_error = ("No AI key found (OpenRouter in career-ops/.env, or "
                       "gemini_key / kimchi_key in config/profile.yml)")
    return ""


def _json_block(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def analyze_job(url: str, title: str, company: str, jd_override: str = "",
                resume_override: str = "") -> dict:
    """LLM judgment. Returns {} if no key/JD problems; caller falls back."""
    jd = jd_override or fetch_jd(url) or f"(Full JD unavailable. Job title: {title} at {company})"
    resume = resume_override or load_cv_md()
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
Opening sentence structure (standard for senior/finance-risk resumes): title,
years of experience, then 3-4 skills that directly match this job's top
requirements — not a generic list.
Every sentence should show IMPACT (what changed because of the work — capital/
risk reduced, losses avoided, time saved), not just a list of tools or tasks.
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


def tailor_summary_cited(url: str, title: str, company: str, level: str = "Balanced",
                         intensity: int = 5, emphasize: list | None = None,
                         cv_corpus=None) -> tuple[str, list[dict]]:
    """Same as `tailor_summary`, but the model picks from numbered resume facts
    and must name the ones behind each sentence.

    Returns (summary, [{"text": ..., "refs": ["cv-bullet-004", ...]}, ...]).
    A citation turns validation from "does any of 67 facts resemble this?" into
    "does THIS fact support it?" — which is the only way to catch a claim that
    is built from real material but attributes it to the wrong employer.

    Returns ("", []) on failure so callers can fall back to `tailor_summary`.
    """
    from . import corpus as cx
    cv = cv_corpus or cx.build_from_resume()
    if not cv.items:
        return "", []
    jd = fetch_jd(url) or f"(Job title: {title} at {company})"
    style = _LEVELS.get(level, _LEVELS["Balanced"])
    emph = ""
    if emphasize:
        emph = ("\nThe candidate CONFIRMS real experience with: " + ", ".join(emphasize)
                + ". Prefer facts covering these where they exist; if no fact "
                "supports one, leave it out rather than fabricate.")
    prompt = f"""Write a Professional Summary for the job below, using ONLY the
numbered resume facts. Tailoring intensity: {intensity}/10 ({level}). {style}{emph}

Rules:
- Every sentence must be supported by the facts you cite for it. Do not merge
  facts from two different employers into one claim.
- Never state a number, employer, title or tool that is not in a cited fact.
- Opening sentence: title, years of experience, then 3-4 skills that directly
  match this job's top requirements — not a generic list (standard structure
  for senior/finance-risk resumes).
- Every sentence should show IMPACT (what changed because of the work —
  capital/risk reduced, losses avoided, time saved), not just tools or tasks.
- 3-4 sentences, plain text, no hype words (expert, world-class, guru, 10x).

Respond with ONLY this JSON:
{{"sentences": [{{"text": "<one sentence>", "refs": ["cv-bullet-003", "cv-skill-011"]}}]}}

JOB ({title} at {company}):
{jd[:4000]}

RESUME FACTS:
{cv.render_for_prompt()}"""
    data = _json_block(_chat(prompt, max_tokens=700))
    sents = []
    for s in (data.get("sentences") or []):
        if not isinstance(s, dict):
            continue
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        refs = [str(r).strip().strip("[]").lower()
                for r in (s.get("refs") or []) if str(r).strip()]
        sents.append({"text": text, "refs": refs})
    if not sents:
        return "", []
    summary = " ".join(s["text"] for s in sents)
    return (summary[:1500], sents)


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

    # The SKILLS list can't know every technology. Anything that LOOKS like a tool
    # or proper noun (capitalised mid-sentence, or an all-caps acronym) and isn't
    # in the base resume is an invented claim — e.g. a model adding "Kubernetes"
    # sailed straight through when we only checked the known vocabulary.
    _STOP = {"i", "a", "the", "and", "or", "of", "in", "for", "with", "to", "at",
             "on", "as", "by", "an", "my"}
    # the candidate's own name tokens are never invented claims — read them from
    # the (gitignored) profile so this generalises instead of hardcoding a name
    try:
        import yaml as _yaml
        _cfgp = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
        _cand = (_yaml.safe_load(_cfgp.read_text(encoding="utf-8")) or {}).get("candidate", {})
        _STOP |= {w.lower() for v in (_cand.get("name"), _cand.get("full_name"))
                  if v for w in str(v).split()}
    except Exception:
        pass
    proper = re.findall(r"\b(?:[A-Z]{2,}|[A-Z][a-zA-Z0-9+.#/-]{2,})\b",
                        tailored_summary or "")
    # drop the first word of each sentence — capitalisation there means nothing
    starts = {m.group(1) for m in
              re.finditer(r"(?:^|[.!?]\s+)([A-Z][\w+.#/-]*)", tailored_summary or "")}
    invented = sorted({p for p in proper
                       if p not in starts
                       and p.lower() not in _STOP
                       and p.lower() not in base})
    if invented:
        warns.append("Names tools/terms that appear nowhere in your resume — "
                     "remove unless you can defend them: " + ", ".join(invented[:8]))

    # '87 percent' must be caught as readily as '87%' — a model that spells the
    # unit out would otherwise smuggle an invented metric straight through.
    _NUM = r"\d+(?:\.\d+)?\s?(?:%|percent)|\$\s?\d[\d,.]*\s?[kmb]?"
    base_nums = {n.replace("percent", "%").replace(" ", "")
                 for n in re.findall(_NUM, base)}
    tl_nums = {n.replace("percent", "%").replace(" ", "")
               for n in re.findall(_NUM, tl)}
    new_nums = tl_nums - base_nums
    if new_nums:
        warns.append("Introduces numbers/metrics not in your base resume — verify: "
                     + ", ".join(sorted(new_nums)[:8]))

    # Only flag hype the TAILORING introduced. Wording already in the base resume
    # is the candidate's own voice — flagging it ("expert", which his own summary
    # uses) is a false alarm, and false alarms teach you to ignore the real ones.
    hype = ["expert", "world-class", "world class", "best-in-class", "guru", "ninja",
            "rockstar", "unparalleled", "revolutionary", "10x", "visionary",
            "genius", "unmatched", "flawless", "seasoned", "proven track record"]
    found = [h for h in hype if h in tl and h not in base]
    if found:
        warns.append("Overhyped language the tailoring added (not in your resume) — "
                     "soften: " + ", ".join(found))

    wc = len(tl.split())
    if wc > 90:
        warns.append(f"Summary is long ({wc} words) — trim to ~50-70 for a 6-second skim.")
    return warns


def tailor_summary_offline(url: str, title: str, company: str) -> str:
    """Deterministic ($0, always works) fallback when free models are capped.
    Appends the JD's matched skills as a plain closing sentence on the
    resume's existing summary — factual, no fabrication, phrased like
    something a person would actually write. The original version prepended
    "Targeting {title} at {company}: direct match on {skills}." — reported
    live, twice, as reading like leaked internal reasoning, not resume prose
    nobody writes "direct match on X" about themselves. Also redundant: you
    ARE applying to this exact job, restating the title/company back at
    yourself in the summary adds nothing a recruiter doesn't already know
    from the application itself."""
    from .jd_match import fetch_jd, SKILLS
    import re as _re
    resume = load_cv_md()
    m = _re.search(r"## Professional Summary\s*\n(.+?)(\n## )", resume, _re.S)
    base = (m.group(1).strip() if m else "").split("\n")[0]
    jd = (fetch_jd(url) or title).lower()
    resume_l = resume.lower()
    # skills the JD wants AND the resume proves. SKILLS entries like "r " carry
    # a deliberate trailing space (word-boundary guard against matching "r"
    # inside "for"/"senior") -- stripped here so it doesn't leak into the
    # display text as "R , Fraud" (reported live).
    matched = [s.strip().upper() if s.strip() in ("sas", "sql", "aml", "kyc", "ccar",
                                                   "cecl", "etl", "r")
               else s.strip().title()
               for s in SKILLS
               if s.strip() and s.strip() in jd and s.strip() in resume_l][:8]
    tail = (f" Directly experienced in {', '.join(matched)}." if matched else "")
    return (base + tail).strip()
