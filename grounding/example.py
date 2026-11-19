"""Run: python -m grounding.example"""
from grounding import check

RESUME = """
## Experience
- Built fraud-detection rules in SQL and Python that cut false positives by 12%.
- Led a team of four analysts on credit card loss forecasting for CECL.
"""

TAILORED = (
    "Built fraud-detection rules in SQL and Python that reduced false positives by 12%. "
    "Led a team of 15 engineers delivering a $40M Salesforce migration at Google."
)

report = check(TAILORED, RESUME)
print(f"checked {report.checked} claims, unsupported {report.flags}, rate {report.rate:.0%}")
for w in report.warnings():
    print(w)
