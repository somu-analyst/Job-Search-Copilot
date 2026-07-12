"""Design system — the single source of truth for how the app LOOKS.

Kept apart from src/ (business logic) so the frontend stays swappable: nothing
here imports from src, and src never imports from ui.

Visual system — Glassdoor green shell, Swiggy orange Apply
----------------------------------------------------------
Brand      green   #0CAA41   (structure: nav, tabs, links, selected states)
Accent     orange  #FC8019   (RESERVED for Apply — one loud thing per screen)
Signal     amber   #F59E0B   (must-apply 🔥 chip only)
Neutrals   green-biased grey (not pure grey — biased toward the brand hue)
Radius     8 / 12 / 16px     Spacing: 4px base unit
Elevation  near-flat: hairline border + 1px shadow. Depth only on hover.

Three roles, three hues, no collisions:
  - Green is the native job-site hue (Glassdoor, Upwork) — reads "go / trusted".
  - Orange is its complement, so Apply separates hard from the shell. That was
    the original bug: the CTA was the same blue family as the nav and vanished
    into it.
  - Orange over yellow for the button specifically because orange carries WHITE
    text legibly (so it reads as a solid primary button) while yellow needs dark
    text and reads as a caution label — and yellow would collide with the amber
    🔥 must-apply chip.

The hero uses a DARK slate-green gradient rather than flat bright green: a large
field of saturated green next to orange drifts "eco/agri", so the pure green
stays an accent, never a wash.
"""
from __future__ import annotations
import streamlit as st

TOKENS = {
    "primary": "#0CAA41", "primary_dk": "#087F33", "primary_sf": "#EFFBF3",
    "accent": "#FC8019", "accent_dk": "#C2410C", "accent_sf": "#FFF4ED",
    "warn": "#F59E0B", "warn_sf": "#FFFBEB",
    "danger": "#E11D48", "danger_sf": "#FFF1F2",
    "ink": "#0E1A16", "body": "#33443C", "muted": "#63776D", "faint": "#94A79B",
    "line": "#E2E9E5", "canvas": "#F7FAF8", "surface": "#FFFFFF",
}

CSS = """
<style>
:root{
  /* brand: Glassdoor green — structure only */
  --p:#0CAA41; --p-dk:#087F33; --p-sf:#EFFBF3; --p-bd:#B7ECCB;
  /* accent: Swiggy orange — Apply button ONLY */
  --a:#FC8019; --a-dk:#C2410C; --a-sf:#FFF4ED; --a-bd:#FED7AA;
  /* signal: amber — 🔥 must-apply chip only */
  --w:#F59E0B; --w-dk:#B45309; --w-sf:#FFFBEB; --w-bd:#FDE68A;
  --d:#E11D48; --d-sf:#FFF1F2;
  /* neutrals biased green, so they read as chosen rather than default grey */
  --ink:#0E1A16; --body:#33443C; --muted:#63776D; --faint:#94A79B;
  --line:#E2E9E5; --canvas:#F7FAF8; --sf:#FFFFFF;
  --r:12px; --r-lg:16px; --r-sm:8px;
  --sh:0 1px 2px rgba(14,26,22,.05);
  --sh-md:0 6px 24px -8px rgba(14,26,22,.16);
}
.stApp{background:var(--canvas);}
.block-container{padding-top:1.2rem;padding-bottom:4rem;max-width:1400px;}
html,body,[class*="css"]{font-family:'Inter',-apple-system,'Segoe UI',Roboto,sans-serif;
  color:var(--body);-webkit-font-smoothing:antialiased;}

/* ── Type scale ─────────────────────────────────────────────── */
h1{font-size:27px;font-weight:800;color:var(--ink);letter-spacing:-.025em;}
h2{font-size:20px;font-weight:700;color:var(--ink);letter-spacing:-.015em;}
h3{font-size:17px;font-weight:700;color:var(--ink);letter-spacing:-.01em;}
h4{font-size:14.5px;font-weight:700;color:var(--ink);margin:4px 0 2px;}
h5{font-size:12px;font-weight:700;color:var(--faint);
   text-transform:uppercase;letter-spacing:.07em;}
p,li,span,label{font-size:14px;}

/* ── Hero: gradient, restrained, states what the app does ───── */
/* Glassdoor's dark slate-green: the pure green arrives late, as an accent —
   a flat field of bright green next to the orange CTA drifts "eco/agri". */
.hero{background:linear-gradient(115deg,#0E1A1F 0%,#124734 55%,#0CAA41 130%);
  border-radius:var(--r-lg);padding:26px 30px;margin-bottom:14px;color:#fff;
  box-shadow:var(--sh-md);position:relative;overflow:hidden;}
.hero:after{content:"";position:absolute;right:-70px;top:-70px;width:250px;height:250px;
  background:radial-gradient(circle,rgba(255,255,255,.13),transparent 68%);}
/* Identity left, system-flow right — the right side used to be dead space. */
.hero-grid{display:flex;align-items:center;justify-content:space-between;
  gap:28px;flex-wrap:wrap;position:relative;z-index:1;}
.hero-id{display:flex;align-items:center;gap:17px;}
.hero-logo{width:70px;height:70px;border-radius:17px;flex:none;
  box-shadow:0 5px 16px -3px rgba(0,0,0,.38);}
.hero h1{color:#fff;margin:0;font-size:42px;font-weight:800;letter-spacing:-.035em;
  line-height:1.02;white-space:nowrap;}
@media (max-width:820px){ .hero h1{font-size:31px;white-space:normal;} }
.hero p{margin:12px 0 0;opacity:.88;font-size:14px;max-width:680px;
  position:relative;z-index:1;}
.hero .kicker{font-size:10.5px;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;opacity:.72;margin-bottom:3px;}

/* The five-stage flow: the whole system at a glance, so a new user gets it
   before scrolling. Hidden on narrow screens rather than wrapping into mush. */
.hero-flow{display:flex;align-items:flex-start;gap:2px;}
.fl-step{text-align:center;min-width:64px;}
.fl-dot{width:24px;height:24px;border-radius:50%;margin:0 auto 5px;
  background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.32);
  color:#fff;font-size:11px;font-weight:800;line-height:23px;}
.fl-lab{font-size:12.5px;font-weight:700;color:#fff;letter-spacing:-.01em;}
.fl-sub{font-size:9.5px;color:rgba(255,255,255,.6);margin-top:1px;line-height:1.25;}
.fl-arw{color:rgba(255,255,255,.38);font-size:13px;padding-top:2px;}
@media (max-width:1150px){ .hero-flow{display:none;} }

/* ── KPI strip ──────────────────────────────────────────────── */
[data-testid="stMetric"]{background:var(--sf);border:1px solid var(--line);
  border-radius:var(--r);padding:14px 16px;box-shadow:var(--sh);transition:.16s;}
[data-testid="stMetric"]:hover{border-color:var(--p-bd);transform:translateY(-1px);
  box-shadow:var(--sh-md);}
[data-testid="stMetricLabel"] p{font-size:11px;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;}
[data-testid="stMetricValue"]{color:var(--ink);font-weight:800;font-size:26px;
  letter-spacing:-.03em;}

/* ── Job card: the core product object ──────────────────────── */
.jcard{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);
  padding:15px 17px;margin-bottom:9px;box-shadow:var(--sh);transition:.16s;}
.jcard:hover{border-color:var(--p-bd);box-shadow:var(--sh-md);transform:translateY(-1px);}
.jcard.hot{border-left:3px solid var(--w);}
.jcard .t{font-size:15.5px;font-weight:700;color:var(--ink);letter-spacing:-.01em;
  line-height:1.32;}
.jcard .m{color:var(--muted);font-size:12.5px;margin-top:3px;}

/* ── Chips / badges ─────────────────────────────────────────── */
.chip{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;
  font-weight:700;margin:5px 5px 0 0;border:1px solid transparent;line-height:1.7;}
.chip-p{background:var(--p-sf);color:var(--p-dk);border-color:var(--p-bd);}
.chip-a{background:var(--a-sf);color:var(--a-dk);border-color:var(--a-bd);}
.chip-w{background:var(--w-sf);color:var(--w-dk);border-color:var(--w-bd);}
.chip-d{background:var(--d-sf);color:#BE123C;border-color:#FECDD3;}
.chip-n{background:#F1F5F3;color:var(--muted);border-color:var(--line);}

/* ── Tabs: segmented control ────────────────────────────────── */
.stTabs [data-baseweb="tab-list"]{gap:2px;background:var(--sf);padding:5px;
  border-radius:var(--r);border:1px solid var(--line);box-shadow:var(--sh);}
.stTabs [data-baseweb="tab"]{border-radius:var(--r-sm);padding:8px 15px;
  font-weight:600;font-size:13.5px;color:var(--muted);transition:.15s;}
.stTabs [data-baseweb="tab"]:hover{background:#F1F5F3;color:var(--ink);}
.stTabs [aria-selected="true"]{background:var(--p)!important;color:#fff!important;}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}

/* ── Buttons: quiet default, ONE orange CTA per view ────────── */
.stButton>button,.stLinkButton>a,.stDownloadButton>button{
  border-radius:var(--r-sm);font-weight:600;font-size:13.5px;border:1px solid var(--line);
  background:var(--sf);color:var(--body);box-shadow:var(--sh);transition:.15s;}
.stButton>button:hover,.stLinkButton>a:hover,.stDownloadButton>button:hover{
  border-color:var(--p);color:var(--p);background:var(--p-sf);transform:translateY(-1px);}
.stButton>button[kind="primary"],.stLinkButton>a[kind="primary"],
.stDownloadButton>button[kind="primary"]{
  background:var(--a);border-color:var(--a);color:#fff!important;
  box-shadow:0 2px 10px -2px rgba(252,128,25,.45);}
.stButton>button[kind="primary"]:hover,.stLinkButton>a[kind="primary"]:hover,
.stDownloadButton>button[kind="primary"]:hover{
  background:var(--a-dk);border-color:var(--a-dk);color:#fff!important;}

/* ── Surfaces ───────────────────────────────────────────────── */
[data-testid="stDataFrame"],[data-testid="stExpander"],
div[data-testid="stVerticalBlockBorderWrapper"],[data-testid="stPopoverBody"]{
  border:1px solid var(--line);border-radius:var(--r);background:var(--sf);
  box-shadow:var(--sh);}
[data-testid="stDataFrame"]{overflow:hidden;}
[data-testid="stDialog"] div[role="dialog"]{border-radius:var(--r-lg);
  box-shadow:0 24px 60px -12px rgba(15,23,42,.3);border:1px solid var(--line);}

/* ── Inputs: hairline, ring only on focus ───────────────────── */
.stTextInput input,.stNumberInput input,.stTextArea textarea{
  border-radius:var(--r-sm);border:1px solid var(--line);font-size:13.5px;}
.stTextInput input:focus,.stTextArea textarea:focus{
  border-color:var(--p);box-shadow:0 0 0 3px rgba(12,170,65,.14);}
.stSelectbox div[data-baseweb="select"]>div,
.stMultiSelect div[data-baseweb="select"]>div{
  border-radius:var(--r-sm);border:1px solid var(--line)!important;
  background:var(--sf)!important;min-height:40px;cursor:pointer;font-size:13.5px;
  transition:.15s;}
.stSelectbox div[data-baseweb="select"]>div:hover,
.stMultiSelect div[data-baseweb="select"]>div:hover{
  border-color:var(--p)!important;background:var(--p-sf)!important;}
.stSelectbox label,.stTextInput label,.stMultiSelect label,.stSlider label,
.stCheckbox label,.stRadio label{font-weight:600;color:var(--body);font-size:13px;}

/* ── Sidebar: secondary controls only ───────────────────────── */
[data-testid="stSidebar"]{background:var(--sf);border-right:1px solid var(--line);}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{font-size:15px;color:var(--ink);}

/* ── Feedback ───────────────────────────────────────────────── */
[data-testid="stAlert"]{border-radius:var(--r);border:1px solid var(--line);
  box-shadow:none;font-size:13.5px;}
[data-testid="stCaptionContainer"]{color:var(--muted);font-size:12.5px;}
hr{margin:14px 0;border-color:var(--line);}
#MainMenu,footer,[data-testid="stDecoration"]{visibility:hidden;}

/* ── Empty state ────────────────────────────────────────────── */
.empty{text-align:center;padding:46px 20px;background:var(--sf);
  border:1px dashed #CBD5E1;border-radius:var(--r-lg);}
.empty .i{font-size:36px;}
.empty .h{font-size:16px;font-weight:700;color:var(--ink);margin-top:8px;}
.empty .s{font-size:13.5px;color:var(--muted);margin-top:4px;}

/* ── Step rail ──────────────────────────────────────────────── */
.rail{display:flex;align-items:stretch;gap:2px;margin:2px 0 12px;}
.rail .s{flex:1;text-align:center;border-radius:var(--r-sm);padding:8px 6px;
  font-size:12.5px;font-weight:600;white-space:nowrap;border:1px solid var(--line);
  background:var(--sf);color:var(--faint);}
.rail .s.on{background:var(--p);border-color:var(--p);color:#fff;}
.rail .s.done{background:var(--p-sf);border-color:var(--p-bd);color:var(--p-dk);}
.rail .arw{color:#CBD5E1;align-self:center;padding:0 6px;font-size:13px;}
</style>
"""


def inject() -> None:
    """Apply the design system. Call once, right after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)
