"""Aggregator APIs — parsing and quota discipline, with no network calls."""
import sqlite3
import types

import pytest

from src import db, scrape_apis as sa


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init(c)
    yield c
    c.close()


# A JSearch job in the newer response shape, with a reposter link listed
# first and the employer's own link flagged is_direct.
NEWER = {
    "job_title": "Fraud Analytics Manager",
    "employer_name": "Citi",
    "job_location": "New York, NY",
    "job_apply_link": "https://lensa.com/repost/1",
    "apply_options": [
        {"publisher": "Lensa", "apply_link": "https://lensa.com/repost/1", "is_direct": False},
        {"publisher": "Citi", "apply_link": "https://jobs.citi.com/job/999", "is_direct": True},
    ],
    "job_posted_at_datetime_utc": "2026-08-08T12:00:00.000Z",
    "job_min_salary": 120000, "job_max_salary": 160000, "job_salary_period": "YEAR",
    "job_description": "Fraud model remediation.",
}
# The older shape: no job_location, epoch timestamp, top-level direct flag.
OLDER = {
    "job_title": "AML Compliance Analyst",
    "employer_name": "PNC",
    "job_city": "Pittsburgh", "job_state": "PA",
    "job_apply_link": "https://pnc.wd1.myworkdayjobs.com/job/123",
    "job_apply_is_direct": True,
    "job_posted_at_timestamp": 1786000000,
    "job_description": "KYC transaction monitoring.",
}
NEGATIVE = {"job_title": "Software Engineer", "employer_name": "Nope",
            "job_is_remote": True, "job_apply_link": "https://x.com/1"}
NO_LINK = {"job_title": "Credit Risk Analyst", "employer_name": "Ghost"}


class Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def fake_http(monkeypatch, payload, calls):
    def get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        return Resp(payload)

    def post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json or {}, "headers": headers or {}})
        return Resp({"jobs": []})

    monkeypatch.setattr(sa, "requests", types.SimpleNamespace(get=get, post=post))


# ── parsers ─────────────────────────────────────────────────────────────────
def test_prefers_the_direct_employer_link_over_the_reposter():
    assert sa._js_link(NEWER) == ("https://jobs.citi.com/job/999", True)


def test_falls_back_to_apply_link_with_top_level_direct_flag():
    assert sa._js_link(OLDER) == ("https://pnc.wd1.myworkdayjobs.com/job/123", True)


def test_location_from_either_shape():
    assert sa._js_location(NEWER) == "New York, NY"
    assert sa._js_location(OLDER) == "Pittsburgh, PA"
    assert sa._js_location(NEGATIVE) == "Remote"


def test_posted_date_from_either_shape():
    assert sa._js_posted(NEWER) == "2026-08-08"
    assert sa._js_posted(OLDER) == "2026-08-06"
    assert sa._js_posted(NO_LINK) == ""


def test_rows_from_either_endpoint_shape():
    assert sa._js_rows({"data": [1, 2]}) == [1, 2]            # rapidapi
    assert sa._js_rows({"data": {"jobs": [1]}}) == [1]        # openwebninja
    assert sa._js_rows({}) == []


# ── the lane ────────────────────────────────────────────────────────────────
def test_jsearch_filters_and_prefills_apply_url(conn, monkeypatch):
    calls = []
    fake_http(monkeypatch, {"data": [NEWER, OLDER, NEGATIVE, NO_LINK]}, calls)
    added = sa._jsearch(conn, "KEY", budget=1, verbose=False)
    conn.commit()
    assert added == 2                     # negative-keyword title and no-link row dropped
    rows = {r["title"]: r for r in conn.execute("SELECT * FROM jobs")}
    assert set(rows) == {"Fraud Analytics Manager", "AML Compliance Analyst"}
    # a direct employer link short-circuits direct_apply.resolve_all()
    assert rows["Fraud Analytics Manager"]["apply_url"] == "https://jobs.citi.com/job/999"
    assert rows["Fraud Analytics Manager"]["salary"] == "$120,000-$160,000"
    assert rows["Fraud Analytics Manager"]["source"] == "jsearch"


def test_budget_covers_distinct_keyword_groups_as_or_queries(conn, monkeypatch):
    calls = []
    fake_http(monkeypatch, {"data": []}, calls)
    sa._jsearch(conn, "KEY", budget=3, verbose=False)
    assert len(calls) == 3
    queries = [c["params"]["query"] for c in calls]
    assert len(set(queries)) == 3, "a run must cover distinct groups, not repeat one"
    # each request is one lane's worth of terms OR'd together, not a single term
    assert all(" OR " in q for q in queries)


def test_jsearch_rotates_one_group_per_run_by_am_pm_bucket(conn, monkeypatch):
    import datetime as _dt

    # four consecutive runs: day0 AM, day0 PM, day1 AM, day1 PM
    stamps = [_dt.datetime(2026, 9, 8, 9, 0), _dt.datetime(2026, 9, 8, 15, 0),
              _dt.datetime(2026, 9, 9, 9, 0), _dt.datetime(2026, 9, 9, 15, 0)]
    seen = []
    for ts in stamps:
        class _Clock(_dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return ts
        monkeypatch.setattr(sa._dt, "datetime", _Clock)
        calls = []
        fake_http(monkeypatch, {"data": []}, calls)
        sa._jsearch(conn, "KEY", budget=1, verbose=False)
        seen.append(calls[0]["params"]["query"])
    assert seen[0] != seen[1], "AM and PM of the same day must hit different groups"
    assert len(set(seen[:3])) == 3, "three runs must cover all three groups"
    assert seen[3] == seen[0], "3 groups -> the 4th run repeats the 1st"


def test_endpoint_and_auth_header_follow_the_vendor(conn, monkeypatch):
    for via, host, header in (
        ("rapidapi", "jsearch.p.rapidapi.com", "X-RapidAPI-Key"),
        ("openwebninja", "api.openwebninja.com", "X-API-Key"),
    ):
        calls = []
        fake_http(monkeypatch, {"data": []}, calls)
        sa._jsearch(conn, "KEY", budget=1, via=via, verbose=False)
        assert host in calls[0]["url"]
        assert calls[0]["headers"][header] == "KEY"


def test_http_error_is_survivable(conn, monkeypatch):
    class Boom(Resp):
        status_code = 429

    monkeypatch.setattr(sa, "requests", types.SimpleNamespace(
        get=lambda *a, **k: Boom({}), post=None))
    assert sa._jsearch(conn, "KEY", budget=1, verbose=False) == 0


# ── cascade ─────────────────────────────────────────────────────────────────
ADZUNA_HIT = {"title": "Fraud Analytics Manager", "redirect_url": "https://ex.com/1",
              "location": {"area": ["US", "New York"]},
              "company": {"display_name": "Citi"}, "created": "2026-08-09",
              "description": "fraud", "salary_min": 1, "salary_max": 2}


def _adzuna_rich(monkeypatch, calls):
    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "adzuna" in url:
            return Resp({"results": [dict(ADZUNA_HIT,
                                          redirect_url=f"https://ex.com/{len(calls)}-{i}")
                                     for i in range(6)]})
        return Resp({"data": []})

    def post(url, json=None, headers=None, timeout=None):
        calls.append(url)      # Jooble posts — record it or the cascade is untestable
        return Resp({"jobs": []})

    monkeypatch.setattr(sa, "requests", types.SimpleNamespace(get=get, post=post))


ALL_KEYS = {"adzuna_app_id": "x", "adzuna_app_key": "y",
            "jooble_key": "j", "jsearch_key": "s"}


def test_metered_sources_are_skipped_once_a_run_has_enough(conn, monkeypatch):
    calls = []
    _adzuna_rich(monkeypatch, calls)
    monkeypatch.setattr(sa, "_keys", lambda: ALL_KEYS)
    monkeypatch.setattr(sa, "_cfg", lambda: {"scrape": {"cascade_min": 5}})
    sa.run(conn, verbose=False)
    hosts = {u.split("/")[2] for u in calls}
    assert hosts == {"api.adzuna.com"}, "monthly quota spent despite a full run"


def test_cascade_min_zero_always_runs_every_source(conn, monkeypatch):
    calls = []
    _adzuna_rich(monkeypatch, calls)
    monkeypatch.setattr(sa, "_keys", lambda: ALL_KEYS)
    monkeypatch.setattr(sa, "_cfg", lambda: {"scrape": {"cascade_min": 0,
                                                        "jsearch_requests": 1}})
    sa.run(conn, verbose=False)
    hosts = {u.split("/")[2] for u in calls}
    assert "jooble.org" in hosts and "jsearch.p.rapidapi.com" in hosts


def test_no_keys_makes_no_calls(conn, monkeypatch):
    calls = []
    fake_http(monkeypatch, {"data": []}, calls)
    monkeypatch.setattr(sa, "_keys", lambda: {})
    assert sa.run(conn, verbose=False) == 0
    assert calls == []
