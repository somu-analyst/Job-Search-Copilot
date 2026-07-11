"""bfsi-job-hunter — Streamlit frontend.

    streamlit run app.py

Three tabs:
  Jobs       — filterable table of every discovered posting; edit status inline
               (new / interested / applied / interview / offer / rejected / skip).
  Companies  — the auto-growing directory: who's hiring, careers pages, Workday.
  Summary    — pipeline funnel + counts.

Reads/writes data/jobs.db. No API key, fully local.
"""
import sqlite3
import pandas as pd
import streamlit as st

from src import db

st.set_page_config(page_title="BFSI Job Hunter", page_icon="💼", layout="wide")


@st.cache_resource
def _conn():
    c = sqlite3.connect(db.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    db.init(c)
    return c


conn = _conn()


def load(sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


st.title("💼 BFSI Job Hunter")
c = db.counts(conn)
n_applied = conn.execute(
    "SELECT COUNT(*) FROM jobs WHERE status IN ('applied','responded','interview','offer')"
).fetchone()[0]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Jobs found", c["jobs"])
m2.metric("Unreviewed", c["new"])
m3.metric("Applied", n_applied)
m4.metric("Companies", c["companies"])


def _post_process():
    from src import score, sponsors
    score.score_all(conn, verbose=False)
    sponsors.enrich_seeds(conn)
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

tab_jobs, tab_applied, tab_co, tab_h1b, tab_sum = st.tabs(
    ["📋 Jobs", "✅ Applied", "🏢 Companies", "🎫 H-1B Sponsors", "📊 Summary"])

# ── Jobs tab ────────────────────────────────────────────────────────────────
from src.score import MUST_APPLY_AT

APPLIED_STATES = ("applied", "responded", "interview", "offer")


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


with tab_jobs:
    with st.expander("🔍 Filters", expanded=True):
        f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1.2])
        with f1:
            status_f = st.multiselect("Status", db.STATUSES, default=["new", "interested"])
        with f2:
            min_score = st.slider("Min score (1–10)", 1.0, 10.0, 1.0, 0.5)
            must_only = st.checkbox(f"🔥 Must-apply only (≥ {MUST_APPLY_AT:.0f})")
        with f3:
            companies_all = [r[0] for r in conn.execute(
                "SELECT DISTINCT company FROM jobs ORDER BY company")]
            company_f = st.multiselect("Company", companies_all)
            source_f = st.multiselect("Source", [r[0] for r in conn.execute(
                "SELECT DISTINCT source FROM jobs")])
        with f4:
            kw = st.text_input("Search title/company")
            core_only = st.checkbox("Core-fit ★ only")

    q = """SELECT rowid, url, title, company, location, score, date_posted,
                  date_found, source, is_core, status, notes, date_applied
           FROM jobs WHERE score >= ?"""
    p = [must_only and MUST_APPLY_AT or min_score]
    if status_f:
        q += f" AND status IN ({','.join('?'*len(status_f))})"; p += status_f
    if company_f:
        q += f" AND company IN ({','.join('?'*len(company_f))})"; p += company_f
    if source_f:
        q += f" AND source IN ({','.join('?'*len(source_f))})"; p += source_f
    if core_only:
        q += " AND is_core = 1"
    if kw:
        q += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"; p += [f"%{kw.lower()}%"]*2
    q += " ORDER BY score DESC, date_found DESC"
    df = load(q, p)

    st.caption(f"{len(df)} jobs — set **Status** to `applied` and it moves to the "
               f"✅ Applied tab with today's date. 🔥 = must apply (score ≥ {MUST_APPLY_AT:.0f}).")
    if df.empty:
        st.info("No jobs match. Loosen filters or run a scan from the sidebar.")
    else:
        view = df.drop(columns=["rowid", "is_core", "date_applied"]).copy()
        view.insert(0, "🔥 Must", (df["score"] >= MUST_APPLY_AT).map({True: "🔥 YES", False: ""}))
        edited = st.data_editor(
            view, hide_index=True, use_container_width=True, height=520,
            column_config={
                "url": st.column_config.LinkColumn("Link", display_text="open ↗"),
                "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
                "score": st.column_config.NumberColumn("Score", format="%.1f / 10"),
                "title": st.column_config.TextColumn("Title", width="large"),
                "date_posted": st.column_config.TextColumn("Posted"),
                "date_found": st.column_config.TextColumn("Pulled"),
            },
            disabled=["🔥 Must", "title", "company", "location", "source", "url",
                      "score", "date_posted", "date_found"],
            key="jobs_editor",
        )
        if st.button("💾 Save changes", type="primary"):
            n = _save_edits(df, edited)
            st.success(f"Saved {n} change(s).")
            st.rerun()

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

# ── Companies tab ───────────────────────────────────────────────────────────
with tab_co:
    st.caption("Auto-grows every scan. Careers pages let you check a company directly, even when boards miss it.")
    co = load("""SELECT name, job_count, careers_url, workday_url, sponsors_h1b,
                        first_seen, last_seen, notes
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
