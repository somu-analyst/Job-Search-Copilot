from grounding import check

RESUME = "- Built fraud-detection rules in SQL and Python that cut false positives by 12%."


def test_honest_rewrite_passes():
    r = check("Built fraud-detection rules in SQL and Python that reduced false positives by 12%.", RESUME)
    assert r.checked == 1 and r.flags == 0


def test_invented_claim_is_flagged():
    r = check("Led a team of 15 engineers delivering a $40M Salesforce migration at Google.", RESUME)
    assert r.flags == 1 and r.unsupported[0].level == "unsupported"
