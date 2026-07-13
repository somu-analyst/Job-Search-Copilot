"""What is this job actually ABOUT? — skill tags for the queue.

The fit score answers "how good is this?" in one number, but it throws away the
reason. Two jobs both scoring 8.5 can be a SAS credit-risk role and a Python
fraud-ML role, and you would apply to them with different resumes. So the score
alone can't drive the decision — you need the *why* back.

That's what this module restores: a short, ordered list of tags per job that
says "AML · SAS · SQL", which is (a) the column you scan and (b) the thing you
filter on ("show me only the SAS + credit-risk ones").

Two deliberate design choices:

1. **Tags are a curated display vocabulary, not the raw POSITIVE list.**
   POSITIVE is ~60 lowercase substrings tuned for *recall* during scraping —
   "risk analy", "anti-money", "data analy". Those are matching fragments, not
   labels a human wants to read in a table. Here each tag has ONE clean display
   name and many patterns that map onto it, so "anti-money laundering", "AML"
   and "BSA" all collapse to a single `AML` chip instead of three near-duplicates.

2. **Ordered by decision value, not by score or alphabet.** Domain first (AML,
   Fraud, Credit Risk) because that's what makes a job yours or not; tools after
   (SAS, Python, SQL) because they're the tiebreak. A tag list that leads with
   "SQL" tells you nothing — every job has SQL.
"""
from __future__ import annotations
import re

# (display name, [regex patterns]) — ORDER IS THE PRIORITY ORDER shown in the UI.
# Domain -> regulation -> technique -> tool. Most-deciding signal first.
TAGS: list[tuple[str, list[str]]] = [
    # ── domain: what the job is
    ("Fraud",        [r"\bfraud\b", r"\bscam\b", r"\bchargeback"]),
    ("AML",          [r"\baml\b", r"anti[- ]money", r"\bbsa\b", r"money launder",
                      r"financial crime", r"transaction monitoring", r"\bsar\b"]),
    ("KYC",          [r"\bkyc\b", r"\bcdd\b", r"\bedd\b", r"know your customer",
                      r"customer due diligence", r"onboarding risk"]),
    ("Sanctions",    [r"sanction", r"\bofac\b", r"watchlist", r"screening"]),
    ("Credit Risk",  [r"credit risk", r"\bunderwrit", r"\bcredit\b.*\bportfolio",
                      r"loss forecast", r"\bpd\b.*\blgd\b", r"delinquen",
                      r"charge[- ]?off", r"collections?\b", r"\brecover"]),
    ("Market Risk",  [r"market risk", r"\bvar\b", r"counterparty", r"liquidity risk"]),
    ("Model Risk",   [r"model risk", r"model validation", r"model governance",
                      r"\bsr 11[- ]7\b"]),
    ("Compliance",   [r"complian", r"regulatory", r"\bfincen\b", r"audit"]),
    ("CCAR/CECL",    [r"\bccar\b", r"\bcecl\b", r"stress test", r"\bdfast\b",
                      r"\bbasel\b", r"capital adequacy"]),
    ("Mortgage",     [r"mortgage", r"\bservicing\b", r"loss mitigation",
                      r"foreclos", r"\bhmda\b"]),
    ("Data Gov",     [r"data governance", r"data quality", r"data lineage",
                      r"\bmetadata\b", r"master data", r"data steward"]),

    # ── technique
    ("ML",           [r"machine learning", r"\bml\b", r"\bai\b", r"deep learning",
                      r"predictive model", r"\bxgboost\b", r"random forest",
                      r"neural net", r"data scien"]),
    ("Modeling",     [r"\bmodel(ing|ling)\b", r"statistical model", r"regression",
                      r"scorecard", r"segmentation"]),

    # ── tools: the tiebreak, never the headline
    ("SAS",          [r"\bsas\b", r"\bviya\b", r"\bsas/?stat\b", r"enterprise guide"]),
    ("Python",       [r"\bpython\b", r"\bpandas\b", r"\bpyspark\b"]),
    ("SQL",          [r"\bsql\b", r"\bteradata\b", r"\bsnowflake\b", r"\boracle\b",
                      r"\bredshift\b"]),
    ("R",            [r"(?<![a-z])r programming", r"\bin r\b", r"\br studio\b"]),
    ("Tableau",      [r"\btableau\b"]),
    ("Power BI",     [r"power ?bi\b"]),
    ("Spark",        [r"\bspark\b", r"\bhadoop\b", r"\bhive\b", r"\bdatabricks\b"]),
    ("Cloud",        [r"\baws\b", r"\bazure\b", r"\bgcp\b", r"\bcloud\b"]),
    ("Excel/VBA",    [r"\bvba\b", r"advanced excel", r"\bmacros?\b"]),
]

_COMPILED = [(name, re.compile("|".join(pats), re.I)) for name, pats in TAGS]

# Every tag we can emit, in priority order — the filter's option list.
ALL_TAGS = [name for name, _ in TAGS]

# The title is a claim; the description is evidence. A tag found in the TITLE is
# what the job IS. Found only in the body it may be a nice-to-have buried in a
# requirements list — still worth showing, just never ahead of a title hit.
MAX_SHOWN = 5


def tags_for(title: str, description: str = "") -> list[str]:
    """Ordered skill tags for one job. Title hits outrank description hits."""
    t, d = title or "", (description or "")[:6000]   # long JDs add noise, not signal
    in_title, in_body = [], []
    for name, rx in _COMPILED:
        if rx.search(t):
            in_title.append(name)
        elif rx.search(d):
            in_body.append(name)
    return (in_title + in_body)[:MAX_SHOWN]


def tag_all(conn, rescore: bool = False, verbose: bool = True) -> int:
    """Compute tags for every job and cache them in jobs.tags (comma-joined).

    Cached rather than computed per render: the queue re-renders on every filter
    change, and re-regexing thousands of JDs each time would make the table feel
    sluggish for a value that only changes when the job does.
    """
    where = "" if rescore else "WHERE COALESCE(tags,'') = ''"
    rows = conn.execute(
        f"SELECT rowid, title, COALESCE(description,'') FROM jobs {where}").fetchall()
    for rowid, title, desc in rows:
        conn.execute("UPDATE jobs SET tags=? WHERE rowid=?",
                     (", ".join(tags_for(title, desc)), rowid))
    conn.commit()
    if verbose and rows:
        print(f"  tagged {len(rows)} jobs")
    return len(rows)
