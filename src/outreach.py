"""Recruiter outreach — from published contacts only, sent by you, one at a time.

DELIBERATE NON-FEATURE: we do not scrape personal emails from LinkedIn or
people-search sites. That breaks LinkedIn's ToS (the same account-ban risk that
ruled out auto-apply), exposes you under CAN-SPAM/GDPR, and — the practical
point — cold blasts get marked as spam and can taint you at that employer.

What we do instead:
  1. Pull contacts the EMPLOYER PUBLISHED in the JD text we already store.
  2. Draft a short, specific email you review and send from your own client.
  3. Deep-link a LinkedIn people search so you connect like a human.

Nothing here sends mail on your behalf. `mailto:` opens YOUR client, pre-filled;
you read it and press send.
"""
from __future__ import annotations
import re
from urllib.parse import quote

# Emails that are never a person worth writing to
_JUNK = ("noreply", "no-reply", "donotreply", "privacy", "abuse", "webmaster",
         "unsubscribe", "postmaster", "example.com", "sentry", "wixpress")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# "Contact Jane Doe", "Recruiter: John Smith", "reach out to Priya Nair"
# Case-insensitive ONLY on the trigger words — the name itself must stay
# properly capitalised, or re.I lets [A-Z] match lowercase and we "find"
# names like "given here at" in ordinary prose.
_NAME_RE = re.compile(
    r"(?i:recruiter|contact|hiring manager|reach out to|questions to)"
    r"[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})")


def contacts_from_jd(jd: str) -> dict:
    """Emails/names the employer chose to publish in the posting. '' if none."""
    t = jd or ""
    emails = [e for e in dict.fromkeys(_EMAIL_RE.findall(t))
              if not any(j in e.lower() for j in _JUNK)]
    names = list(dict.fromkeys(_NAME_RE.findall(t)))
    return {"emails": emails, "names": names}


def linkedin_search(company: str, role_hint: str = "recruiter") -> str:
    """Deep link to a LinkedIn PEOPLE search — you connect/InMail manually.
    No scraping, no automation, no ban risk."""
    q = quote(f"{role_hint} {company}".strip())
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


def domain_for(company: str, careers_url: str = "") -> str:
    """Best guess at the employer's mail domain (from their careers URL if we
    have one — that's the most reliable free signal we hold)."""
    from urllib.parse import urlparse
    host = (urlparse(careers_url or "").netloc or "").lower()
    host = re.sub(r"^(www|jobs|careers|apply|recruiting)\.", "", host)
    if host and "myworkdayjobs" not in host and "." in host:
        return host
    slug = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    return f"{slug}.com" if slug else ""


def email_patterns(first: str, last: str, domain: str) -> list[str]:
    """The address shapes corporate mail almost always uses. These are GUESSES —
    surfaced for you to verify, never auto-sent to. (This is exactly what the
    'email permutation' tools do; the difference is we say so.)"""
    f, l = (first or "").strip().lower(), (last or "").strip().lower()
    if not (f and l and domain):
        return []
    return [f"{f}.{l}@{domain}", f"{f[0]}{l}@{domain}", f"{f}{l}@{domain}",
            f"{f}_{l}@{domain}", f"{f}@{domain}", f"{l}.{f}@{domain}"]


def hunter_lookup(domain: str, api_key: str) -> dict:
    """Hunter.io — the LEGAL version of contact discovery (free tier ~25/mo,
    GDPR opt-out process, which scraped lists don't have). Returns
    {'pattern': 'first.last', 'emails': [{'value','first_name','last_name',
    'position'}, ...]}. Empty dict when no key / lookup fails."""
    if not (domain and api_key):
        return {}
    try:
        import requests
        r = requests.get("https://api.hunter.io/v2/domain-search",
                         params={"domain": domain, "api_key": api_key, "limit": 10,
                                 "department": "hr"},
                         timeout=20)
        if r.status_code != 200:
            return {}
        d = (r.json() or {}).get("data", {}) or {}
        return {"pattern": d.get("pattern", ""),
                "emails": [{"value": e.get("value", ""),
                            "first_name": e.get("first_name", ""),
                            "last_name": e.get("last_name", ""),
                            "position": e.get("position", "")}
                           for e in (d.get("emails") or [])]}
    except Exception:
        return {}


def draft_email(*, name: str, title: str, company: str, job_title: str,
                highlights: list[str] | None = None,
                job_url: str = "") -> tuple[str, str]:
    """(subject, body) — short, specific, and honest. No hype, no mass-merge feel.

    Recruiters bin generic notes. This leads with the role, gives two concrete
    proof points from YOUR resume, and asks one small question."""
    hl = [h for h in (highlights or []) if h][:2]
    proof = ""
    if hl:
        proof = ("\n".join(f"  • {h}" for h in hl)) + "\n"

    subject = f"{job_title} — {name}" if name else f"Application: {job_title}"
    greet = f"Hi {name.split()[0]}," if name else "Hello,"

    body = f"""{greet}

I applied for the {job_title} role at {company} and wanted to put a short note
alongside the application.

I'm a {title} with 13+ years in financial services — fraud/AML analytics, credit
risk, and regulatory reporting (CCAR/CECL), built mostly in SAS/SAS Viya, SQL and
Python. Two things from my background that map directly to this role:
{proof}
I'd welcome a short conversation if it's useful. Happy to send anything else that
would help.

Thanks for your time,
"""
    if job_url:
        body += f"\nPosting: {job_url}\n"
    return subject, body


def mailto(to: str, subject: str, body: str) -> str:
    """A mailto: link — opens the user's own mail client, pre-filled, unsent."""
    return (f"mailto:{quote(to)}"
            f"?subject={quote(subject)}&body={quote(body)}")
