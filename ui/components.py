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
def hero(title: str, subtitle: str, kicker: str = "") -> None:
    """Top-of-page banner. Says what the app does, in one breath."""
    k = f"<div class='kicker'>{_esc(kicker)}</div>" if kicker else ""
    st.markdown(
        f"<div class='hero'>{k}<h1>{_esc(title)}</h1><p>{_esc(subtitle)}</p></div>",
        unsafe_allow_html=True)


# ── Chips ───────────────────────────────────────────────────────────────────
def chip(text: str, kind: str = "n") -> str:
    """Inline tag. kind: p=brand, a=good, w=warn, d=risk, n=neutral."""
    return f"<span class='chip chip-{kind}'>{_esc(text)}</span>"


def chips(items: list[tuple[str, str]]) -> str:
    return "".join(chip(t, k) for t, k in items if t)


def score_kind(score: float) -> str:
    """Colour a fit score by band, consistently everywhere."""
    if score >= 8:
        return "w"      # amber = must-apply
    if score >= 6:
        return "a"      # emerald = strong
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
        tags.append((salary, "a"))
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
