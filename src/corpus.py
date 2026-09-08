"""Your resume as addressable facts — the ground truth tailoring must cite.

Adapted from jamwithai/observable-job-agent's `corpus.py` (MIT). The idea that
makes their validator precise: don't hand the model a wall of resume text and
hope, hand it a numbered list of facts and require it to say which ones it
used. Then checking a claim is a lookup, not a search.

    [cv-bullet-004] Led a team of 4 building and running the credit-risk
                    models (PD, LGD, EAD, ECL) behind CCAR/ICAAP...

That id is what closes the recombination hole. `grounding.check()` alone can
only search all 46 facts for a best match, so when a sentence needs two facts
it cannot tell an honest merge from a false one and has to ask. With a citation
it knows the intended source, so it can grade the actual pairing — and because
each item carries the employer from its section heading, a summary that cites a
Citi bullet while claiming the work happened at HSBC is caught outright.

One addition beyond the original: `employer`. Their corpus items are typed but
employer-blind; on a resume like yours, where the same tooling recurs at four
banks, attribution is the thing most worth checking.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

KINDS = ("summary", "bullet", "skill", "education", "award")


@dataclass(frozen=True)
class Item:
    id: str
    text: str
    kind: str        # one of KINDS
    section: str     # the heading it lived under
    employer: str    # '' unless the section names one

    def label(self) -> str:
        return f"[{self.id}] {self.text}"


@dataclass
class Corpus:
    items: list[Item] = field(default_factory=list)

    def get(self, item_id: str) -> Item | None:
        key = (item_id or "").strip().strip("[]").lower()
        for it in self.items:
            if it.id == key:
                return it
        return None

    def of_kind(self, *kinds: str) -> list[Item]:
        return [i for i in self.items if i.kind in kinds]

    def employers(self) -> set[str]:
        return {i.employer for i in self.items if i.employer}

    def render_for_prompt(self, kinds: tuple[str, ...] = ("summary", "bullet", "skill"),
                          max_chars: int = 6000) -> str:
        """The fact sheet the model selects from. Skills are folded into one
        line per group — 60 individually numbered skills would crowd out the
        bullets, which are what actually carry a claim."""
        lines, used = [], 0
        for it in self.items:
            if it.kind not in kinds:
                continue
            line = it.label()
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)


# ── parsing ─────────────────────────────────────────────────────────────────
_EMP_SPLIT = re.compile(r"\s+[—–-]\s+|\s*\|\s*|\s*,\s+")


def _employer_from(heading: str) -> str:
    """'Wells Fargo — Senior Consultant, AML/Fraud' -> 'Wells Fargo'."""
    h = re.sub(r"[*_`]", "", heading or "").strip()
    if not h:
        return ""
    first = _EMP_SPLIT.split(h, maxsplit=1)[0].strip()
    return first if 1 <= len(first.split()) <= 5 else ""


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 15]


def _split_skills(line: str) -> list[str]:
    """Comma-split that respects parentheses — 'Python (Pandas, NumPy)' is ONE
    skill, not three."""
    out, buf, depth = [], "", 0
    for ch in line:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    out.append(buf.strip())
    return [s for s in out if s]


def _clean(line: str) -> str:
    line = re.sub(r"^[-*•]\s+", "", line.strip())
    line = re.sub(r"^\d+[.)]\s*", "", line)
    return re.sub(r"[*_`]", "", line).strip()


# A list marker needs the trailing space: '**Senior Analyst**' and
# '*06/2023 - Present*' are bold/italic text, not bullets, and both were
# landing in the corpus as claims before this distinction existed.
_BULLET = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)")

# Skills are the one kind that is legitimately tiny. An 8-char floor silently
# ate SAS, SQL, Hive, Unix and VBA — the exact terms a JD screens on — and even
# a 2-char floor still ate 'R' and would eat 'C'. Single letters are real here.
_MIN_LEN = {"skill": 1}


def _is_meta(text: str) -> bool:
    """Date/employment-type lines under a role heading — context, not a claim."""
    t = text.strip()
    return bool(re.match(r"^\d{1,2}/\d{4}\s*[—–-]\s*(present|\d{1,2}/\d{4})", t, re.I))


def build(md: str) -> Corpus:
    """Parse a markdown resume into addressable facts."""
    corpus = Corpus()
    counters: dict[str, int] = {}
    h2, h3 = "", ""

    def add(text: str, kind: str, section: str, employer: str) -> None:
        text = " ".join((text or "").split())
        if len(text) < _MIN_LEN.get(kind, 8) or _is_meta(text):
            return
        counters[kind] = counters.get(kind, 0) + 1
        corpus.items.append(Item(id=f"cv-{kind}-{counters[kind]:03d}", text=text,
                                 kind=kind, section=section, employer=employer))

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            h3 = line[4:].strip()
            continue
        if line.startswith("## "):
            h2, h3 = line[3:].strip(), ""
            continue
        if line.startswith("#"):
            continue

        sect = h3 or h2
        emp = _employer_from(h3)
        low = h2.lower()
        body = _clean(line)
        if not body or set(body) <= set("-*_ |"):
            continue

        if "skill" in low:
            # '**Tech Stack:** SAS, SAS Viya, Python (Pandas, NumPy), R'
            group, _, rest = body.partition(":")
            for skill in _split_skills(rest if rest else body):
                add(skill, "skill", group.strip() or sect, "")
        elif "education" in low or "certification" in low:
            add(body, "education", sect, "")
        elif "award" in low or "achievement" in low:
            # '... regulatory validations — Citi, 2023': the employer is the
            # tail here, not the head as it is in a role heading.
            tail = re.split(r"\s+[—–-]\s+", body)[-1]
            add(body, "award", sect, _employer_from(tail))
        elif "summary" in low or "profile" in low or "objective" in low:
            for s in _sentences(body):
                add(s, "summary", sect, "")
        elif _BULLET.match(line):
            add(body, "bullet", sect, emp)
    return corpus


def build_from_resume() -> Corpus:
    from .resume import load_cv_md
    return build(load_cv_md())
