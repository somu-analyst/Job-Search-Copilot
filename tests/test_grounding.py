"""Grounding — both modes. The point of these tests is discrimination:
an honest rewrite and an invention must not land in the same bucket."""
from src import corpus, grounding

from .test_corpus import CV


def rep_for(text):
    return grounding.check(text, CV)


def test_style_sentences_are_not_graded():
    """Voice is the candidate's to write. Only checkable claims are claims."""
    r = rep_for("A pragmatic leader who turns messy data into decisions people trust.")
    assert r.checked == 0
    assert r.rate == 0.0
    assert r.warnings() == []


def test_verbatim_fact_is_clean():
    r = rep_for("Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR.")
    assert r.flags == 0
    assert r.rate == 0.0


def test_invention_is_unsupported():
    r = rep_for("Architected a Kubernetes platform processing 4 billion transactions "
                "a day for the Federal Reserve in 2019.")
    assert r.flags == 1
    assert r.rate == 1.0
    assert r.unsupported[0].level == "unsupported"


def test_merge_of_two_facts_asks_rather_than_accuses():
    """No string match can tell an honest merge from a false one, so this is a
    soft note and must NOT count toward the fabrication rate."""
    r = rep_for("Led a team of 4 on CCAR credit-risk models while piloting the "
                "SAS-to-Viya migration that cut runtimes about 80%.")
    assert r.pairing, "expected a pairing note"
    assert r.flags == 0
    assert r.rate == 0.0
    assert len(r.warnings()) == 1


def test_numbers_weigh_more_than_words():
    assert grounding._weight("80%") > grounding._weight("migration")


def test_unit_normalisation():
    n = grounding.normalize
    assert n("$1.2M annually") == n("$1.2 million per year")
    assert n("300+ alerts monthly") == n("300+ alerts per month")


def test_rate_is_zero_when_nothing_checked():
    assert grounding.Report().rate == 0.0


# ── cited mode ──────────────────────────────────────────────────────────────
def cv_corpus():
    return corpus.build(CV)


def cited(text, refs):
    return grounding.check_cited([{"text": text, "refs": refs}], cv_corpus())


def test_cited_fact_that_supports_the_claim_is_clean():
    r = cited("Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR.",
              ["cv-bullet-001"])
    assert r.flags == 0
    assert r.rate == 0.0


def test_hallucinated_citation_is_caught():
    """A cited id that doesn't exist is a strong tell the claim came first and
    the citation was decoration."""
    r = cited("Led a 40-person quantitative research division.", ["cv-bullet-404"])
    assert r.flags == 1
    assert "don't exist" in r.unsupported[0].reason


def test_attribution_drift_is_caught():
    """THE case search mode cannot see: every word is real, the arithmetic is
    real, but the work is attributed to the wrong employer."""
    r = cited("At HSBC, led a team of 4 building credit-risk models for CCAR.",
              ["cv-bullet-001"])          # cv-bullet-001 is a Citi bullet
    assert r.flags == 1
    assert "HSBC" in r.unsupported[0].reason
    assert "Citi" in r.unsupported[0].reason


def test_correct_attribution_passes():
    r = cited("At Citi, led a team of 4 building credit-risk models for CCAR.",
              ["cv-bullet-001"])
    assert r.flags == 0


def test_citation_that_does_not_cover_the_claim():
    r = cited("Ran a $4 billion algorithmic trading book across three continents.",
              ["cv-bullet-001"])
    assert r.flags == 1
    assert "cover" in r.unsupported[0].reason


def test_no_refs_at_all_is_unsupported():
    r = cited("Delivered $12M in savings during 2021 at Barclays.", [])
    assert r.flags == 1


def test_cited_mode_ignores_style_sentences():
    r = cited("A pragmatic leader who enjoys hard problems.", [])
    assert r.checked == 0
    assert r.rate == 0.0
