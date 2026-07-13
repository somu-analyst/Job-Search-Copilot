"""Job Search Copilot — Streamlit frontend.

    streamlit run app.py

Presentation only. All business logic lives in src/ (scrapers, scoring, resume,
AI, apply-link resolution); all styling/primitives live in ui/. This file just
wires the two together, so the frontend could be replaced wholesale without
touching a line of logic.

Information architecture
  Today      → the one screen that answers "what do I apply to right now?"
  Jobs       → the full board, power filters behind a popover
  Applied    → pipeline you've acted on, with dates
  Resume     → 4-step studio (pick → fit → tailor → documents) as sub-tabs
  Companies  → the auto-growing employer + ATS directory
  Sponsors   → H-1B priority view
  Insights   → funnel + top employers + exports
"""
from __future__ import annotations
import base64
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src import db
from src.score import MUST_APPLY_AT
import ui

ASSETS = Path(__file__).resolve().parent / "assets"
_ICON = ASSETS / "favicon.png"

st.set_page_config(page_title="Job Search Copilot",
                   page_icon=str(_ICON) if _ICON.exists() else "🏹",
                   layout="wide", initial_sidebar_state="collapsed")
ui.inject()


@st.cache_data
def _logo_b64() -> str:
    """Inline the mark so the hero needs no static-file server."""
    p = ASSETS / "logo-180.png"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


@st.cache_data(ttl=300)
def _hunter_quota() -> dict:
    """Hunter's remaining searches. Doesn't consume quota, but it IS a network
    round-trip — cached so it isn't re-fetched on every rerun."""
    from src import outreach as og
    return og.hunter_quota()

APPLIED_STATES = ("applied", "responded", "interview", "offer")
AGE_OPTS = {"Any time": None, "Today": 0, "1 day": 1, "3 days": 3,
            "1 week": 7, "2 weeks": 14, "1 month": 30}
STEPS = ["Pick a job", "Fit scores", "AI tailor", "Documents & apply"]


# ── data plumbing ───────────────────────────────────────────────────────────
@st.cache_resource
def _conn():
    c = sqlite3.connect(db.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    db.init(c)
    return c


conn = _conn()


def load(sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def posted_days_ago(s) -> int | None:
    """Normalize messy date_posted ('Posted 3 Days Ago', '2026-07-10') to days."""
    s = str(s or "").strip().lower()
    if not s or s in ("none", "nan"):
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
    return int(m.group(1)) if m else None


def _post_process():
    from src import score, sponsors, direct_apply
    score.score_all(conn, verbose=False)
    sponsors.enrich_seeds(conn)
    db.enrich_industries(conn)
    db.backfill_salary(conn)
    direct_apply.resolve_all(conn, verbose=False)   # real employer apply links
    db.archive_stale(conn)


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
            if status_changed and row["status"] in APPLIED_STATES \
                    and not (orig["date_applied"] or ""):
                conn.execute("UPDATE jobs SET date_applied=? WHERE rowid=?",
                             (db.today(), int(orig["rowid"])))
            n += 1
    conn.commit()
    return n


def mark_applied(url: str):
    conn.execute("UPDATE jobs SET status='applied', date_applied=? WHERE url=?",
                 (db.today(), url))
    conn.commit()


# ── quick-view dialog: drill into a job without leaving the list ────────────
@st.dialog("Job details", width="large")
def job_dialog(row: dict):
    from src import jd_match as jdm
    st.markdown(f"### {row['title']}")
    st.caption(f"{row['company']} · {row['location'] or '—'} · "
               f"{row.get('industry') or '—'}")
    st.markdown(ui.chips([
        (f"{row['score']:.1f}/10 fit", ui.score_kind(row["score"])),
        ("MUST APPLY", "w") if row["score"] >= MUST_APPLY_AT else ("", ""),
        (row.get("salary") or "", "p"),
        (row.get("source") or "", "n"),
    ]), unsafe_allow_html=True)

    jd = jdm.fetch_jd(row["url"]) or (row.get("description") or "")
    flags = jdm.jd_flags(jd)
    for b in flags["block"]:
        st.error(f"🚫 {b}")
    for n in flags["note"]:
        st.warning(f"⚠️ {n}")

    if jd.strip():
        with st.expander("📄 Full job description", expanded=False):
            st.markdown(f"<div style='max-height:340px;overflow:auto;font-size:13.5px;"
                        f"line-height:1.6'>{jd}</div>", unsafe_allow_html=True)
    else:
        st.info("Full JD isn't published by this source — open the posting to read it.")

    a, b, c = st.columns(3)
    with a:
        st.link_button("✅ Apply on employer site", row["apply_url"],
                       use_container_width=True, type="primary")
    with b:
        st.link_button("↗ Original posting", row["url"], use_container_width=True)
    with c:
        if st.button("Mark applied", use_container_width=True, key="dlg_applied"):
            mark_applied(row["url"])
            st.rerun()


# ── the jobs board (filters in a popover; table stays the hero) ─────────────
def job_board(kp: str, default_status=None, height=460):
    default_status = default_status if default_status is not None else ["new", "interested"]
    bar_l, bar_r = st.columns([3, 1.15])
    with bar_l:
        kw = st.text_input("Search", placeholder="Search title or company…",
                           key=f"{kp}_kw", label_visibility="collapsed")
    with bar_r:
        with st.popover("⚙️ Filters", use_container_width=True):
            status_f = st.multiselect("Status", db.STATUSES, default=default_status,
                                      key=f"{kp}_status")
            c1, c2 = st.columns(2)
            with c1:
                age_f = st.selectbox("Pulled", list(AGE_OPTS), key=f"{kp}_age")
            with c2:
                posted_f = st.selectbox("Posted", list(AGE_OPTS), key=f"{kp}_posted",
                                        help="Source's own posted date; jobs with "
                                             "no date always pass")
            min_score = st.slider("Min fit", 1.0, 10.0, 1.0, 0.5, key=f"{kp}_min")
            must_only = st.checkbox(f"🔥 Must-apply only (≥ {MUST_APPLY_AT:.0f})",
                                    key=f"{kp}_must")
            core_only = st.checkbox("Core-fit ★ only", key=f"{kp}_core")
            company_f = st.multiselect("Company", [r[0] for r in conn.execute(
                "SELECT DISTINCT company FROM jobs ORDER BY company")], key=f"{kp}_co")
            industry_f = st.multiselect("Industry", [r[0] for r in conn.execute(
                "SELECT DISTINCT industry FROM companies WHERE industry != '' ORDER BY 1")],
                key=f"{kp}_ind")
            source_f = st.multiselect("Source", [r[0] for r in conn.execute(
                "SELECT DISTINCT source FROM jobs")], key=f"{kp}_src")

    q = """SELECT jobs.rowid AS rowid, jobs.url AS url, jobs.title AS title,
                  jobs.company AS company, COALESCE(companies.industry,'') AS industry,
                  jobs.location AS location, jobs.score AS score,
                  jobs.date_posted AS date_posted, jobs.date_found AS date_found,
                  jobs.source AS source, jobs.is_core AS is_core,
                  COALESCE(jobs.salary,'') AS salary,
                  COALESCE(NULLIF(jobs.apply_url,''), jobs.url) AS apply_url,
                  jobs.status AS status, jobs.notes AS notes,
                  jobs.date_applied AS date_applied
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
        d = df["date_posted"].map(posted_days_ago)
        df = df[(d.isna()) | (d <= pmax)].reset_index(drop=True)

    if df.empty:
        ui.empty("🔍", "No jobs match these filters",
                 "Loosen the filters, or run a scan from the sidebar.")
        return

    st.caption(f"**{len(df)} jobs** · set **Status → applied** and it moves to "
               f"Applied with today's date. 🔥 = fit ≥ {MUST_APPLY_AT:.0f}.")
    view = df.drop(columns=["rowid", "is_core", "date_applied"]).copy()
    view.insert(0, "score", view.pop("score"))
    view.insert(0, "🔥", (df["score"] >= MUST_APPLY_AT).map({True: "🔥", False: ""}))
    edited = st.data_editor(
        view, hide_index=True, use_container_width=True, height=height,
        column_config={
            "🔥": st.column_config.TextColumn("🔥", width="small"),
            "apply_url": st.column_config.LinkColumn(
                "Apply", display_text="apply ↗",
                help="Direct link to the employer's own application page — "
                     "skips reposters like Lensa/Talentify."),
            "url": st.column_config.LinkColumn("Source", display_text="src ↗"),
            "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
            "score": st.column_config.NumberColumn("Fit", format="%.1f", width="small",
                     help="1-10 match vs your keywords, seniority, H-1B sponsor history"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "salary": st.column_config.TextColumn("Salary (FYI)",
                     help="Shown when the posting lists pay. Never used to filter."),
            "date_posted": st.column_config.TextColumn("Posted"),
            "date_found": st.column_config.TextColumn("Pulled"),
        },
        disabled=["🔥", "title", "company", "industry", "location", "source", "url",
                  "apply_url", "salary", "score", "date_posted", "date_found"],
        key=f"{kp}_editor")
    if st.button("💾 Save changes", key=f"{kp}_save"):
        st.success(f"Saved {_save_edits(df, edited)} change(s).")
        st.rerun()


# ── Hero + KPI strip ────────────────────────────────────────────────────────
c = db.counts(conn)
n_applied = conn.execute(
    f"SELECT COUNT(*) FROM jobs WHERE status IN {APPLIED_STATES}").fetchone()[0]
n_fire = conn.execute(
    "SELECT COUNT(*) FROM jobs WHERE score>=8 AND status IN ('new','interested')"
).fetchone()[0]
n_link = conn.execute(
    "SELECT COUNT(*) FROM jobs WHERE COALESCE(apply_url,'') != ''").fetchone()[0]

ui.hero("Job Search Copilot",
        "Finds roles across every source, scores them against your resume, "
        "tailors it per job, and links you straight to the employer's own "
        "application page — never a reposter.",
        kicker="find · tailor · apply · track",
        logo_b64=_logo_b64())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Jobs found", f"{c['jobs']:,}")
k2.metric("Must apply", n_fire)
k3.metric("Unreviewed", c["new"])
k4.metric("Applied", n_applied)
k5.metric("Direct links", f"{n_link:,}")

# ── Sidebar: secondary controls only ────────────────────────────────────────
with st.sidebar:
    st.subheader("⚡ Run a scan")
    st.caption("Scrape → filter → dedupe → score → sponsor-tag → resolve apply "
               "links. Token-free.")
    if st.button("⚡ Quick — Workday employers", use_container_width=True):
        from src import scrape_workday
        with st.status("Scanning employer Workday APIs…", expanded=True) as s:
            n = scrape_workday.run(conn, verbose=False)
            st.write(f"Workday: **+{n}** new")
            _post_process()
            s.update(label=f"Done — +{n} new jobs", state="complete")
        st.rerun()
    if st.button("🌐 Full — all sources", use_container_width=True):
        from src import scrape_boards, scrape_workday, scrape_apis
        with st.status("Full scan — keep this tab open…", expanded=True) as s:
            st.write("1/3 Job boards…")
            nb = scrape_boards.run(conn, verbose=False)
            st.write(f"Boards: **+{nb}**")
            st.write("2/3 Workday employer APIs…")
            nw = scrape_workday.run(conn, verbose=False)
            st.write(f"Workday: **+{nw}**")
            st.write("3/3 Aggregator APIs…")
            na = scrape_apis.run(conn, verbose=False)
            st.write(f"APIs: **+{na}**")
            _post_process()
            s.update(label=f"Done — +{nb+nw+na} new jobs", state="complete")
        st.rerun()
    st.divider()

    # ── Hunter.io budget: 50 searches/month, so make the number impossible to miss
    from src import outreach as _og
    if _og.hunter_key():
        _q = _hunter_quota()
        if _q:
            used, avail = _q.get("used", 0), _q.get("available", 50)
            left = max(0, avail - used)
            _cached = conn.execute("SELECT COUNT(*) FROM hunter_cache").fetchone()[0]
            st.subheader("🎯 Recruiter lookups")
            st.progress(min(1.0, used / avail) if avail else 0.0)
            st.caption(f"**{left} of {avail}** left this month · "
                       f"{_cached} employer{'s' if _cached != 1 else ''} already "
                       f"cached (free forever)")
            if left <= 5:
                st.warning("Nearly out — spend the rest on jobs you'll actually apply to.")

    st.caption(f"DB `{db.DB_PATH.name}` · {c['companies']} companies tracked")

# ── Navigation ──────────────────────────────────────────────────────────────
t_today, t_jobs, t_applied, t_resume, t_arch, t_co, t_h1b, t_ins = st.tabs(
    ["🎯 Today", "📋 Jobs", "✅ Applied", "📄 Resume Studio", "🗂 My Resumes",
     "🏢 Companies", "🎫 Sponsors", "📊 Insights"])

# ── Today: the answer to "what do I apply to right now?" ────────────────────
with t_today:
    top = load(f"""SELECT jobs.rowid, jobs.url, jobs.title, jobs.company, jobs.location,
                          jobs.score, jobs.source, jobs.date_posted,
                          COALESCE(jobs.salary,'') salary,
                          COALESCE(jobs.description,'') description,
                          COALESCE(NULLIF(jobs.apply_url,''), jobs.url) apply_url,
                          COALESCE(companies.industry,'') industry,
                          COALESCE(companies.sponsors_h1b,'') sponsor
                   FROM jobs LEFT JOIN companies ON jobs.company = companies.name
                   WHERE jobs.status IN ('new','interested')
                     AND jobs.score >= {MUST_APPLY_AT}
                   ORDER BY jobs.score DESC, jobs.date_found DESC LIMIT 6""")
    ui.section("🔥 Top picks for you",
               "Highest-fit roles you haven't actioned yet. Apply goes straight "
               "to the employer's portal.")
    if top.empty:
        ui.empty("🎉", "Nothing urgent right now",
                 "No unreviewed must-apply roles. Run a scan or browse the Jobs tab.")
    else:
        for i in range(0, len(top), 2):
            cols = st.columns(2)
            for col, (_, r) in zip(cols, top.iloc[i:i+2].iterrows()):
                with col:
                    ui.job_card(r["title"], r["company"], r["location"], r["score"],
                                industry=r["industry"], salary=r["salary"],
                                sponsor=r["sponsor"], source=r["source"])
                    b1, b2 = st.columns(2)
                    with b1:
                        st.link_button("✅ Apply", r["apply_url"],
                                       use_container_width=True, type="primary")
                    with b2:
                        if st.button("View", key=f"v{r['rowid']}",
                                     use_container_width=True):
                            job_dialog(r.to_dict())

    st.divider()
    ui.section("📋 Your queue", "Same power filters as the Jobs tab.")
    job_board("today", default_status=["new", "interested"], height=380)

    st.divider()
    ui.section("⏰ Follow-ups due", "Applied 7+ days ago with no response.")
    fu = load("""SELECT date_applied, title, company, url,
                        CAST(julianday('now') - julianday(date_applied) AS INT) days_ago
                 FROM jobs WHERE status='applied' AND date_applied != ''
                   AND date_applied <= date('now','-7 days')
                 ORDER BY date_applied""")
    if fu.empty:
        st.caption("None due — you're on top of it.")
    else:
        st.dataframe(fu, hide_index=True, use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn(
                         "Link", display_text="open ↗")})

# ── Jobs ────────────────────────────────────────────────────────────────────
with t_jobs:
    ui.section("📋 Every job we found", "Filter, score-sort, and mark status inline.")
    job_board("jobs", default_status=["new", "interested"], height=560)

# ── Applied ─────────────────────────────────────────────────────────────────
with t_applied:
    ui.section("✅ Applications in flight",
               "Update status as companies respond: responded → interview → offer.")
    dfa = load("""SELECT rowid, url, title, company, location, score, date_applied,
                         date_posted, date_found, status, notes
                  FROM jobs
                  WHERE status IN ('applied','responded','interview','offer','rejected')
                  ORDER BY date_applied DESC, score DESC""")
    if dfa.empty:
        ui.empty("📮", "No applications yet",
                 "Mark a job as `applied` from Today or Jobs and it lands here with a date.")
    else:
        edited = st.data_editor(
            dfa.drop(columns=["rowid"]), hide_index=True, use_container_width=True,
            height=500,
            column_config={
                "url": st.column_config.LinkColumn("Link", display_text="open ↗"),
                "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
                "score": st.column_config.NumberColumn("Fit", format="%.1f"),
                "date_applied": st.column_config.TextColumn("Applied on"),
                "title": st.column_config.TextColumn("Title", width="large"),
            },
            disabled=["title", "company", "location", "url", "score",
                      "date_applied", "date_posted", "date_found"],
            key="applied_editor")
        a1, a2 = st.columns([1, 4])
        with a1:
            if st.button("💾 Save", key="applied_save"):
                st.success(f"Saved {_save_edits(dfa, edited)} change(s).")
                st.rerun()
        with a2:
            st.download_button("⬇ Export CSV",
                               dfa.drop(columns=["rowid"]).to_csv(index=False),
                               "applied-jobs.csv", "text/csv")

# ── Resume Studio: 4 steps as sub-tabs = one screen at a time ───────────────
with t_resume:
    from src import resume as rz, jd_match

    picked = st.session_state.get("picked_url")
    step_now = 1 if not picked else st.session_state.get("step_now", 1)
    ui.step_rail(STEPS, step_now)

    s1, s2, s3, s4 = st.tabs([f"1 · {STEPS[0]}", f"2 · {STEPS[1]}",
                              f"3 · {STEPS[2]}", f"4 · {STEPS[3]}"])

    # Step 1 — pick a job from a real table (headers + every column, scrolls)
    with s1:
        f1, f2, f3 = st.columns([2.2, 1.2, 1])
        with f1:
            pk = st.text_input("Search", placeholder="Filter by title or company…",
                               key="pick_search", label_visibility="collapsed")
        with f2:
            pi = st.selectbox("Industry", ["All"] + [r[0] for r in conn.execute(
                "SELECT DISTINCT industry FROM companies WHERE industry != '' ORDER BY 1")],
                key="pick_ind", label_visibility="collapsed")
        with f3:
            pf = st.checkbox("🔥 Must-apply", key="pick_fire")

        pq = """SELECT jobs.url, jobs.title, jobs.company, jobs.score, jobs.location,
                       jobs.source, COALESCE(jobs.salary,'') salary,
                       COALESCE(jobs.description,'') description,
                       COALESCE(NULLIF(jobs.apply_url,''), jobs.url) apply_url,
                       COALESCE(companies.industry,'') industry, jobs.status
                FROM jobs LEFT JOIN companies ON jobs.company = companies.name
                WHERE jobs.status NOT IN ('skip','stale','rejected')"""
        pp = []
        if pk:
            pq += " AND (LOWER(jobs.title) LIKE ? OR LOWER(jobs.company) LIKE ?)"
            pp += [f"%{pk.lower()}%"] * 2
        if pi != "All":
            pq += " AND companies.industry = ?"; pp.append(pi)
        if pf:
            pq += f" AND jobs.score >= {MUST_APPLY_AT}"
        pq += " ORDER BY jobs.score DESC, jobs.date_found DESC LIMIT 300"
        jp = load(pq, pp)

        if jp.empty:
            ui.empty("🔍", "No jobs match", "Loosen the filters or run a scan.")
            st.stop()

        st.caption(f"**{len(jp)} jobs** — click a row to select it. "
                   "Headers stay put while you scroll.")
        grid = jp[["score", "title", "company", "industry", "location", "salary",
                   "status", "apply_url"]].copy()
        grid.insert(0, "🔥", (jp["score"] >= MUST_APPLY_AT).map({True: "🔥", False: ""}))
        ev = st.dataframe(
            grid, hide_index=True, height=260, use_container_width=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "🔥": st.column_config.TextColumn("🔥", width="small"),
                "score": st.column_config.NumberColumn("Fit", format="%.1f", width="small"),
                "title": st.column_config.TextColumn("Title", width="large"),
                "salary": st.column_config.TextColumn("Salary (FYI)"),
                "apply_url": st.column_config.LinkColumn("Apply", display_text="apply ↗"),
            }, key="pick_grid")
        rows = ev.selection.rows if ev and ev.selection else []
        job = jp.iloc[rows[0] if rows else 0]
        st.session_state["picked_url"] = job["url"]
        st.session_state["step_now"] = 2

        ui.job_card(job["title"], job["company"], job["location"], job["score"],
                    industry=job["industry"], salary=job["salary"], source=job["source"])
        b1, b2, _ = st.columns([1.2, 1.2, 2.6])
        with b1:
            st.link_button("✅ Apply on employer site", job["apply_url"],
                           use_container_width=True, type="primary")
        with b2:
            st.link_button("↗ Original posting", job["url"], use_container_width=True)
        st.caption("Selected. Move to **2 · Fit scores** above. →")

    # JD + screening (shared by steps 2-4)
    jd_text = jd_match.fetch_jd(job["url"]) or (job.get("description") or "")
    flags = jd_match.jd_flags(jd_text)

    # Step 2 — fit scores
    with s2:
        if flags["block"]:
            st.error("🚫 **Likely deal-breaker for your H-1B status:** "
                     + " · ".join(flags["block"]) + " — verify before applying.")
        for n in flags["note"]:
            st.warning("⚠️ " + n)

        with st.spinner("Scoring this position against your resume…"):
            fit = jd_match.analyze(job["url"], job["title"], jd_override=jd_text)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Recruiter", f"{fit['recruiter']}/10",
                  help="The 6-second skim: does the TITLE and headline echo your resume?")
        m2.metric("ATS / Workday", f"{fit['ats']}/10",
                  help="Keyword coverage — what the automated filter counts.")
        m3.metric("Hiring manager", f"{fit['hiring_manager']}/10",
                  help="Domain depth + quantified achievements.")
        m4.metric("Overall", f"{fit['overall']}/10")
        st.caption("These are literal **keyword** proxies. The AI deep-dive in step 3 "
                   "reads *meaning* and usually scores transferable fits higher — "
                   "trust it when they disagree.")
        if not fit["jd_available"]:
            st.caption("⚠ Full JD not published by this source — scored from the title only.")

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**✅ Highlights — JD asks, you have**")
            st.write(", ".join(fit["highlights"]) or "—")
        with g2:
            st.markdown("**❌ Missing — JD asks, resume lacks**")
            st.write(", ".join(fit["missing"]) or "Nothing — full coverage!")

        add_kw = []
        if fit["missing"]:
            add_kw = st.multiselect(
                "➕ Weave into the AI-tailored resume — tick ONLY skills you genuinely have",
                fit["missing"], key="add_missing",
                help="The authenticity check still flags anything your base resume "
                     "can't support, so only tick what you can defend in an interview.")

        with st.expander("📄 Read the full job description"):
            if jd_text.strip():
                st.markdown(f"<div style='max-height:420px;overflow:auto;font-size:13.5px;"
                            f"line-height:1.6'>{jd_text}</div>", unsafe_allow_html=True)
            else:
                st.info("This source doesn't publish the JD — use ↗ Original posting.")

    # Step 3 — build several versions, compare, edit, archive
    with s3:
        from src import variants as vz, resume_store as rs
        from src.sources import slugify

        st.markdown("**Generate a few versions and pick the best one.** Each is "
                    "scored against this JD, so you can see what a stronger reframe "
                    "actually buys you — and what it costs in authenticity.")
        gc1, gc2 = st.columns([1.4, 2.6])
        with gc1:
            if st.button("✨ Build resume versions", use_container_width=True,
                         type="primary"):
                with st.spinner("Writing 3 tailored versions and scoring each…"):
                    vs = vz.build(job["url"], job["title"], job["company"],
                                  emphasize=add_kw, jd_override=jd_text)
                for v in vs:                       # archive every version we make
                    if v["mode"] != "base":
                        v["id"] = rs.save(conn, job_url=job["url"],
                                          job_title=job["title"], company=job["company"],
                                          variant=v["label"], summary=v["summary"],
                                          resume_md=v["resume_md"], scores=v["scores"])
                st.session_state["variants"] = vs
                st.session_state.pop("edited_summary", None)
        with gc2:
            st.caption("Versions: **Master** (untouched baseline) · **Conservative** · "
                       "**Balanced** · **ATS-max**. All are archived with this job "
                       "and timestamped — see the 🗂 My Resumes tab.")

        vs = st.session_state.get("variants")
        if not vs:
            ui.empty("📝", "No versions yet",
                     "Click Build resume versions — takes ~30s on free models, "
                     "and falls back to offline tailoring if they're capped.")
        else:
            base = vs[0]["scores"]
            cols = st.columns(len(vs))
            for col, v in zip(cols, vs):
                with col:
                    sc = v["scores"]
                    st.markdown(f"**{v['label']}**")
                    st.caption(v["blurb"])
                    d = None if v["mode"] == "base" else round(
                        sc["overall"] - base["overall"], 1)
                    st.metric("Overall", f"{sc['overall']}/10", delta=d)
                    st.caption(f"ATS {sc['ats']} · Rec {sc['recruiter']} · "
                               f"HM {sc['hiring_manager']}")
                    if v["warnings"]:
                        # A bare count is useless — you can't act on "1 flag".
                        # Click through to see exactly which claim is the problem.
                        with st.popover(f"⚠️ {len(v['warnings'])} over-claim flag"
                                        f"{'s' if len(v['warnings']) > 1 else ''}",
                                        use_container_width=True):
                            st.markdown(f"**{v['label']} — what this version claims "
                                        f"that your resume doesn't back up:**")
                            for w in v["warnings"]:
                                st.warning(w)
                            st.caption("Fix it in the editor below, or use a gentler "
                                       "version. Over-claiming fails interviews and "
                                       "background checks.")
                    elif v["mode"] != "base":
                        st.success("✅ Authentic")

            labels = [v["label"] for v in vs]
            pick = st.radio("Which version do you want to use?", labels,
                            index=min(2, len(labels) - 1), horizontal=True,
                            key="variant_pick")
            chosen = next(v for v in vs if v["label"] == pick)

            if chosen["warnings"]:
                st.error("⚠️ **Authenticity check — this version may over-claim:**")
                for w in chosen["warnings"]:
                    st.write("- " + w)
                st.caption("Over-claiming fails interviews and background checks. "
                           "Edit it below or drop to a gentler version.")

            # ── User edits the summary, then re-scores ──
            st.markdown("**✏️ Edit before you send** — your words always win.")
            start = st.session_state.get("edited_summary") or chosen["summary"] \
                or vs[0]["resume_md"].split("## Professional Summary")[-1]\
                                     .split("##")[0].strip()
            edited = st.text_area("Professional Summary", value=start, height=170,
                                  key="summary_editor",
                                  help="Rewrite freely. Re-score to see what your "
                                       "edit did to the ATS/recruiter numbers.")
            e1, e2 = st.columns([1.2, 2.8])
            with e1:
                if st.button("🔄 Re-score my edit", use_container_width=True):
                    with st.spinner("Re-scoring your edited summary…"):
                        r = vz.rescore_edited(job["url"], job["title"], edited,
                                              jd_override=jd_text)
                    r["id"] = rs.save(conn, job_url=job["url"], job_title=job["title"],
                                      company=job["company"], variant="Edited by me",
                                      summary=edited, resume_md=r["resume_md"],
                                      scores=r["scores"], notes="hand-edited")
                    st.session_state["edited"] = r
                    st.session_state["edited_summary"] = edited
            with e2:
                st.caption("Your edit is archived as its own version — nothing is "
                           "overwritten.")

            ed = st.session_state.get("edited")
            if ed:
                sc = ed["scores"]
                st.markdown("**Your edited version, re-scored:**")
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Recruiter", f"{sc['recruiter']}/10",
                          delta=round(sc["recruiter"] - base["recruiter"], 1))
                q2.metric("ATS / Workday", f"{sc['ats']}/10",
                          delta=round(sc["ats"] - base["ats"], 1))
                q3.metric("Hiring manager", f"{sc['hiring_manager']}/10",
                          delta=round(sc["hiring_manager"] - base["hiring_manager"], 1))
                q4.metric("Overall", f"{sc['overall']}/10",
                          delta=round(sc["overall"] - base["overall"], 1))
                if ed["warnings"]:
                    st.error("⚠️ Your edit may over-claim:")
                    for w in ed["warnings"]:
                        st.write("- " + w)
                else:
                    st.success("✅ Authenticity check passed on your edit.")

            # what step 4 will use
            final_md = (ed or {}).get("resume_md") or chosen["resume_md"]
            final_summary = st.session_state.get("edited_summary") or chosen["summary"]
            st.session_state["final_md"] = final_md
            st.session_state["final_summary"] = final_summary
            st.session_state["final_label"] = "Edited by me" if ed else chosen["label"]

            with st.expander("👁 Preview every version side by side"):
                for v in vs:
                    st.markdown(f"**{v['label']}** — overall {v['scores']['overall']}/10")
                    st.info(v["summary"] or "(your master summary, untouched)")

    # Step 4 — documents, outreach, apply
    with s4:
        from src import resume_store as rs, outreach as og
        from src.sources import slugify

        final_summary = st.session_state.get("final_summary", "")
        final_label = st.session_state.get("final_label", "Master")
        html_doc = rz.tailored_resume_html(job["title"], job["company"],
                                           summary_override=final_summary)

        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**📄 Documents** — using **{final_label}**")
            st.caption("ATS-clean: emoji-free, plain formatting, parser-safe.")
            st.download_button("⬇ Resume (HTML → Ctrl+P → PDF)", html_doc,
                               f"resume-{slugify(job['company'])[:30]}.html",
                               "text/html", use_container_width=True, type="primary")
            st.download_button("⬇ Cover letter (.txt)",
                               rz.cover_letter(job["title"], job["company"]),
                               "cover-letter.txt", "text/plain",
                               use_container_width=True)
            with st.expander("👁 Preview resume"):
                components.html(html_doc, height=520, scrolling=True)

            st.divider()
            st.link_button("✅ Apply on employer site", job["apply_url"],
                           use_container_width=True, type="primary")
            st.caption("Assisted apply opens Chrome and fills what it can — "
                       "it **never** submits for you.")
            if st.button("🚀 Launch assisted apply", use_container_width=True):
                import subprocess, sys
                subprocess.Popen([sys.executable, "apply_assist.py", job["url"]],
                                 cwd=str(db.DB_PATH.parent.parent),
                                 creationflags=0x00000008)  # DETACHED_PROCESS
                st.info("Chrome opening… sign in once per employer; it stays saved. "
                        "Review and press Submit yourself.")
            if st.button("✅ Mark applied (archives this resume)",
                         use_container_width=True):
                mark_applied(job["url"])
                rid = rs.save(conn, job_url=job["url"], job_title=job["title"],
                              company=job["company"], variant=final_label,
                              summary=final_summary,
                              resume_md=st.session_state.get("final_md", ""),
                              notes="sent with application")
                rs.mark_applied(conn, rid)
                st.success("Applied ✓ — this exact resume is saved in 🗂 My Resumes.")
                st.rerun()

        with d2:
            st.markdown("**✉️ Reach a human**")
            st.caption("We use contacts the employer **published**, and open a draft in "
                       "*your* mail client. We don't scrape LinkedIn — that risks your "
                       "account and cold blasts get binned anyway.")

            found = og.contacts_from_jd(jd_text)
            careers = conn.execute("SELECT careers_url FROM companies WHERE name=?",
                                   (job["company"],)).fetchone()
            domain = og.domain_for(job["company"], (careers[0] if careers else "") or "")

            if found["emails"]:
                st.success(f"📧 Published in the JD: {', '.join(found['emails'])}")
            if found["names"]:
                st.info(f"👤 Named in the JD: {', '.join(found['names'])}")
            if not found["emails"] and not found["names"]:
                st.caption("No contact published in this JD — look them up below, "
                           "or use the LinkedIn searches.")

            # ── Hunter.io: real HR contacts. 50 searches/MONTH, so a lookup only
            # happens on an explicit press and is then cached forever per domain.
            hunted = og.hunter_cached(conn, domain)
            if og.hunter_key():
                if hunted["cached"] and hunted["emails"]:
                    st.success(f"🎯 **{len(hunted['emails'])} HR contacts** at "
                               f"{domain} *(cached — no search spent)*")
                elif hunted["cached"]:
                    st.caption(f"Hunter had no contacts for {domain} "
                               "*(already checked — not spending another search)*")
                elif found["emails"]:
                    # The JD already names someone. Spending one of 50 searches to
                    # find a contact you were handed for free is the easiest way
                    # to burn the budget.
                    st.caption("✅ The posting already gives you a contact — "
                               "no need to spend a lookup.")
                else:
                    q = og.hunter_quota()
                    left = (q["available"] - q["used"]) if q else None
                    lbl = (f"{left} of {q['available']} left this month"
                           if q else "free plan")
                    if left == 0:
                        st.warning("Hunter.io searches exhausted for this month.")
                    elif st.button(f"🔎 Find recruiters at {job['company'][:20]}",
                                   use_container_width=True,
                                   help=f"Spends ONE Hunter.io search ({lbl}). "
                                        f"Cached forever after, so this employer is "
                                        f"never looked up twice — and one search "
                                        f"covers every job they post."):
                        with st.spinner(f"Looking up {domain}…"):
                            hunted = og.hunter_cached(conn, domain, allow_fetch=True)
                        st.rerun()
                    if left is not None:
                        st.caption(f"Hunter.io: **{lbl}**")

            if hunted["emails"]:
                if hunted["pattern"]:
                    st.caption(f"Email pattern at {domain}: `{hunted['pattern']}`")
                for e in hunted["emails"][:8]:
                    nm = f"{e.get('first_name','')} {e.get('last_name','')}".strip()
                    pos = e.get("position") or ""
                    with st.container(border=True):
                        st.markdown(f"**{nm or e['value']}** — {pos or 'HR'}")
                        st.code(e["value"], language=None)
                        subj_h, body_h = og.draft_email(
                            name=nm,
                            title="Senior Fraud & Credit Risk Data Analytics professional",
                            company=job["company"], job_title=job["title"],
                            highlights=fit.get("highlights", [])[:2],
                            job_url=job["url"])
                        st.link_button("📨 Draft an email to them",
                                       og.mailto(e["value"], subj_h, body_h),
                                       use_container_width=True)

            st.markdown("**Find them on LinkedIn** (you connect manually)")
            for role in ("recruiter", "talent acquisition", "hiring manager"):
                st.link_button(f"🔗 {role.title()} at {job['company'][:22]}",
                               og.linkedin_search(job["company"], role),
                               use_container_width=True)

            with st.popover("🔍 Guess their email pattern", use_container_width=True):
                st.caption(f"Corporate mail domain (guess): **{domain or 'unknown'}**")
                gn1, gn2 = st.columns(2)
                first = gn1.text_input("First name", key="og_first")
                last = gn2.text_input("Last name", key="og_last")
                if first and last and domain:
                    st.caption("Likely address shapes — **verify before sending**, "
                               "these are guesses, not confirmed addresses:")
                    for e in og.email_patterns(first, last, domain):
                        st.code(e, language=None)

            fit_now = st.session_state.get("variants")
            highlights = (fit_now[0]["scores"]["highlights"][:2] if fit_now
                          else fit.get("highlights", [])[:2])
            to = (found["emails"] or [""])[0]
            nm = (found["names"] or [""])[0]
            subj, body = og.draft_email(
                name=nm, title="Senior Fraud & Credit Risk Data Analytics professional",
                company=job["company"], job_title=job["title"],
                highlights=highlights, job_url=job["url"])
            with st.expander("✉️ Draft outreach email (you review & send)"):
                subj = st.text_input("Subject", value=subj, key="og_subj")
                body = st.text_area("Body", value=body, height=230, key="og_body")
                to = st.text_input("To", value=to, key="og_to",
                                   placeholder="recruiter@company.com")
                if to:
                    st.link_button("📨 Open in my mail app", og.mailto(to, subj, body),
                                   use_container_width=True, type="primary")
                    st.caption("Opens your own mail client, pre-filled and **unsent**. "
                               "Read it, personalise the first line, then send.")
                else:
                    st.caption("Add a recipient to enable the draft.")

# ── My Resumes: every version, with the job it was written for ──────────────
with t_arch:
    from src import resume as rz2, resume_store as rs2
    ui.section("🗂 Resume archive",
               "Every version you generated or edited, timestamped and tied to its "
               "job. Months from now, when a recruiter calls, you'll know exactly "
               "which resume they're holding.")

    only_sent = st.toggle("Show only the ones I actually applied with", value=False)
    rows = rs2.history(conn, applied_only=only_sent)
    if not rows:
        ui.empty("🗂", "No resumes archived yet",
                 "Open Resume Studio → pick a job → Build resume versions. "
                 "Every version is saved here automatically.")
    else:
        arch = pd.DataFrame([dict(r) for r in rows])
        arch["sent"] = arch["used_to_apply"].map({1: "✅ sent", 0: ""})
        show = arch[["id", "created_at", "sent", "applied_at", "company", "job_title",
                     "variant", "overall", "ats", "recruiter", "hiring_manager"]]
        ev2 = st.dataframe(
            show, hide_index=True, use_container_width=True, height=340,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "id": st.column_config.NumberColumn("#", width="small"),
                "created_at": st.column_config.TextColumn("Created"),
                "applied_at": st.column_config.TextColumn("Applied"),
                "job_title": st.column_config.TextColumn("Role", width="large"),
                "overall": st.column_config.NumberColumn("Overall", format="%.1f"),
                "ats": st.column_config.NumberColumn("ATS", format="%.1f"),
                "recruiter": st.column_config.NumberColumn("Rec", format="%.1f"),
                "hiring_manager": st.column_config.NumberColumn("HM", format="%.1f"),
            }, key="arch_grid")
        sel = ev2.selection.rows if ev2 and ev2.selection else []
        if sel:
            r = rs2.get(conn, int(arch.iloc[sel[0]]["id"]))
            st.markdown(f"#### {r['variant']} — {r['job_title']} @ {r['company']}")
            st.caption(f"Created {r['created_at']}"
                       + (f" · applied {r['applied_at']}" if r["used_to_apply"] else ""))
            if r["summary"]:
                st.info(r["summary"])
            html_v = rz2.tailored_resume_html(r["job_title"], r["company"],
                                              summary_override=r["summary"] or "")
            st.download_button("⬇ Download this exact resume", html_v,
                               f"resume-{r['id']}.html", "text/html")
            with st.expander("👁 Preview the resume as it was sent"):
                components.html(html_v, height=520, scrolling=True)
        st.download_button("⬇ Export archive (CSV)", arch.to_csv(index=False),
                           "resume-archive.csv", "text/csv")

# ── Companies ───────────────────────────────────────────────────────────────
with t_co:
    ui.section("🏢 Employer directory",
               "Auto-grows every scan. `ATS` is how they take applications — that's "
               "what powers direct apply links.")
    co = load("""SELECT name, industry, COALESCE(ats,'') ats, job_count, careers_url,
                        workday_url, sponsors_h1b, first_seen, last_seen
                 FROM companies ORDER BY job_count DESC, last_seen DESC""")
    kw2 = st.text_input("Search", placeholder="Filter companies…",
                        key="co_kw", label_visibility="collapsed")
    if kw2:
        co = co[co["name"].str.contains(kw2, case=False, na=False)]
    st.dataframe(co, hide_index=True, use_container_width=True, height=520,
                 column_config={
                     "careers_url": st.column_config.LinkColumn("Careers",
                                                                display_text="open ↗"),
                     "workday_url": st.column_config.LinkColumn("Workday API",
                                                                display_text="json ↗"),
                     "ats": st.column_config.TextColumn("ATS",
                            help="Applicant system we resolve apply links through."),
                     "job_count": st.column_config.NumberColumn("Jobs seen"),
                 })
    st.download_button("⬇ Export companies (CSV)", co.to_csv(index=False),
                       "company-directory.csv", "text/csv")

# ── Sponsors ────────────────────────────────────────────────────────────────
with t_h1b:
    from src import sponsors as sp
    ui.section("🎫 H-1B sponsor priority",
               "Apply to **strong** sponsors first. Seeds from a curated employer map; "
               "live counts from public H-1B disclosure data.")
    h = load("""SELECT name, sponsors_h1b, job_count, careers_url FROM companies
                ORDER BY CASE
                  WHEN sponsors_h1b LIKE 'strong%' THEN 0
                  WHEN sponsors_h1b LIKE '%filings%'
                       AND sponsors_h1b NOT LIKE '0 filings%' THEN 1
                  WHEN sponsors_h1b LIKE 'moderate%' THEN 2
                  WHEN sponsors_h1b = '' THEN 3 ELSE 4 END, job_count DESC""")
    st.dataframe(h, hide_index=True, use_container_width=True, height=440,
                 column_config={
                     "sponsors_h1b": st.column_config.TextColumn("H-1B verdict"),
                     "careers_url": st.column_config.LinkColumn("Careers",
                                                                display_text="open ↗"),
                 })
    q1, q2 = st.columns([1, 2])
    with q1:
        if st.button("🔎 Live-lookup top 15 unverified", use_container_width=True):
            with st.spinner("Querying h1bdata.info (rate-limited, ~30s)…"):
                n = sp.enrich_live(conn, limit=15, verbose=False)
            st.success(f"Updated {n} companies.")
            st.rerun()
    with q2:
        one = st.text_input("Check one company", placeholder="e.g. Fannie Mae",
                            label_visibility="collapsed")
        if one:
            cnt = sp.lookup_h1b(one)
            st.write(f"**{one}**: {cnt} H-1B filings" if cnt is not None
                     else "Lookup failed — try again.")

# ── Insights ────────────────────────────────────────────────────────────────
with t_ins:
    ui.section("📊 Pipeline", "Where every job you've found currently sits.")
    funnel = load("SELECT status, COUNT(*) n FROM jobs GROUP BY status")
    order = {s: i for i, s in enumerate(db.STATUSES)}
    funnel["o"] = funnel["status"].map(order).fillna(99)
    funnel = funnel.sort_values("o").drop(columns="o").set_index("status")
    st.bar_chart(funnel, color="#4F46E5", height=260)

    ui.section("🏆 Top hiring employers", "Who posts the most roles you match.")
    st.dataframe(load("""SELECT company, COUNT(*) jobs, SUM(is_core) core_fit
                         FROM jobs GROUP BY company ORDER BY jobs DESC LIMIT 25"""),
                 hide_index=True, use_container_width=True, height=340)
    st.download_button("⬇ Export all jobs (CSV)",
                       load("SELECT title,company,location,source,status,salary,"
                            "apply_url,url FROM jobs").to_csv(index=False),
                       "jobs.csv", "text/csv")
