"""Corpus parsing — the fact sheet everything downstream cites."""
from src import corpus


CV = """# Jane Doe

**Senior Risk Analytics Professional**
jane@example.com | (555) 555-5555 | NJ, USA

## Professional Summary

Senior analytics professional with 12 years in banking. Expert in SAS and Python.

## Experience

### Citi — Quantitative Credit Risk Manager
*12/2017 - 05/2023 | Full-Time*

- Led a team of 4 building credit-risk models (PD, LGD, EAD) for CCAR. Every submission on time.
- Piloted the SAS-to-Viya migration, cutting model runtimes ~80%.

### HSBC — Assistant Manager, Collections Analytics
*10/2014 - 12/2017 | Full-Time*

- Ran loss-mitigation analytics on a $23B sub-prime mortgage portfolio.

## Key Skills

- **Tech Stack:** SAS, Python (Pandas, NumPy), SQL, R
- **Risk:** CCAR, CECL, Fraud detection

## Education

- **Masters in Economics**, IGNOU, India - 2019

## Awards & Achievements

- 4x Bronze Awards for regulatory automation - Citi, 2023
"""


def test_kinds_and_counts():
    c = corpus.build(CV)
    kinds = {k: len(c.of_kind(k)) for k in corpus.KINDS}
    assert kinds["bullet"] == 3
    assert kinds["summary"] == 2
    assert kinds["education"] == 1
    assert kinds["award"] == 1
    assert kinds["skill"] == 7


def test_bold_and_italic_lines_are_not_bullets():
    """'**Senior Risk Analytics Professional**' and the italic date line both
    start with '*'. Neither is a claim, and both used to land in the corpus."""
    c = corpus.build(CV)
    texts = [i.text for i in c.items]
    assert "Senior Risk Analytics Professional" not in texts
    assert not [t for t in texts if t.startswith("12/2017")]


def test_short_skills_survive():
    """SAS/SQL/R are the terms a JD screens on — a length floor once ate them."""
    skills = {i.text for i in corpus.build(CV).of_kind("skill")}
    assert {"SAS", "SQL", "R"} <= skills
    assert "Python (Pandas, NumPy)" in skills   # paren-aware comma split


def test_employer_attribution():
    c = corpus.build(CV)
    assert c.employers() == {"Citi", "HSBC"}
    citi = [i for i in c.of_kind("bullet") if "CCAR" in i.text][0]
    assert citi.employer == "Citi"
    hsbc = [i for i in c.of_kind("bullet") if "23B" in i.text][0]
    assert hsbc.employer == "HSBC"
    # award employer is the TAIL of the line, not the head
    assert c.of_kind("award")[0].employer == "Citi"


def test_ids_are_stable_and_resolvable():
    c = corpus.build(CV)
    first = c.of_kind("bullet")[0]
    assert first.id == "cv-bullet-001"
    assert c.get("cv-bullet-001") is first
    assert c.get("[CV-BULLET-001]") is first   # tolerant of the model's format
    assert c.get("cv-bullet-999") is None


def test_render_for_prompt_is_addressable():
    c = corpus.build(CV)
    out = c.render_for_prompt()
    assert "[cv-bullet-001]" in out
    assert "[cv-education-001]" not in out     # not offered for tailoring
    assert len(c.render_for_prompt(max_chars=120)) <= 200


def test_empty_input_is_safe():
    assert corpus.build("").items == []
    assert corpus.build(None).items == []
