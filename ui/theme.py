"""Design system — the single source of truth for how the app LOOKS.

Kept apart from src/ (business logic) so the frontend stays swappable: nothing
here imports from src, and src never imports from ui.

Visual system
-------------
Brand      indigo  #4F46E5   (primary — nav, links, focus, selected states)
Accent     emerald #10B981   (RESERVED for apply/success — one per screen)
Signal     amber   #F59E0B   (must-apply 🔥 only)
Neutrals   slate ramp        (ink → body → muted → faint → line → canvas)
Radius     8 / 12 / 16px     Spacing: 4px base unit
Elevation  near-flat: hairline border + 1px shadow. Depth only on hover.
"""
from __future__ import annotations
import streamlit as st

TOKENS = {
    "primary": "#4F46E5", "primary_dk": "#4338CA", "primary_sf": "#EEF2FF",
    "accent": "#10B981", "accent_dk": "#059669", "accent_sf": "#ECFDF5",
    "warn": "#F59E0B", "warn_sf": "#FFFBEB",
    "danger": "#E11D48", "danger_sf": "#FFF1F2",
    "ink": "#0F172A", "body": "#334155", "muted": "#64748B", "faint": "#94A3B8",
    "line": "#E2E8F0", "canvas": "#F8FAFC", "surface": "#FFFFFF",
}

CSS = """
<style>
:root{
  --p:#4F46E5; --p-dk:#4338CA; --p-sf:#EEF2FF;
  --a:#10B981; --a-dk:#059669; --a-sf:#ECFDF5;
  --w:#F59E0B; --w-sf:#FFFBEB;
  --d:#E11D48; --d-sf:#FFF1F2;
  --ink:#0F172A; --body:#334155; --muted:#64748B; --faint:#94A3B8;
  --line:#E2E8F0; --canvas:#F8FAFC; --sf:#FFFFFF;
  --r:12px; --r-lg:16px; --r-sm:8px;
  --sh:0 1px 2px rgba(15,23,42,.05);
  --sh-md:0 6px 24px -8px rgba(15,23,42,.14);
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
.hero{background:linear-gradient(115deg,#312E81 0%,#4F46E5 55%,#6366F1 100%);
  border-radius:var(--r-lg);padding:26px 30px;margin-bottom:14px;color:#fff;
  box-shadow:var(--sh-md);position:relative;overflow:hidden;}
.hero:after{content:"";position:absolute;right:-70px;top:-70px;width:250px;height:250px;
  background:radial-gradient(circle,rgba(255,255,255,.13),transparent 68%);}
.hero h1{color:#fff;margin:0;font-size:26px;}
.hero p{margin:6px 0 0;opacity:.9;font-size:14px;max-width:640px;}
.hero .kicker{font-size:11px;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;opacity:.75;margin-bottom:5px;}

/* ── KPI strip ──────────────────────────────────────────────── */
[data-testid="stMetric"]{background:var(--sf);border:1px solid var(--line);
  border-radius:var(--r);padding:14px 16px;box-shadow:var(--sh);transition:.16s;}
[data-testid="stMetric"]:hover{border-color:#C7D2FE;transform:translateY(-1px);
  box-shadow:var(--sh-md);}
[data-testid="stMetricLabel"] p{font-size:11px;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;}
[data-testid="stMetricValue"]{color:var(--ink);font-weight:800;font-size:26px;
  letter-spacing:-.03em;}

/* ── Job card: the core product object ──────────────────────── */
.jcard{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);
  padding:15px 17px;margin-bottom:9px;box-shadow:var(--sh);transition:.16s;}
.jcard:hover{border-color:#C7D2FE;box-shadow:var(--sh-md);transform:translateY(-1px);}
.jcard.hot{border-left:3px solid var(--w);}
.jcard .t{font-size:15.5px;font-weight:700;color:var(--ink);letter-spacing:-.01em;
  line-height:1.32;}
.jcard .m{color:var(--muted);font-size:12.5px;margin-top:3px;}

/* ── Chips / badges ─────────────────────────────────────────── */
.chip{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;
  font-weight:700;margin:5px 5px 0 0;border:1px solid transparent;line-height:1.7;}
.chip-p{background:var(--p-sf);color:var(--p-dk);border-color:#C7D2FE;}
.chip-a{background:var(--a-sf);color:var(--a-dk);border-color:#A7F3D0;}
.chip-w{background:var(--w-sf);color:#B45309;border-color:#FDE68A;}
.chip-d{background:var(--d-sf);color:#BE123C;border-color:#FECDD3;}
.chip-n{background:#F1F5F9;color:var(--muted);border-color:var(--line);}

/* ── Tabs: segmented control ────────────────────────────────── */
.stTabs [data-baseweb="tab-list"]{gap:2px;background:var(--sf);padding:5px;
  border-radius:var(--r);border:1px solid var(--line);box-shadow:var(--sh);}
.stTabs [data-baseweb="tab"]{border-radius:var(--r-sm);padding:8px 15px;
  font-weight:600;font-size:13.5px;color:var(--muted);transition:.15s;}
.stTabs [data-baseweb="tab"]:hover{background:#F1F5F9;color:var(--ink);}
.stTabs [aria-selected="true"]{background:var(--p)!important;color:#fff!important;}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}

/* ── Buttons: quiet default, ONE emerald CTA per view ───────── */
.stButton>button,.stLinkButton>a,.stDownloadButton>button{
  border-radius:var(--r-sm);font-weight:600;font-size:13.5px;border:1px solid var(--line);
  background:var(--sf);color:var(--body);box-shadow:var(--sh);transition:.15s;}
.stButton>button:hover,.stLinkButton>a:hover,.stDownloadButton>button:hover{
  border-color:var(--p);color:var(--p);background:var(--p-sf);transform:translateY(-1px);}
.stButton>button[kind="primary"],.stLinkButton>a[kind="primary"],
.stDownloadButton>button[kind="primary"]{
  background:var(--a);border-color:var(--a);color:#fff!important;
  box-shadow:0 2px 10px -2px rgba(16,185,129,.45);}
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
  border-color:var(--p);box-shadow:0 0 0 3px rgba(79,70,229,.12);}
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
.rail .s.done{background:var(--p-sf);border-color:#C7D2FE;color:var(--p-dk);}
.rail .arw{color:#CBD5E1;align-self:center;padding:0 6px;font-size:13px;}
</style>
"""


def inject() -> None:
    """Apply the design system. Call once, right after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)
