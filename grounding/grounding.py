"""Deterministic grounding check for generated prose — $0, no LLM call.

`ai.authenticity_check` catches claims made of NEW material: a skill, a proper
noun, a number or a hype word that isn't in your base resume. It cannot catch
**recombination** — a summary that welds a tool from one job onto an employer from
another, or moves a metric from the project it belongs to. Every token is
present in the resume, so a vocabulary check passes it, and the sentence is
still something you'd have to walk back in an interview.

Adapted from jamwithai/observable-job-agent's deterministic validator (MIT),
with one change forced by the difference in inputs: there, the model declares
which corpus item each bullet came from, so validation grades a known pairing
with difflib's character ratio. We have no declared reference, so a free search
by character ratio just grades sentence LENGTH — measured on the real resume it
scored an honest rewrite (0.36) below a pure invention (0.40). This scores
weighted token coverage instead: how much of a claim's substance one resume
fact accounts for, with numbers weighted 3x because a wrong metric is the
costliest and most checkable thing a resume can say.

Every factual sentence lands in one of three states:
  * grounded    — one resume fact covers it. Silent.
  * pairing     — no single fact covers it, but two together do. Soft note:
                  each half is real, confirm the combination is. String
                  matching cannot tell an honest merge from a false one, so
                  this asks rather than accuses.
  * unsupported — nothing covers it. This is the hard flag, and the only
                  state counted in the fabrication rate.

Only sentences that LOOK factual are graded (a digit, a year, or a multi-word
capitalised name) — voice and framing are yours to write, and false alarms
teach you to ignore the real ones.

Thresholds: PROSE_RATIO (share of a claim one resume fact must cover) and
MIN_WORDS (shorter sentences are too noisy to judge).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

PROSE_RATIO = 0.55
MIN_WORDS = 6


def _thresholds() -> tuple[float, int]:
    return PROSE_RATIO, MIN_WORDS


# ── normalisation ───────────────────────────────────────────────────────────
# "$1.2M" and "1.2 million dollars" are the same claim; "monthly" and "per
# month" are the same cadence. Canonicalise both so formatting never reads as
# a fabrication.
_UNITS = [
    (r"(\d[\d.,]*)\s*b\b", r"\1 billion"),
    (r"(\d[\d.,]*)\s*m\b", r"\1 million"),
    (r"(\d[\d.,]*)\s*k\b", r"\1 thousand"),
    (r"\bdaily\b|\bper day\b|\ba day\b", "day"),
    (r"\bweekly\b|\bper week\b|\ba week\b", "week"),
    (r"\bmonthly\b|\bper month\b|\ba month\b", "month"),
    (r"\bannually\b|\byearly\b|\bper year\b|\ba year\b|\bper annum\b", "year"),
    (r"\bpercent\b|\bpct\b", "%"),
]


def normalize(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("–", "-").replace("—", "-").replace("’", "'")
    for pat, rep in _UNITS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"[^a-z0-9%$+#./ -]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ── reference facts (the ground truth: your base resume) ────────────────────
def references(base_md: str) -> list[str]:
    """Every atomic fact in the resume: bullets, and sentences of prose blocks.

    One reference = one claim you can defend. Splitting matters — comparing a
    generated sentence against a whole 400-word section would let anything
    through on shared vocabulary alone."""
    refs: list[str] = []
    for raw in (base_md or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= set("-*_ "):
            continue
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if line.startswith("|"):        # markdown table row -> cells are facts
            refs.extend(c.strip() for c in line.strip("|").split("|"))
            continue
        refs.extend(sentences(line))
    return [r for r in (normalize(x) for x in refs) if len(r.split()) >= 3]


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_CAPS = re.compile(r"\b[A-Z][\w&.+-]*(?:\s+[A-Z][\w&.+-]*)+")


def is_factual(sentence: str) -> bool:
    """Does this sentence assert something checkable? Style isn't a claim."""
    s = sentence or ""
    return bool(re.search(r"\d", s) or _YEAR.search(s) or _CAPS.search(s))


# ── the check ───────────────────────────────────────────────────────────────
@dataclass
class Flag:
    where: str          # 'summary' / 'letter' — which generated text it came from
    text: str           # the offending sentence, verbatim
    ratio: float        # best single-fact coverage it achieved
    level: str          # 'unsupported' (hard) | 'pairing' (soft)
    reason: str


@dataclass
class Report:
    checked: int = 0
    flagged: list[Flag] = field(default_factory=list)
    ratio_threshold: float = PROSE_RATIO

    @property
    def unsupported(self) -> list[Flag]:
        return [f for f in self.flagged if f.level == "unsupported"]

    @property
    def pairing(self) -> list[Flag]:
        return [f for f in self.flagged if f.level == "pairing"]

    @property
    def flags(self) -> int:
        return len(self.unsupported)

    @property
    def rate(self) -> float:
        """Fabrication rate: 0.0 = every claim grounded, 1.0 = nothing grounded.
        Counts only unsupported claims — a number to track across variants
        instead of eyeballing prose. Pairing notes are advisory, not failures."""
        return (self.flags / self.checked) if self.checked else 0.0

    def warnings(self) -> list[str]:
        """Merge-able into the existing authenticity warning list."""
        out = []
        if self.unsupported:
            worst = sorted(self.unsupported, key=lambda f: f.ratio)[:3]
            out.append(
                f"{len(self.unsupported)} of {self.checked} factual claims aren't "
                f"supported by anything in your resume — verify or cut:"
                + "".join(f'\n  • "{_clip(f.text)}"' for f in worst))
        if self.pairing:
            first = self.pairing[:3]
            out.append(
                f"{len(self.pairing)} claim(s) combine facts from two different "
                f"roles. Each half is real; check the combination is true as written:"
                + "".join(f'\n  • "{_clip(f.text)}"' for f in first))
        return out


def _clip(s: str, n: int = 110) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "across",
    "while", "using", "used", "than", "then", "their", "them", "was", "were",
    "have", "has", "had", "been", "being", "are", "its", "his", "her", "our",
    "you", "your", "all", "any", "each", "per", "via", "including", "such",
    "also", "more", "most", "other", "both", "who", "which", "what", "when",
    "where", "how", "not", "but", "out", "off", "own", "same", "new", "end",
    "led", "run", "ran", "built", "build", "building", "driving", "drove",
    "delivered", "delivering", "worked", "working", "managed", "managing",
    "owned", "owning", "handled", "handling", "supported", "supporting",
}


def _content(norm: str) -> list[str]:
    """Content tokens only — the checkable substance of a claim."""
    return [t for t in norm.split()
            if (len(t) >= 3 and t not in _STOP) or any(c.isdigit() for c in t)]


def _weight(tok: str) -> float:
    # A wrong metric is the costliest thing a resume can say, and the easiest
    # for an interviewer to test. Weight numbers far above ordinary words.
    return 3.0 if any(c.isdigit() for c in tok) else 1.0


def _coverage(sent_toks: list[str], ref: str) -> float:
    """Share of a sentence's weighted substance that ONE resume fact supports.

    Token overlap, not difflib's character ratio: a 25-word rewrite of a
    12-word bullet is honest, but scores terribly on character similarity
    purely because it is longer. Substance is what we need to grade."""
    if not sent_toks:
        return 0.0
    rt = set(ref.split())
    hit = sum(_weight(t) for t in sent_toks
              if t in rt or any(t in r or r in t for r in rt if len(r) >= 4))
    return hit / sum(_weight(t) for t in sent_toks)


def _best(sent_toks: list[str], refs: list[str]) -> tuple[float, str]:
    best, hit = 0.0, ""
    for r in refs:
        got = _coverage(sent_toks, r)
        if got > best:
            best, hit = got, r
    return best, hit


def check(generated: str, base_md: str, *, where: str = "summary",
          refs: list[str] | None = None) -> Report:
    """Ground every factual sentence of `generated` against `base_md`."""
    ratio_min, min_words = _thresholds()
    rep = Report(ratio_threshold=ratio_min)
    pool = refs if refs is not None else references(base_md)
    if not pool:
        return rep
    # Verbatim text is grounded by definition. The fact pool holds body lines only, so a
    # heading copied straight from the source ('### Acme Bank - Senior Analyst')
    # used to be flagged as unsupported (found 2026-10-25, master-resume upload).
    base_norm = normalize(base_md or "")

    for sent in sentences(generated or ""):
        if not is_factual(sent):
            continue
        norm = normalize(sent)
        toks = _content(norm)
        if len(norm.split()) < min_words or not toks:
            continue
        rep.checked += 1
        if norm in base_norm:
            continue
        best, hit = _best(toks, pool)
        if best >= ratio_min:
            continue    # one real fact carries the whole claim — clean

        # No single fact covers it. Either the sentence honestly merges two
        # facts, or it welds two roles together into something untrue — and no
        # amount of string matching can tell those apart, so say which it is
        # and let the human judge. Merging the top refs pairwise tests it.
        top = sorted(pool, key=lambda r: _coverage(toks, r), reverse=True)[:3]
        composites = [f"{a} {b}" for a in top for b in top if a is not b]
        comp_best, _ = _best(toks, composites) if composites else (0.0, "")
        if comp_best >= ratio_min:
            rep.flagged.append(Flag(
                where=where, text=sent.strip(), ratio=round(best, 3),
                level="pairing",
                reason=(f"no single resume line covers this ({best:.0%}); two "
                        f"together do ({comp_best:.0%}) — confirm the pairing")))
            continue
        rep.flagged.append(Flag(
            where=where, text=sent.strip(), ratio=round(best, 3),
            level="unsupported",
            reason=(f"best resume line covers {best:.0%} of it "
                    f"(needs {ratio_min:.0%}): \"{_clip(hit, 80)}\"" if hit
                    else "no resume fact resembles this claim")))
    return rep
