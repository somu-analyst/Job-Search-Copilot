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
import re
import sqlite3
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src import db
from src.score import MUST_APPLY_AT
import ui

st.set_page_config(page_title="Job Search Copilot", page_icon="🧭",
                   layout="wide", initial_sidebar_state="collapsed")
ui.inject()

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
               f"{row.get('industry') or 'BFSI'}")
    st.markdown(ui.chips([
        (f"{row['score']:.1f}/10 fit", ui.score_kind(row["score"])),
        ("MUST APPLY", "w") if row["score"] >= MUST_APPLY_AT else ("", ""),
        (row.get("salary") or "", "a"),
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
        "Finds BFSI roles across every source, scores them against your resume, "
        "tailors it per job, and links you straight to the employer's own "
        "application page — never a reposter.",
        kicker="find · tailor · apply · track")

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
    if st.button("🏦 Quick — Workday banks", use_container_width=True):
        from src import scrape_workday
        with st.status("Scanning bank Workday APIs…", expanded=True) as s:
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
            st.write("2/3 Workday bank APIs…")
            nw = scrape_workday.run(conn, verbose=False)
            st.write(f"Workday: **+{nw}**")
            st.write("3/3 Aggregator APIs…")
            na = scrape_apis.run(conn, verbose=False)
            st.write(f"APIs: **+{na}**")
            _post_process()
            s.update(label=f"Done — +{nb+nw+na} new jobs", state="complete")
        st.rerun()
    st.divider()
    st.caption(f"DB `{db.DB_PATH.name}` · {c['companies']} companies tracked")

# ── Navigation ──────────────────────────────────────────────────────────────
t_today, t_jobs, t_applied, t_resume, t_co, t_h1b, t_ins = st.tabs(
    ["🎯 Today", "📋 Jobs", "✅ Applied", "📄 Resume Studio", "🏢 Companies",
     "🎫 Sponsors", "📊 Insights"])

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

    # Step 3 — AI deep-dive & tailoring
    with s3:
        a1, a2 = st.columns(2)
        with a1:
            st.markdown("**🤖 AI deep analysis**")
            st.caption("A free model reads the JD against your resume and judges fit.")
            if st.button("Run AI analysis (~30s)", use_container_width=True):
                from src import ai
                with st.spinner("Free model reading the JD vs your resume…"):
                    v = ai.analyze_job(job["url"], job["title"], job["company"])
                if v:
                    st.session_state["ai_verdict"] = v
                    conn.execute("UPDATE jobs SET score=?, notes=? WHERE url=?",
                                 (float(v.get("score_10", job["score"])), "AI-scored",
                                  job["url"]))
                    conn.commit()
                else:
                    from src import ai as _a
                    st.warning("Free AI models are at their daily cap — the keyword "
                               f"scores in step 2 still apply. ({_a.last_error() or 'busy'})")
        with a2:
            st.markdown("**✨ AI-tailored summary**")
            lvl = st.slider("Tailoring strength (1 = light · 10 = strong reframe)",
                            1, 10, 5, key="tailor_level",
                            help="Higher lifts the ATS score but raises over-claim risk — "
                                 "the authenticity check flags it.")
            band = "Conservative" if lvl <= 3 else "Balanced" if lvl <= 7 else "Aggressive"
            st.caption(f"Level {lvl}/10 — **{band}**")
            if st.button("Tailor my resume (~30s)", use_container_width=True):
                from src import ai
                with st.spinner("Tailoring (all free models, then offline fallback)…"):
                    s = ai.tailor_summary(job["url"], job["title"], job["company"],
                                          band, intensity=lvl, emphasize=add_kw)
                    mode = "AI"
                    if not s:
                        s = ai.tailor_summary_offline(job["url"], job["title"],
                                                      job["company"])
                        mode = "offline"
                if s:
                    st.session_state["ai_summary"] = s
                    st.session_state["ai_summary_mode"] = mode
                else:
                    st.error("Could not tailor — check your OpenRouter key.")

        if st.session_state.get("ai_verdict"):
            v = st.session_state["ai_verdict"]
            st.success(f"AI score: **{v.get('score_10','?')}/10** (saved to the table)")
            st.write(f"**Recruiter view:** {v.get('recruiter_view','')}")
            st.write(f"**Hiring-manager view:** {v.get('hiring_manager_view','')}")
            v1, v2 = st.columns(2)
            with v1:
                st.markdown("**Strengths**")
                for x in v.get("strengths", []):
                    st.write("- " + str(x))
            with v2:
                st.markdown("**Gaps**")
                for x in v.get("gaps", []):
                    st.write("- " + str(x))
            st.markdown("**Resume tweaks for this job**")
            for x in v.get("resume_tweaks", []):
                st.write("- " + str(x))

        if st.session_state.get("ai_summary"):
            from src import ai as _ai
            tailored = st.session_state["ai_summary"]
            if st.session_state.get("ai_summary_mode") == "offline":
                st.warning("Free models were capped — used instant offline tailoring "
                           "(keyword-matched, no fabrication).")
            st.markdown("**✨ Tailored Professional Summary** — facts only, review before use")
            st.info(tailored)

            base_md = rz.load_cv_md()
            tailored_md = re.sub(r"(## Professional Summary\s*\n).*?(\n## )",
                                 r"\1" + tailored + r"\2", base_md, count=1, flags=re.S)
            nf = jd_match.analyze(job["url"], job["title"], resume_override=tailored_md)
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Recruiter", f"{nf['recruiter']}/10",
                      delta=round(nf["recruiter"] - fit["recruiter"], 1))
            d2.metric("ATS / Workday", f"{nf['ats']}/10",
                      delta=round(nf["ats"] - fit["ats"], 1))
            d3.metric("Hiring manager", f"{nf['hiring_manager']}/10",
                      delta=round(nf["hiring_manager"] - fit["hiring_manager"], 1))
            d4.metric("Overall", f"{nf['overall']}/10",
                      delta=round(nf["overall"] - fit["overall"], 1))
            st.caption("Green = the tailored summary improved that score vs your base "
                       "resume. Nudge the strength slider to trade fit against authenticity.")

            warns = _ai.authenticity_check(tailored, base_md)
            if warns:
                st.error("⚠️ **Authenticity check — this may over-claim:**")
                for w in warns:
                    st.write("- " + w)
                st.caption("Fix these before sending — over-claiming fails interviews "
                           "and background checks. Try a lower strength.")
            else:
                st.success("✅ Authenticity check passed — every claim traces to your resume.")

            from src.sources import slugify
            st.download_button(
                "⬇ Download AI-tailored resume (HTML → Ctrl+P → PDF)",
                rz.tailored_resume_html(job["title"], job["company"],
                                        summary_override=tailored),
                f"resume-ai-{slugify(job['company'])[:28]}.html", "text/html",
                use_container_width=True, type="primary")

    # Step 4 — documents & apply
    with s4:
        from src.sources import slugify
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**📄 ATS-clean documents**")
            st.caption("Emoji-free, plain formatting — safe for every ATS parser.")
            html_doc = rz.tailored_resume_html(job["title"], job["company"])
            st.download_button("⬇ Resume (HTML → Ctrl+P → PDF)", html_doc,
                               f"resume-{slugify(job['company'])[:30]}.html",
                               "text/html", use_container_width=True)
            st.download_button("⬇ Cover letter (.txt)",
                               rz.cover_letter(job["title"], job["company"]),
                               "cover-letter.txt", "text/plain", use_container_width=True)
            with st.expander("Preview resume"):
                components.html(html_doc, height=560, scrolling=True)
        with d2:
            st.markdown("**⚡ Apply kit** — copy/paste blocks")
            for label, text in rz.apply_kit().items():
                with st.popover(label, use_container_width=True):
                    st.code(text, language=None)
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
            if st.button("✅ Mark this job applied (today)", use_container_width=True):
                mark_applied(job["url"])
                st.success("Moved to ✅ Applied with today's date.")
                st.rerun()

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
               "Apply to **strong** sponsors first. Seeds from a curated BFSI map; "
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
