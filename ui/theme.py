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

/* ── Type scale ─────────────────────────────────────────────────
   Lifted a full step across the board: the app was set at 13–14px, which is
   fine for a dense internal tool and too small for something you look at all
   day. Body sits at 15.5px, headings scale from it. */
h1{font-size:31px;font-weight:800;color:var(--ink);letter-spacing:-.025em;}
h2{font-size:23px;font-weight:700;color:var(--ink);letter-spacing:-.015em;}
h3{font-size:19.5px;font-weight:700;color:var(--ink);letter-spacing:-.012em;}
h4{font-size:16.5px;font-weight:700;color:var(--ink);margin:6px 0 3px;}
h5{font-size:13px;font-weight:700;color:var(--faint);
   text-transform:uppercase;letter-spacing:.07em;}
p,li,span,label,div[data-testid="stMarkdownContainer"] p{font-size:15.5px;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{
  font-size:13.5px!important;}

/* ── Hero: gradient, restrained, states what the app does ───── */
/* Glassdoor's dark slate-green: the pure green arrives late, as an accent —
   a flat field of bright green next to the orange CTA drifts "eco/agri". */
.hero{background:linear-gradient(115deg,#0E1A1F 0%,#124734 55%,#0CAA41 130%);
  border-radius:var(--r-lg);padding:26px 30px;margin-bottom:14px;color:#fff;
  box-shadow:var(--sh-md);position:relative;overflow:hidden;}
.hero:after{content:"";position:absolute;right:-70px;top:-70px;width:250px;height:250px;
  background:radial-gradient(circle,rgba(255,255,255,.13),transparent 68%);}
/* Identity left, system-flow right. The flow is CENTRED against the full hero
   height — it used to hug the top and leave a dead band underneath. */
.hero-grid{display:flex;align-items:center;justify-content:space-between;
  gap:34px;flex-wrap:wrap;position:relative;z-index:1;}
.hero-left{flex:1 1 420px;min-width:330px;}
.hero-id{display:flex;align-items:center;gap:19px;}
.hero-logo{width:84px;height:84px;border-radius:20px;flex:none;
  box-shadow:0 6px 18px -3px rgba(0,0,0,.40);}
/* !important on purpose: Streamlit ships its own h1 rule at the SAME specificity
   as `.hero h1`, so which wins comes down to stylesheet load order — and ours
   silently lost. This is the one place in the sheet where we force it. */
/* clamp() rather than fixed px + media queries: it scales with the viewport and
   can't be caught out by a breakpoint that happens to sit near the user's window
   width — which is how this kept landing "small" for him at ~1100px. */
.hero h1{margin:0!important;font-size:clamp(40px,5.4vw,82px)!important;
  font-weight:800!important;letter-spacing:-.042em!important;
  line-height:1.02!important;padding:0!important;}
.hero h1 .w1{color:#F2FBF5!important;}             /* cool white, reads on green */
.hero h1 .w2{color:#FFD166!important;              /* warm gold — sings on green */
  text-shadow:0 3px 20px rgba(255,209,102,.32);}
.hero p{margin:16px 0 0!important;opacity:.9;font-size:17px!important;
  max-width:660px;position:relative;z-index:1;line-height:1.55;}
.hero .kicker{font-size:12px;font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;opacity:.78;margin-bottom:6px;}

/* The five-stage flow: the whole system at a glance, so a new user gets it
   before scrolling. Boxed steps, centred against the hero's full height. */
.hero-flow{display:flex;align-items:stretch;gap:5px;flex:none;}
.fl-step{text-align:center;min-width:92px;padding:13px 9px 12px;
  background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.20);
  border-radius:12px;display:flex;flex-direction:column;justify-content:center;}
.fl-dot{width:30px;height:30px;border-radius:50%;margin:0 auto 8px;
  background:rgba(255,255,255,.20);border:1px solid rgba(255,255,255,.38);
  color:#fff;font-size:14px;font-weight:800;line-height:29px;}
.fl-lab{font-size:15px;font-weight:700;color:#fff;letter-spacing:-.01em;}
.fl-sub{font-size:11.5px;color:rgba(255,255,255,.72);margin-top:3px;
  line-height:1.3;}
.fl-arw{color:rgba(255,255,255,.45);font-size:17px;align-self:center;padding:0 2px;}
@media (max-width:1250px){ .hero-flow{display:none;} }

/* ── KPI strip ──────────────────────────────────────────────── */
[data-testid="stMetric"]{background:var(--sf);border:1px solid var(--line);
  border-radius:var(--r);padding:14px 16px;box-shadow:var(--sh);transition:.16s;}
[data-testid="stMetric"]:hover{border-color:var(--p-bd);transform:translateY(-1px);
  box-shadow:var(--sh-md);}
[data-testid="stMetricLabel"] p{font-size:12.5px;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;}
[data-testid="stMetricValue"]{color:var(--ink);font-weight:800;font-size:31px;
  letter-spacing:-.03em;}

/* ── Job card: the core product object ──────────────────────── */
.jcard{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);
  padding:15px 17px;margin-bottom:9px;box-shadow:var(--sh);transition:.16s;}
.jcard:hover{border-color:var(--p-bd);box-shadow:var(--sh-md);transform:translateY(-1px);}
.jcard.hot{border-left:3px solid var(--w);}
.jcard .t{font-size:17px;font-weight:700;color:var(--ink);letter-spacing:-.01em;
  line-height:1.32;}
.jcard .m{color:var(--muted);font-size:13.5px;margin-top:3px;}

/* ── Chips / badges ─────────────────────────────────────────── */
.chip{display:inline-block;padding:3px 11px;border-radius:999px;font-size:12.5px;
  font-weight:700;margin:5px 5px 0 0;border:1px solid transparent;line-height:1.7;}
.chip-p{background:var(--p-sf);color:var(--p-dk);border-color:var(--p-bd);}
.chip-a{background:var(--a-sf);color:var(--a-dk);border-color:var(--a-bd);}
.chip-w{background:var(--w-sf);color:var(--w-dk);border-color:var(--w-bd);}
.chip-d{background:var(--d-sf);color:#BE123C;border-color:#FECDD3;}
.chip-n{background:#F1F5F3;color:var(--muted);border-color:var(--line);}

/* ── Tabs: segmented control ────────────────────────────────── */
.stTabs [data-baseweb="tab-list"]{gap:2px;background:var(--sf);padding:5px;
  border-radius:var(--r);border:1px solid var(--line);box-shadow:var(--sh);}
.stTabs [data-baseweb="tab"]{border-radius:var(--r-sm);padding:10px 17px;
  font-weight:600;font-size:15px;color:var(--muted);transition:.15s;}
.stTabs [data-baseweb="tab"]:hover{background:#F1F5F3;color:var(--ink);}
.stTabs [aria-selected="true"]{background:var(--p)!important;color:#fff!important;}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}

/* ── Buttons: quiet default, ONE orange CTA per view ────────── */
.stButton>button,.stLinkButton>a,.stDownloadButton>button{
  border-radius:var(--r-sm);font-weight:700;font-size:15px;border:1px solid var(--line);
  background:var(--sf);color:var(--body);box-shadow:var(--sh);transition:.15s;
  padding:.5rem 1rem;}
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
[data-testid="stDataFrame"]{overflow:hidden;font-size:14.5px;}
[data-testid="stDialog"] div[role="dialog"]{border-radius:var(--r-lg);
  box-shadow:0 24px 60px -12px rgba(15,23,42,.3);border:1px solid var(--line);}

/* ── Inputs: hairline, ring only on focus ───────────────────── */
.stTextInput input,.stNumberInput input,.stTextArea textarea{
  border-radius:var(--r-sm);border:1px solid var(--line);font-size:15px;}
.stTextInput input:focus,.stTextArea textarea:focus{
  border-color:var(--p);box-shadow:0 0 0 3px rgba(12,170,65,.14);}
.stSelectbox div[data-baseweb="select"]>div,
.stMultiSelect div[data-baseweb="select"]>div{
  border-radius:var(--r-sm);border:1px solid var(--line)!important;
  background:var(--sf)!important;min-height:44px;cursor:pointer;font-size:15px;
  transition:.15s;}
.stSelectbox div[data-baseweb="select"]>div:hover,
.stMultiSelect div[data-baseweb="select"]>div:hover{
  border-color:var(--p)!important;background:var(--p-sf)!important;}
.stSelectbox label,.stTextInput label,.stMultiSelect label,.stSlider label,
.stCheckbox label,.stRadio label{font-weight:600;color:var(--body);font-size:14.5px;}

/* ── Sidebar: secondary controls only ───────────────────────── */
[data-testid="stSidebar"]{background:var(--sf);border-right:1px solid var(--line);}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{font-size:15px;color:var(--ink);}

/* ── Feedback ───────────────────────────────────────────────── */
[data-testid="stAlert"]{border-radius:var(--r);border:1px solid var(--line);
  box-shadow:none;font-size:15px;}
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
.rail .s{flex:1;text-align:center;border-radius:var(--r-sm);padding:11px 8px;
  font-size:14.5px;font-weight:600;white-space:nowrap;border:1px solid var(--line);
  background:var(--sf);color:var(--faint);}
.rail .s.on{background:var(--p);border-color:var(--p);color:#fff;}
.rail .s.done{background:var(--p-sf);border-color:var(--p-bd);color:var(--p-dk);}
.rail .arw{color:#CBD5E1;align-self:center;padding:0 6px;font-size:13px;}
</style>
"""


def inject() -> None:
    """Apply the design system. Call once, right after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)
