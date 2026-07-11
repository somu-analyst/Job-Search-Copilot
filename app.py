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
m1, m2, m3 = st.columns(3)
m1.metric("Jobs found", c["jobs"])
m2.metric("Unreviewed", c["new"])
m3.metric("Companies", c["companies"])

tab_jobs, tab_co, tab_h1b, tab_sum = st.tabs(
    ["📋 Jobs", "🏢 Companies", "🎫 H-1B Sponsors", "📊 Summary"])

# ── Jobs tab ────────────────────────────────────────────────────────────────
with tab_jobs:
    left, right = st.columns([3, 1])
    with right:
        status_f = st.multiselect("Status", db.STATUSES, default=["new", "interested"])
        core_only = st.checkbox("Core-fit only (fraud/risk/AML/SAS)", value=False)
        kw = st.text_input("Search title/company")
    q = "SELECT rowid, url, title, company, location, source, is_core, status, score, notes FROM jobs WHERE 1=1"
    p = []
    if status_f:
        q += f" AND status IN ({','.join('?'*len(status_f))})"; p += status_f
    if core_only:
        q += " AND is_core = 1"
    if kw:
        q += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"; p += [f"%{kw.lower()}%"]*2
    q += " ORDER BY score DESC, is_core DESC, date_found DESC"
    df = load(q, p)

    with left:
        st.caption(f"{len(df)} jobs — edit **Status** / **Notes**, click a URL to open, then Save.")
    if df.empty:
        st.info("No jobs yet. Run `python run.py` to fetch some.")
    else:
        view = df.drop(columns=["rowid"]).copy()
        view.insert(0, "★", view.pop("is_core").map({1: "★", 0: ""}))
        edited = st.data_editor(
            view, hide_index=True, use_container_width=True, height=560,
            column_config={
                "url": st.column_config.LinkColumn("Link", display_text="open ↗"),
                "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
                "score": st.column_config.NumberColumn("Score", format="%.1f"),
                "title": st.column_config.TextColumn("Title", width="large"),
            },
            disabled=["★", "title", "company", "location", "source", "url", "score"],
            key="jobs_editor",
        )
        if st.button("💾 Save changes", type="primary"):
            n = 0
            for i, row in edited.iterrows():
                orig = df.iloc[i]
                if row["status"] != orig["status"] or (row.get("notes") or "") != (orig["notes"] or ""):
                    conn.execute("UPDATE jobs SET status=?, notes=? WHERE rowid=?",
                                 (row["status"], row.get("notes") or "", int(orig["rowid"])))
                    n += 1
            conn.commit()
            st.success(f"Saved {n} change(s).")
            st.rerun()

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
