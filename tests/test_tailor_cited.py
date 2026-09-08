"""The cited tailoring path: prompt contract, parsing, and the fallback chain.

No network and no LLM — `_chat` and `fetch_jd` are stubbed, so these assert the
wiring, which is the part that silently rots."""
import json

import pytest

from src import ai, corpus, grounding, variants

from .test_corpus import CV


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(ai, "fetch_jd", lambda url: "Fraud analytics manager, CCAR, SAS.")
    monkeypatch.setattr(ai, "load_cv_md", lambda: CV)


def reply(monkeypatch, payload):
    seen = {}

    def chat(prompt, max_tokens=1400, passes=2):
        seen["prompt"] = prompt
        return payload

    monkeypatch.setattr(ai, "_chat", chat)
    return seen


def test_prompt_offers_numbered_facts_not_raw_resume(monkeypatch):
    seen = reply(monkeypatch, json.dumps(
        {"sentences": [{"text": "Led CCAR credit-risk models at Citi.",
                        "refs": ["cv-bullet-001"]}]}))
    ai.tailor_summary_cited("u", "t", "c", cv_corpus=corpus.build(CV))
    assert "[cv-bullet-001]" in seen["prompt"]
    assert '"refs"' in seen["prompt"]


def test_parses_sentences_and_refs(monkeypatch):
    reply(monkeypatch, json.dumps({"sentences": [
        {"text": "Led CCAR credit-risk models.", "refs": ["cv-bullet-001"]},
        {"text": "Piloted the SAS-to-Viya migration.", "refs": ["[CV-BULLET-002]"]},
    ]}))
    summary, cited = ai.tailor_summary_cited("u", "t", "c", cv_corpus=corpus.build(CV))
    assert summary.startswith("Led CCAR")
    assert "Piloted" in summary
    assert [s["refs"] for s in cited] == [["cv-bullet-001"], ["cv-bullet-002"]]


def test_junk_reply_returns_empty_so_caller_can_fall_back(monkeypatch):
    for junk in ("", "I'm sorry, I can't help.", '{"sentences": []}', "{}"):
        reply(monkeypatch, junk)
        assert ai.tailor_summary_cited("u", "t", "c",
                                       cv_corpus=corpus.build(CV)) == ("", [])


def test_empty_corpus_is_safe(monkeypatch):
    reply(monkeypatch, json.dumps({"sentences": [{"text": "x", "refs": []}]}))
    assert ai.tailor_summary_cited("u", "t", "c",
                                   cv_corpus=corpus.build("")) == ("", [])


def test_end_to_end_cited_summary_grades_clean(monkeypatch):
    """A well-behaved model reply should produce zero flags — if this drifts,
    the guard has started crying wolf on honest output."""
    reply(monkeypatch, json.dumps({"sentences": [
        {"text": "Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR.",
         "refs": ["cv-bullet-001"]}]}))
    _, cited = ai.tailor_summary_cited("u", "t", "c", cv_corpus=corpus.build(CV))
    rep = grounding.check_cited(cited, corpus.build(CV))
    assert rep.rate == 0.0
    assert rep.warnings() == []


# ── variants fallback chain ────────────────────────────────────────────────
@pytest.fixture
def stub_variants(monkeypatch):
    """Every outbound call stubbed, including all three tailoring lanes.

    They default to 'produced nothing' so a test that forgets to stub the lane
    it exercises fails loudly instead of quietly making real LLM calls — which
    is exactly what happened here first time round (a 65-second test run)."""
    monkeypatch.setattr(variants.rz, "load_cv_md", lambda: CV)
    monkeypatch.setattr(variants, "score_resume", lambda *a, **k: {"overall": 7.0})
    monkeypatch.setattr(variants.ai, "authenticity_check", lambda *a, **k: [])
    monkeypatch.setattr(variants.ai, "tailor_summary_cited", lambda *a, **k: ("", []))
    monkeypatch.setattr(variants.ai, "tailor_summary", lambda *a, **k: "")
    monkeypatch.setattr(variants.ai, "tailor_summary_offline", lambda *a, **k: "")


def test_build_uses_the_cited_path_when_available(monkeypatch, stub_variants):
    monkeypatch.setattr(variants.ai, "tailor_summary_cited", lambda *a, **k: (
        "Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR.",
        [{"text": "Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR.",
          "refs": ["cv-bullet-001"]}]))
    out = variants.build("u", "t", "c", presets=[("Balanced", 5, "b")])
    v = out[1]
    assert v["mode"] == "AI+cited"
    assert v["citations"][0]["refs"] == ["cv-bullet-001"]
    assert v["fabrication_rate"] == 0.0


def test_build_falls_back_to_uncited_then_offline(monkeypatch, stub_variants):
    monkeypatch.setattr(variants.ai, "tailor_summary",
                        lambda *a, **k: "Led CCAR credit-risk models for cards.")
    out = variants.build("u", "t", "c", presets=[("Balanced", 5, "b")])
    assert out[1]["mode"] == "AI"
    assert out[1]["citations"] == []

    monkeypatch.setattr(variants.ai, "tailor_summary", lambda *a, **k: "")
    monkeypatch.setattr(variants.ai, "tailor_summary_offline",
                        lambda *a, **k: "Led CCAR credit-risk models for cards.")
    out = variants.build("u", "t", "c", presets=[("Balanced", 5, "b")])
    assert out[1]["mode"] == "offline"


def test_master_variant_is_always_the_baseline(stub_variants):
    """Every lane empty (models capped) still yields the untouched master —
    the comparison baseline must never disappear."""
    out = variants.build("u", "t", "c")
    assert len(out) == 1
    assert out[0]["mode"] == "base"
    assert out[0]["fabrication_rate"] == 0.0
    assert out[0]["resume_md"] == CV
