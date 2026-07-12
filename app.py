"""bfsi-job-hunter — Streamlit frontend.

    streamlit run app.py

Three tabs:
  Jobs       — filterable table of every discovered posting; edit status inline
               (new / interested / applied / interview / offer / rejected / skip).
  Companies  — the auto-growing directory: who's hiring, careers pages, Workday.
  Summary    — pipeline funnel + counts.

Reads/writes data/jobs.db. No API key, fully local.
"""
import re
import sqlite3
from datetime import date
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def posted_days_ago(s) -> int | None:
    """Normalize messy date_posted ('Posted 3 Days Ago', '2026-07-10') to days."""
    s = str(s or "").strip().lower()
    if not s or s == "none" or s == "nan":
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return (date.today() - date(int(m[1]), int(m[2]), int(m[3]))).days
        except ValueError:
            return None
    if "today" in s or "just posted" in s:
        return 0
    if "yesterday" in s:
        return 1
    m = re.search(r"(\d+)\+?\s*day", s)
    if m:
        return int(m.group(1))
    return None

from src import db

st.set_page_config(page_title="BFSI Job Hunter", page_icon="💼", layout="wide",
                   initial_sidebar_state="expanded")

# ── Modern professional theme (classic banking blue) ────────────────────────
st.markdown("""
<style>
:root { --navy:#0f2a4a; --blue:#0f5ea8; --ink:#1a2733; --line:#e3e9f0; }
.stApp { background:#f4f7fb; }
.block-container { padding-top:1.6rem; max-width:1500px; }
/* Header band */
.app-header{background:linear-gradient(100deg,#0f2a4a 0%,#0f5ea8 100%);
  color:#fff;border-radius:14px;padding:20px 28px;margin-bottom:18px;
  box-shadow:0 6px 20px rgba(15,42,74,.18);}
.app-header h1{margin:0;font-size:26px;font-weight:700;letter-spacing:.3px;color:#fff;}
.app-header p{margin:4px 0 0;opacity:.85;font-size:14px;}
/* Metric cards */
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);
  border-radius:12px;padding:14px 18px;box-shadow:0 2px 6px rgba(16,40,70,.05);}
[data-testid="stMetricLabel"] p{font-size:13px;color:#5b6b7d;font-weight:600;}
[data-testid="stMetricValue"]{color:var(--navy);font-weight:700;}
/* Tabs */
.stTabs [data-baseweb="tab-list"]{gap:4px;background:#fff;padding:6px;
  border-radius:12px;border:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{border-radius:8px;padding:8px 16px;font-weight:600;
  color:#5b6b7d;}
.stTabs [aria-selected="true"]{background:var(--blue)!important;color:#fff!important;}
/* Buttons */
.stButton>button{border-radius:9px;font-weight:600;border:1px solid var(--line);
  transition:all .15s;}
.stButton>button:hover{border-color:var(--blue);color:var(--blue);}
.stButton>button[kind="primary"]{background:var(--blue);border-color:var(--blue);}
/* Dataframes */
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;
  overflow:hidden;box-shadow:0 2px 6px rgba(16,40,70,.04);}
/* Sidebar */
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line);}
[data-testid="stSidebar"] h2{color:var(--navy);font-size:18px;}
/* Expander (filter panel) */
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:12px;
  background:#fff;}
h2,h3{color:var(--navy);}
h4{color:var(--blue);font-weight:700;margin-top:8px;}
h5{color:var(--navy);font-weight:700;}
.stTextInput input{border-radius:8px;border:1.5px solid var(--line);}
/* Dropdowns — clearly bordered so they read as selectable */
.stSelectbox div[data-baseweb="select"]>div,
.stMultiSelect div[data-baseweb="select"]>div{
  border-radius:8px;border:2px solid #b9cbe0!important;background:#fff!important;
  min-height:42px;cursor:pointer;box-shadow:0 1px 3px rgba(16,40,70,.06);
  transition:border-color .15s,box-shadow .15s;}
.stSelectbox div[data-baseweb="select"]>div:hover,
.stMultiSelect div[data-baseweb="select"]>div:hover{
  border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(15,94,168,.12);}
/* Visible dropdown chevron */
.stSelectbox svg,.stMultiSelect svg{color:var(--blue);width:22px;height:22px;}
.stSelectbox label,.stTextInput label,.stMultiSelect label,
.stSlider label,.stCheckbox label{font-weight:600;color:#3d4d5e;}
[data-testid="stCode"]{border-radius:9px;border:1px solid var(--line);}
.stLinkButton>a{border-radius:9px;font-weight:600;}
hr{margin:10px 0;border-color:var(--line);}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def _conn():
    c = sqlite3.connect(db.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    db.init(c)
    return c


conn = _conn()


def load(sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


st.markdown(
    "<div class='app-header'><h1>BFSI Job Hunter</h1>"
    "<p>Fraud · Credit Risk · AML · Analytics — discovery, fit-scoring, "
    "AI-tailored resumes & application tracking, all local and token-free.</p></div>",
    unsafe_allow_html=True)
c = db.counts(conn)
n_applied = conn.execute(
    "SELECT COUNT(*) FROM jobs WHERE status IN ('applied','responded','interview','offer')"
).fetchone()[0]
n_fire = conn.execute(
    "SELECT COUNT(*) FROM jobs WHERE score>=8 AND status IN ('new','interested')").fetchone()[0]
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Jobs found", c["jobs"])
m2.metric("Unreviewed", c["new"])
m3.metric("🔥 Must-apply", n_fire)
m4.metric("Applied", n_applied)
m5.metric("Companies", c["companies"])


def _post_process():
    from src import score, sponsors
    score.score_all(conn, verbose=False)
    sponsors.enrich_seeds(conn)
    db.enrich_industries(conn)
    db.archive_stale(conn)


# ── Ad-hoc scan (sidebar) ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚡ Run a scan now")
    st.caption("Same pipeline as the scheduler — scrape → filter → dedupe "
               "→ score → sponsor-tag. Token-free.")
    if st.button("🏦 Quick scan — Workday banks (~1 min)", use_container_width=True):
        from src import scrape_workday
        with st.status("Scanning bank Workday APIs...", expanded=True) as s:
            n = scrape_workday.run(conn, verbose=False)
            st.write(f"Workday: **+{n}** new jobs")
            _post_process()
            s.update(label=f"Done — +{n} new jobs", state="complete")
        st.rerun()
    if st.button("🌐 Full scan — all sources (~5–10 min)", use_container_width=True):
        from src import scrape_boards, scrape_workday, scrape_apis
        with st.status("Full scan running — leave this tab open...", expanded=True) as s:
            st.write("1/3 Job boards (Indeed / LinkedIn / Google)...")
            nb = scrape_boards.run(conn, verbose=False)
            st.write(f"Boards: **+{nb}** new jobs")
            st.write("2/3 Workday bank APIs...")
            nw = scrape_workday.run(conn, verbose=False)
            st.write(f"Workday: **+{nw}** new jobs")
            st.write("3/3 Aggregator APIs (Adzuna / Jooble, if keys set)...")
            na = scrape_apis.run(conn, verbose=False)
            st.write(f"APIs: **+{na}** new jobs")
            _post_process()
            s.update(label=f"Done — +{nb + nw + na} new jobs", state="complete")
        st.rerun()
    st.divider()
    st.caption(f"DB: `{db.DB_PATH.name}` · statuses: {', '.join(db.STATUSES)}")

from src.score import MUST_APPLY_AT

APPLIED_STATES = ("applied", "responded", "interview", "offer")
AGE_OPTS = {"Any time": None, "Today": 0, "1 day": 1, "3 days": 3,
            "1 week": 7, "2 weeks": 14, "1 month": 30}


def _save_edits(df, edited, key_note="notes"):
    """Persist status/notes edits; stamp date_applied when a job turns applied."""
    n = 0
    for i, row in edited.iterrows():
        orig = df.iloc[i]
        status_changed = row["status"] != orig["status"]
        notes_changed = (row.get(key_note) or "") != (orig[key_note] or "")
        if status_changed or notes_changed:
            conn.execute("UPDATE jobs SET status=?, notes=? WHERE rowid=?",
                         (row["status"], row.get(key_note) or "", int(orig["rowid"])))
            if status_changed and row["status"] in APPLIED_STATES and not (orig["date_applied"] or ""):
                conn.execute("UPDATE jobs SET date_applied=? WHERE rowid=?",
                             (db.today(), int(orig["rowid"])))
            n += 1
    conn.commit()
    return n


def render_job_board(kp, default_status=None, default_freshness="Any time"):
    """Reusable filter panel + editable jobs table. `kp` = unique widget-key prefix."""
    default_status = default_status if default_status is not None else ["new", "interested"]
    with st.expander("🔍 Filters", expanded=True):
        f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1.2])
        with f1:
            status_f = st.multiselect("Status", db.STATUSES, default=default_status, key=f"{kp}_status")
            age_f = st.selectbox("Freshness (pulled)", list(AGE_OPTS),
                                 index=list(AGE_OPTS).index(default_freshness), key=f"{kp}_age")
            posted_f = st.selectbox("Posted age (from source)", list(AGE_OPTS), index=0,
                                    key=f"{kp}_posted",
                                    help="Job board's own posted date; jobs with no date always pass")
        with f2:
            min_score = st.slider("Min score (1–10)", 1.0, 10.0, 1.0, 0.5, key=f"{kp}_min")
            must_only = st.checkbox(f"🔥 Must-apply only (≥ {MUST_APPLY_AT:.0f})", key=f"{kp}_must")
        with f3:
            companies_all = [r[0] for r in conn.execute(
                "SELECT DISTINCT company FROM jobs ORDER BY company")]
            company_f = st.multiselect("Company", companies_all, key=f"{kp}_co")
            source_f = st.multiselect("Source", [r[0] for r in conn.execute(
                "SELECT DISTINCT source FROM jobs")], key=f"{kp}_src")
            industry_f = st.multiselect("Industry", [r[0] for r in conn.execute(
                "SELECT DISTINCT industry FROM companies WHERE industry != '' ORDER BY 1")],
                key=f"{kp}_ind")
        with f4:
            kw = st.text_input("Search title/company", key=f"{kp}_kw")
            core_only = st.checkbox("Core-fit ★ only", key=f"{kp}_core")

    q = """SELECT jobs.rowid AS rowid, jobs.url AS url, jobs.title AS title,
                  jobs.company AS company, COALESCE(companies.industry,'') AS industry,
                  jobs.location AS location, jobs.score AS score,
                  jobs.date_posted AS date_posted, jobs.date_found AS date_found,
                  jobs.source AS source, jobs.is_core AS is_core,
                  jobs.status AS status, jobs.notes AS notes, jobs.date_applied AS date_applied
           FROM jobs LEFT JOIN companies ON jobs.company = companies.name
           WHERE jobs.score >= ?"""
    p = [must_only and MUST_APPLY_AT or min_score]
    if industry_f:
        q += f" AND companies.industry IN ({','.join('?'*len(industry_f))})"; p += industry_f
    if status_f:
        q += f" AND status IN ({','.join('?'*len(status_f))})"; p += status_f
    if company_f:
        q += f" AND jobs.company IN ({','.join('?'*len(company_f))})"; p += company_f
    if source_f:
        q += f" AND source IN ({','.join('?'*len(source_f))})"; p += source_f
    if core_only:
        q += " AND is_core = 1"
    if kw:
        q += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"; p += [f"%{kw.lower()}%"]*2
    days = AGE_OPTS[age_f]
    if days is not None:
        q += " AND date_found >= date('now', ?)"; p.append(f"-{days} days")
    q += " ORDER BY score DESC, date_found DESC"
    df = load(q, p)
    pmax = AGE_OPTS[posted_f]
    if pmax is not None and not df.empty:
        pd_days = df["date_posted"].map(posted_days_ago)
        df = df[(pd_days.isna()) | (pd_days <= pmax)].reset_index(drop=True)

    st.caption(f"**{len(df)} jobs** — set **Status** to `applied` and it moves to the "
               f"✅ Applied tab with today's date. 🔥 = must apply (score ≥ {MUST_APPLY_AT:.0f}).")
    if df.empty:
        st.info("No jobs match. Loosen filters or run a scan from the sidebar.")
        return
    view = df.drop(columns=["rowid", "is_core", "date_applied"]).copy()
    view.insert(0, "score", view.pop("score"))
    view.insert(0, "🔥", (df["score"] >= MUST_APPLY_AT).map({True: "🔥", False: ""}))
    edited = st.data_editor(
        view, hide_index=True, use_container_width=True, height=520,
        column_config={
            "🔥": st.column_config.TextColumn("🔥", width="small"),
            "url": st.column_config.LinkColumn("Link", display_text="open ↗"),
            "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
            "score": st.column_config.NumberColumn("Resume fit", format="%.1f / 10",
                     help="1-10 match vs your target-role keywords, seniority, H-1B sponsor history"),
            "industry": st.column_config.TextColumn("Industry"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "date_posted": st.column_config.TextColumn("Posted"),
            "date_found": st.column_config.TextColumn("Pulled"),
        },
        disabled=["🔥", "title", "company", "industry", "location", "source", "url",
                  "score", "date_posted", "date_found"],
        key=f"{kp}_editor",
    )
    if st.button("💾 Save changes", type="primary", key=f"{kp}_save"):
        n = _save_edits(df, edited)
        st.success(f"Saved {n} change(s).")
        st.rerun()


tab_today, tab_jobs, tab_applied, tab_resume, tab_co, tab_h1b, tab_sum = st.tabs(
    ["🎯 Today", "📋 Jobs", "✅ Applied", "📄 Resume & Apply", "🏢 Companies",
     "🎫 H-1B Sponsors", "📊 Summary"])

# ── Today tab: fresh action queue (full board + follow-ups) ─────────────────
with tab_today:
    st.subheader("🔥 Apply next — fresh, high-fit, still open")
    st.caption("Same powerful filters as the Jobs tab, pre-focused on new & "
               "interested roles. Sort by score, filter by industry, mark applied inline.")
    render_job_board("today", default_status=["new", "interested"])

    st.divider()
    st.subheader("⏰ Follow-ups due (applied 7+ days ago, no response)")
    fu = load("""SELECT date_applied, title, company, url,
                        CAST(julianday('now') - julianday(date_applied) AS INT) AS days_ago
                 FROM jobs WHERE status='applied'
                   AND date_applied != '' AND date_applied <= date('now','-7 days')
                 ORDER BY date_applied""")
    if fu.empty:
        st.caption("None due — good.")
    else:
        st.dataframe(fu, hide_index=True, use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn("Link", display_text="open ↗"),
                                    "days_ago": st.column_config.NumberColumn("Days ago")})
        st.caption("Message the recruiter/hiring manager on LinkedIn, or re-check status.")

# ── Jobs tab ────────────────────────────────────────────────────────────────
with tab_jobs:
    render_job_board("jobs", default_status=["new", "interested"])

# ── Applied tab ─────────────────────────────────────────────────────────────
with tab_applied:
    st.caption("Everything you've applied to, with dates. Update status as "
               "companies respond (responded → interview → offer / rejected).")
    dfa = load(f"""SELECT rowid, url, title, company, location, score,
                          date_applied, date_posted, date_found, status, notes
                   FROM jobs WHERE status IN ('applied','responded','interview','offer','rejected')
                   ORDER BY date_applied DESC, score DESC""")
    if dfa.empty:
        st.info("Nothing applied yet — mark jobs as `applied` in the Jobs tab.")
    else:
        viewa = dfa.drop(columns=["rowid"]).copy()
        editeda = st.data_editor(
            viewa, hide_index=True, use_container_width=True, height=520,
            column_config={
                "url": st.column_config.LinkColumn("Link", display_text="open ↗"),
                "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
                "score": st.column_config.NumberColumn("Score", format="%.1f / 10"),
                "date_applied": st.column_config.TextColumn("Applied on"),
                "date_posted": st.column_config.TextColumn("Posted"),
                "date_found": st.column_config.TextColumn("Pulled"),
                "title": st.column_config.TextColumn("Title", width="large"),
            },
            disabled=["title", "company", "location", "url", "score",
                      "date_applied", "date_posted", "date_found"],
            key="applied_editor",
        )
        if st.button("💾 Save applied changes", type="primary"):
            n = _save_edits(dfa, editeda)
            st.success(f"Saved {n} change(s).")
            st.rerun()
        st.download_button("⬇ Export applied (CSV)", dfa.drop(columns=["rowid"]).to_csv(index=False),
                           "applied-jobs.csv", "text/csv")

# ── Resume & Apply tab ──────────────────────────────────────────────────────
with tab_resume:
    from src import resume as rz
    st.markdown("### 📄 Resume & Apply Center")
    st.caption("**Step 1 — find your job** (filter, then pick from the dropdown). "
               "Then get fit scores, a tailored ATS resume, cover letter, apply kit, "
               "and one-click assisted apply.")

    # ── Step 1: narrowing filters, then the picker ────────────────────────
    fc1, fc2, fc3 = st.columns([2, 1.3, 1])
    with fc1:
        pick_search = st.text_input("🔎 Filter jobs by title or company",
                                    placeholder="e.g. fraud, credit risk, Citi…",
                                    key="pick_search")
    with fc2:
        pick_ind = st.selectbox("Industry", ["All"] + [r[0] for r in conn.execute(
            "SELECT DISTINCT industry FROM companies WHERE industry != '' ORDER BY 1")],
            key="pick_ind")
    with fc3:
        pick_fire = st.checkbox("🔥 Must-apply only", key="pick_fire")

    pq = """SELECT jobs.url AS url, jobs.title AS title, jobs.company AS company,
                   jobs.score AS score, jobs.location AS location,
                   COALESCE(companies.industry,'') AS industry, jobs.status AS status
            FROM jobs LEFT JOIN companies ON jobs.company = companies.name
            WHERE jobs.status NOT IN ('skip','stale','rejected')"""
    pp = []
    if pick_search:
        pq += " AND (LOWER(jobs.title) LIKE ? OR LOWER(jobs.company) LIKE ?)"
        pp += [f"%{pick_search.lower()}%"] * 2
    if pick_ind != "All":
        pq += " AND companies.industry = ?"; pp.append(pick_ind)
    if pick_fire:
        pq += " AND jobs.score >= 8"
    pq += " ORDER BY jobs.score DESC, jobs.date_found DESC LIMIT 300"
    jobs_pick = load(pq, pp)

    if jobs_pick.empty:
        st.info("No jobs match those filters — loosen them or run a scan.")
    else:
        st.markdown(f"**{len(jobs_pick)} matching jobs** — choose one below ⬇️")
        labels = [f"{'🔥 ' if r.score >= 8 else ''}{r.score:.1f}/10  •  {r.title[:64]}  •  {r.company}"
                  for r in jobs_pick.itertuples()]
        idx = st.selectbox("🎯 Job to apply for  (click to open the list ▾)",
                           range(len(labels)),
                           format_func=lambda i: labels[i], key="pick_job")
        job = jobs_pick.iloc[idx]

        # ── Styled job header card ────────────────────────────────────────
        fire = "🔥 MUST APPLY" if job["score"] >= 8 else ""
        st.markdown(f"""
<div style="background:#fff;border:1px solid #e3e9f0;border-left:5px solid #0f5ea8;
     border-radius:12px;padding:16px 20px;margin:8px 0 14px;
     box-shadow:0 2px 8px rgba(16,40,70,.06)">
  <div style="font-size:18px;font-weight:700;color:#0f2a4a">{job['title']}</div>
  <div style="color:#5b6b7d;margin-top:3px">
     🏢 {job['company']} &nbsp;·&nbsp; 📍 {job['location'] or 'n/a'}
     &nbsp;·&nbsp; {job['industry'] or 'BFSI'} &nbsp;·&nbsp;
     <b style="color:#0f5ea8">{job['score']:.1f}/10 fit</b>
     &nbsp; <span style="color:#c0392b;font-weight:700">{fire}</span></div>
</div>""", unsafe_allow_html=True)
        st.link_button("↗ Open the job posting", job["url"], use_container_width=False)

        # ── JD fetch (once), sponsorship/location screen, optional viewer ──
        from src import jd_match as _jdm
        jd_text = _jdm.fetch_jd(job["url"])
        flags = _jdm.jd_flags(jd_text)
        if flags["block"]:
            st.error("🚫 **Likely deal-breaker for your H-1B status:** "
                     + " · ".join(flags["block"])
                     + "  — verify before spending an application.")
        for n in flags["note"]:
            st.warning("⚠️ " + n)

        jv1, jv2 = st.columns([1, 2])
        with jv1:
            show_jd = st.checkbox("📄 View full job description", value=False, key="show_jd")
        with jv2:
            jd_where = st.radio("Show it in", ["Inline (right here)", "Left sidebar"],
                                horizontal=True, key="jd_where",
                                label_visibility="collapsed") if show_jd else None
        if show_jd:
            if not jd_text.strip():
                st.info("Full JD isn't fetchable for this source (LinkedIn/Indeed block it). "
                        "Use the ↗ posting link. Workday jobs show the full JD here.")
            elif jd_where == "Left sidebar":
                with st.sidebar:
                    st.markdown(f"### 📄 JD — {job['title'][:40]}")
                    st.markdown(
                        f"<div style='max-height:75vh;overflow:auto;font-size:13px;"
                        f"line-height:1.5'>{jd_text}</div>", unsafe_allow_html=True)
            else:
                with st.expander("📄 Full job description", expanded=True):
                    st.markdown(
                        f"<div style='max-height:480px;overflow:auto;padding:6px 4px;"
                        f"font-size:14px;line-height:1.55'>{jd_text}</div>",
                        unsafe_allow_html=True)

        # ── Position-fit analysis (JD fetched from Workday API when possible) ──
        st.markdown("#### Step 2 — Fit scores")
        from src import jd_match
        with st.spinner("Analyzing position fit vs your resume..."):
            fit = jd_match.analyze(job["url"], job["title"])
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Recruiter score", f"{fit['recruiter']}/10",
                  help="Surface match a recruiter skims in 6 sec: does the TITLE and "
                       "headline keywords echo your resume? Low = different job title/domain, "
                       "even if you could do the work.")
        s2.metric("ATS/Workday score", f"{fit['ats']}/10",
                  help="Pure keyword coverage — % of the JD's skills present in your resume. "
                       "This is what the automated filter counts.")
        s3.metric("Hiring-mgr score", f"{fit['hiring_manager']}/10",
                  help="Domain depth + quantified achievements — what an expert reviewer values.")
        s4.metric("OVERALL", f"{fit['overall']}/10")
        st.caption("ℹ️ These are literal **keyword** proxies. Recruiter looks at title/"
                   "keyword echo (so a Fraud resume scores low on an 'Interest Rate Risk' "
                   "title even if transferable); hiring-manager rewards deep skills. The "
                   "**AI deep analysis** below reads *meaning* and usually scores transferable "
                   "fits higher — trust it over these when they disagree.")
        if not fit["jd_available"]:
            st.caption("⚠ Full JD not fetchable for this source (LinkedIn/Indeed "
                       "block it) — scores estimated from the title only. "
                       "Workday jobs get full-JD analysis.")
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**✅ Highlights — JD asks, you HAVE:**")
            st.write(", ".join(fit["highlights"]) or "—")
        with g2:
            st.markdown("**❌ Missing — JD asks, resume lacks:**")
            st.write(", ".join(fit["missing"]) or "Nothing — full coverage!")
        st.caption("Keyword-based estimate ($0).")

        add_kw = []
        if fit["missing"]:
            add_kw = st.multiselect(
                "➕ Add to your AI-tailored resume — pick ONLY skills you genuinely have:",
                fit["missing"], key="add_missing",
                help="These get woven into the tailored summary below. The authenticity "
                     "check still flags anything your base resume can't support, so only "
                     "tick skills you can defend in an interview.")

        # ── AI deep analysis + AI tailoring (free OpenRouter models) ──────
        st.markdown("#### Step 3 — AI deep-dive & tailoring")
        a1, a2 = st.columns(2)
        with a1:
            if st.button("🤖 AI deep analysis (free model, ~30s)", use_container_width=True):
                from src import ai
                with st.spinner("Free model reading the JD vs your resume..."):
                    verdict = ai.analyze_job(job["url"], job["title"], job["company"])
                if verdict:
                    st.session_state["ai_verdict"] = verdict
                    conn.execute("UPDATE jobs SET score=?, notes=? WHERE url=?",
                                 (float(verdict.get("score_10", job["score"])),
                                  "AI-scored", job["url"]))
                    conn.commit()
                else:
                    from src import ai as _ai
                    st.warning("Free AI models are at their daily cap right now — the "
                               "keyword scores and Highlights/Missing above still apply. "
                               f"({_ai.last_error() or 'all busy'}). Try again tomorrow.")
        with a2:
            level_n = st.slider(
                "Tailoring strength (1 = light touch · 10 = strong reframe)",
                min_value=1, max_value=10, value=5, key="tailor_level",
                help="1-3 = light reorder of existing wording · 4-7 = emphasize matching "
                     "experience · 8-10 = strong reframe toward the JD (still facts-only). "
                     "Higher lifts the ATS score but raises over-claim risk — the "
                     "authenticity check flags it.")
            level = ("Conservative" if level_n <= 3 else
                     "Balanced" if level_n <= 7 else "Aggressive")
            st.caption(f"Level {level_n}/10 — **{level}**")
            if st.button("✨ AI-tailored resume for this job (~30s)", use_container_width=True):
                from src import ai
                with st.spinner("Tailoring your summary (tries all free models, then offline)..."):
                    new_summary = ai.tailor_summary(job["url"], job["title"], job["company"],
                                                    level, intensity=level_n, emphasize=add_kw)
                    mode = "AI"
                    if not new_summary:
                        new_summary = ai.tailor_summary_offline(job["url"], job["title"], job["company"])
                        mode = "offline"
                if new_summary:
                    st.session_state["ai_summary"] = new_summary
                    st.session_state["ai_summary_mode"] = mode
                else:
                    st.error("Could not tailor — check your OpenRouter key in career-ops/.env.")

        if st.session_state.get("ai_verdict"):
            v = st.session_state["ai_verdict"]
            st.success(f"AI score: **{v.get('score_10','?')}/10** (saved to the table)")
            st.write(f"**Recruiter view:** {v.get('recruiter_view','')}")
            st.write(f"**Hiring-manager view:** {v.get('hiring_manager_view','')}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Strengths:**")
                for s in v.get("strengths", []):
                    st.write("- " + str(s))
            with c2:
                st.markdown("**Gaps:**")
                for s in v.get("gaps", []):
                    st.write("- " + str(s))
            st.markdown("**Resume tweaks for this job:**")
            for s in v.get("resume_tweaks", []):
                st.write("- " + str(s))

        if st.session_state.get("ai_summary"):
            tailored = st.session_state["ai_summary"]
            if st.session_state.get("ai_summary_mode") == "offline":
                st.warning("Free AI models were at their daily cap — used instant offline "
                           "tailoring (keyword-matched, no fabrication).")
            st.markdown("**✨ AI-tailored Professional Summary** (facts only — review before use):")
            st.info(tailored)

            # ── Before → After scores for the tailored resume ──
            import re as _re2
            from src import ai as _ai2
            base_md = rz.load_cv_md()
            tailored_md = _re2.sub(r"(## Professional Summary\s*\n).*?(\n## )",
                                   r"\1" + tailored + r"\2", base_md, count=1, flags=_re2.S)
            new_fit = jd_match.analyze(job["url"], job["title"], resume_override=tailored_md)
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Recruiter", f"{new_fit['recruiter']}/10",
                      delta=round(new_fit['recruiter'] - fit['recruiter'], 1))
            d2.metric("ATS/Workday", f"{new_fit['ats']}/10",
                      delta=round(new_fit['ats'] - fit['ats'], 1))
            d3.metric("Hiring-mgr", f"{new_fit['hiring_manager']}/10",
                      delta=round(new_fit['hiring_manager'] - fit['hiring_manager'], 1))
            d4.metric("OVERALL", f"{new_fit['overall']}/10",
                      delta=round(new_fit['overall'] - fit['overall'], 1))
            st.caption("Green = the tailored summary improved that score vs your base resume. "
                       "Nudge the **Tailoring strength** slider and regenerate to trade fit vs authenticity.")

            # ── Authenticity / over-claim guard ──
            warns = _ai2.authenticity_check(tailored, base_md)
            if warns:
                st.error("⚠️ **Authenticity check — this tailored summary may over-claim:**")
                for w in warns:
                    st.write("- " + w)
                st.caption("Fix these before sending — over-claiming fails interviews and "
                           "background checks. Try a lower Tailoring strength.")
            else:
                st.success("✅ Authenticity check passed — every claim traces to your base resume.")

            from src.sources import slugify as _slug
            html_ai = rz.tailored_resume_html(job["title"], job["company"],
                                              summary_override=tailored)
            st.download_button("⬇ Download AI-TAILORED resume (HTML → Ctrl+P → PDF)",
                               html_ai, f"resume-ai-{_slug(job['company'])[:28]}.html",
                               "text/html", use_container_width=True, type="primary")

        st.divider()
        st.markdown("#### Step 4 — Get your documents & apply")
        colL, colR = st.columns(2)
        with colL:
            st.markdown("##### 📄 ATS-clean resume")
            st.caption("Emoji-free, plain formatting — safe for every ATS parser.")
            html_doc = rz.tailored_resume_html(job["title"], job["company"])
            from src.sources import slugify
            st.download_button("⬇ Download resume (HTML → Ctrl+P → PDF)",
                               html_doc, f"resume-{slugify(job['company'])[:30]}.html",
                               "text/html", use_container_width=True)
            st.download_button("⬇ Download cover letter (.txt)",
                               rz.cover_letter(job["title"], job["company"]),
                               "cover-letter.txt", "text/plain", use_container_width=True)
            if st.button("🤖 Queue for AI-tailored PDF (career-ops)", use_container_width=True):
                st.info(rz.queue_for_ai_tailoring(job["url"]))
            with st.expander("Preview tailored resume"):
                components.html(html_doc, height=600, scrolling=True)
        with colR:
            st.markdown("##### ⚡ Apply kit — copy/paste blocks")
            for label, text in rz.apply_kit().items():
                st.caption(label)
                st.code(text, language=None)
            st.caption("Workday assisted apply (experimental — never auto-submits):")
            if st.button("🚀 Launch assisted apply (opens Chrome)", use_container_width=True):
                import subprocess, sys as _sys
                subprocess.Popen([_sys.executable, "apply_assist.py", job["url"]],
                                 cwd=str(db.DB_PATH.parent.parent),
                                 creationflags=0x00000008)  # DETACHED_PROCESS
                st.info("Chrome window opening... first visit per bank: sign in once, "
                        "it stays saved. Review and press Submit yourself.")
            st.caption("Mark it applied when done:")
            if st.button("✅ Mark this job APPLIED (today)", use_container_width=True):
                conn.execute("UPDATE jobs SET status='applied', date_applied=? WHERE url=?",
                             (db.today(), job["url"]))
                conn.commit()
                st.success("Moved to ✅ Applied with today's date.")
                st.rerun()

# ── Companies tab ───────────────────────────────────────────────────────────
with tab_co:
    st.caption("Auto-grows every scan. Careers pages let you check a company directly, even when boards miss it.")
    co = load("""SELECT name, industry, job_count, careers_url, workday_url,
                        sponsors_h1b, first_seen, last_seen, notes
                 FROM companies ORDER BY job_count DESC, last_seen DESC""")
    kw2 = st.text_input("Filter companies")
    if kw2:
        co = co[co["name"].str.contains(kw2, case=False, na=False)]
    st.dataframe(
        co, hide_index=True, use_container_width=True, height=560,
        column_config={
            "careers_url": st.column_config.LinkColumn("Careers", display_text="open ↗"),
            "workday_url": st.column_config.LinkColumn("Workday API", display_text="json ↗"),
            "job_count": st.column_config.NumberColumn("Jobs seen"),
        },
    )
    st.download_button("⬇ Export companies (CSV)", co.to_csv(index=False),
                       "company-directory.csv", "text/csv")

# ── H-1B Sponsors tab ───────────────────────────────────────────────────────
with tab_h1b:
    from src import sponsors as sp
    st.caption("Sponsor-priority view: apply to **strong** sponsors first. "
               "Seeds come from a curated BFSI map; live counts from public "
               "H-1B disclosure data (h1bdata.info).")
    h = load("""SELECT name, sponsors_h1b, job_count, careers_url
                FROM companies ORDER BY
                  CASE WHEN sponsors_h1b LIKE 'strong%'   THEN 0
                       WHEN sponsors_h1b LIKE '%filings%' AND sponsors_h1b NOT LIKE '0 filings%' THEN 1
                       WHEN sponsors_h1b LIKE 'moderate%' THEN 2
                       WHEN sponsors_h1b = ''             THEN 3
                       ELSE 4 END, job_count DESC""")
    st.dataframe(
        h, hide_index=True, use_container_width=True, height=480,
        column_config={
            "sponsors_h1b": st.column_config.TextColumn("H-1B verdict"),
            "careers_url": st.column_config.LinkColumn("Careers", display_text="open ↗"),
        },
    )
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔎 Live-lookup top unverified (15)"):
            with st.spinner("Querying h1bdata.info (rate-limited, ~30s)..."):
                n = sp.enrich_live(conn, limit=15, verbose=False)
            st.success(f"Updated {n} companies.")
            st.rerun()
    with c2:
        one = st.text_input("Or check one company", placeholder="e.g. Fannie Mae")
        if one:
            cnt = sp.lookup_h1b(one)
            st.write(f"**{one}**: {cnt if cnt is not None else 'lookup failed'} H-1B filings"
                     if cnt is not None else "Lookup failed — try again.")

# ── Summary tab ─────────────────────────────────────────────────────────────
with tab_sum:
    funnel = load("SELECT status, COUNT(*) n FROM jobs GROUP BY status")
    order = {s: i for i, s in enumerate(db.STATUSES)}
    funnel["o"] = funnel["status"].map(order).fillna(99)
    funnel = funnel.sort_values("o").drop(columns="o").set_index("status")
    st.subheader("Pipeline")
    st.bar_chart(funnel)
    st.subheader("Top hiring companies")
    st.dataframe(load("""SELECT company, COUNT(*) jobs,
                                SUM(is_core) core_fit
                         FROM jobs GROUP BY company
                         ORDER BY jobs DESC LIMIT 25"""),
                 hide_index=True, use_container_width=True)
    alljobs = load("SELECT title,company,location,source,status,url FROM jobs")
    st.download_button("⬇ Export all jobs (CSV / open in Excel)",
                       alljobs.to_csv(index=False), "jobs.csv", "text/csv")
