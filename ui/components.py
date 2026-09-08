"""Reusable UI primitives — cards, chips, hero, empty/loading states, step rail.

Pure presentation. Takes plain values, returns/renders markup. No DB, no src
imports — so the whole ui/ package can be thrown away and replaced (React,
Next.js, whatever) without touching business logic.
"""
from __future__ import annotations
import html

import streamlit as st


def _esc(s) -> str:
    return html.escape(str(s or ""))


# ── Hero ────────────────────────────────────────────────────────────────────
# The five stages of the product, shown as a flow on the right of the hero.
# This is the whole system in one glance — a new user should understand what the
# app does before scrolling. (label, one-word what-it-does)
FLOW = [
    ("Find", "every source"),
    ("Score", "vs your resume"),
    ("Tailor", "per job"),
    ("Apply", "direct link"),
    ("Track", "dates & follow-ups"),
]


def hero(title: str, subtitle: str, kicker: str = "", logo_b64: str = "") -> None:
    """Top-of-page banner: identity on the left, the system's flow on the right."""
    k = f"<div class='kicker'>{_esc(kicker)}</div>" if kicker else ""
    mark = (f"<img class='hero-logo' src='data:image/png;base64,{logo_b64}' "
            f"alt='' />") if logo_b64 else ""

    steps = []
    for i, (label, sub) in enumerate(FLOW):
        steps.append(
            f"<div class='fl-step'><div class='fl-dot'>{i+1}</div>"
            f"<div class='fl-lab'>{_esc(label)}</div>"
            f"<div class='fl-sub'>{_esc(sub)}</div></div>")
        if i < len(FLOW) - 1:
            steps.append("<div class='fl-arw'>&rarr;</div>")

    # Two-tone wordmark: the last word takes a warm gold that sings against the
    # green shell. Deliberately NOT the orange accent — orange means Apply, and
    # spending it on decoration would blunt the one button that matters.
    words = _esc(title).split()
    head = " ".join(words[:-1])
    tail = words[-1] if words else ""
    mark_html = (f"<h1><span class='w1'>{head}</span> "
                 f"<span class='w2'>{tail}</span></h1>")

    # Subtitle lives INSIDE the left column now. Previously it sat below the grid,
    # which forced the flow to hug the top and left dead space beneath it.
    st.markdown(
        f"""<div class='hero'>
  <div class='hero-grid'>
    <div class='hero-left'>
      <div class='hero-id'>{mark}<div>{k}{mark_html}</div></div>
      <p>{_esc(subtitle)}</p>
    </div>
    <div class='hero-flow'>{''.join(steps)}</div>
  </div>
</div>""", unsafe_allow_html=True)


# ── Chips ───────────────────────────────────────────────────────────────────
def chip(text: str, kind: str = "n") -> str:
    """Inline tag. kind: p=brand green, w=amber signal, d=risk, n=neutral.

    NOTE the deliberate omission: chips never use the orange accent ('a').
    Orange means Apply, and only Apply — the moment a salary chip is also orange,
    the button stops being the one loud thing on the screen."""
    return f"<span class='chip chip-{kind}'>{_esc(text)}</span>"


def chips(items: list[tuple[str, str]]) -> str:
    return "".join(chip(t, k) for t, k in items if t)


def score_kind(score: float) -> str:
    """Colour a fit score by band, consistently everywhere."""
    if score >= 8:
        return "w"      # amber = must-apply signal
    if score >= 6:
        return "p"      # green = strong fit
    return "n"


# ── Job card ────────────────────────────────────────────────────────────────
def job_card(title: str, company: str, location: str, score: float,
             industry: str = "", salary: str = "", sponsor: str = "",
             source: str = "", posted: str = "") -> None:
    """The product's core object. Chips carry the signal; text stays quiet."""
    hot = score >= 8
    tags = [(f"{score:.1f}/10 fit", score_kind(score))]
    if hot:
        tags.append(("MUST APPLY", "w"))
    if salary:
        tags.append((salary, "p"))
    if industry:
        tags.append((industry, "n"))
    if sponsor and sponsor.lower().startswith("strong"):
        tags.append(("H-1B sponsor", "p"))
    if source:
        tags.append((source, "n"))
    meta = " · ".join(x for x in [company, location or "—", posted] if x)
    st.markdown(
        f"<div class='jcard {'hot' if hot else ''}'>"
        f"<div class='t'>{_esc(title)}</div>"
        f"<div class='m'>{_esc(meta)}</div>"
        f"<div>{chips(tags)}</div></div>",
        unsafe_allow_html=True)


# ── States ──────────────────────────────────────────────────────────────────
def empty(icon: str, headline: str, sub: str = "") -> None:
    """Polished empty state — never a bare 'no data'."""
    st.markdown(
        f"<div class='empty'><div class='i'>{icon}</div>"
        f"<div class='h'>{_esc(headline)}</div>"
        f"<div class='s'>{_esc(sub)}</div></div>",
        unsafe_allow_html=True)


def section(title: str, sub: str = "") -> None:
    """Consistent section header with optional one-line explainer."""
    st.markdown(f"##### {title}")
    if sub:
        st.caption(sub)


# ── Grounding (resume authenticity) ─────────────────────────────────────────
def grounding_badge(rate: float, cited: bool = False, checked: int = 0) -> None:
    """One line on a resume version: how much of it traces back to your resume.

    Shown as GROUNDED, not as a fabrication rate — the number people act on is
    'how much of this can I defend', and a 0%-is-good metric reads backwards at
    a glance. `cited` marks the stronger check: the model named its sources, so
    the claim was verified against the fact it meant, not the closest match."""
    pct = max(0.0, min(1.0, 1.0 - float(rate or 0.0)))
    tone = "ok" if pct >= 0.999 else ("warn" if pct >= 0.75 else "bad")
    mark = {"ok": "🔗", "warn": "⚠️", "bad": "⛔"}[tone]
    detail = f" of {checked} claim{'s' if checked != 1 else ''}" if checked else ""
    st.markdown(
        f"<div class='ground {tone}'>{mark} Grounded {pct:.0%}{_esc(detail)}"
        + ("<span class='cite'>cited</span>" if cited else "")
        + "</div>", unsafe_allow_html=True)


def citation_list(rows: list[tuple[str, list[tuple[str, str]]]]) -> None:
    """Sentence-by-sentence provenance: each claim above the resume facts it
    was built from. This is what makes the check reviewable instead of
    something you either trust or ignore — you can see the actual line."""
    if not rows:
        st.caption("This version has no citations — it was written without the "
                   "cited path, so claims were matched by similarity instead.")
        return
    for sentence, facts in rows:
        st.markdown(f"<div class='claim'>{_esc(sentence)}</div>",
                    unsafe_allow_html=True)
        if not facts:
            st.markdown("<div class='src none'>no source cited</div>",
                        unsafe_allow_html=True)
            continue
        for fid, text in facts:
            st.markdown(
                f"<div class='src'><span class='fid'>{_esc(fid)}</span>"
                f"{_esc(text)}</div>", unsafe_allow_html=True)


# ── Step rail ───────────────────────────────────────────────────────────────
def step_rail(steps: list[str], active: int) -> None:
    """1 → 2 → 3 → 4 progress rail. `active` is 1-indexed; earlier steps read
    as completed so the user always knows where they are."""
    cells = []
    for i, label in enumerate(steps, 1):
        cls = "on" if i == active else ("done" if i < active else "")
        cells.append(f"<div class='s {cls}'>{i} &nbsp;{_esc(label)}</div>")
        if i < len(steps):
            cells.append("<div class='arw'>&rarr;</div>")
    st.markdown(f"<div class='rail'>{''.join(cells)}</div>", unsafe_allow_html=True)
