"""Gmail lane — pulls jobs out of job-alert digest emails (LinkedIn, Indeed,
Jooble, ZipRecruiter, Glassdoor...) you already receive, instead of you having
to open each one by hand.

Deliberately scoped to structured job-alert digests, not free-text recruiter
emails — digests have a predictable shape (repeated "job card" blocks with a
title, company and a link into the board), so extraction is reliable. A
recruiter's personal email has no fixed format and would need free-text NLP
to parse without a high false-positive rate; out of scope here.

One-time setup (you do this, not the bot — it's your Google account):
  1. console.cloud.google.com -> new project -> enable "Gmail API"
  2. OAuth consent screen -> External -> add yourself as a test user
  3. Credentials -> Create Credentials -> OAuth client ID -> Desktop app
  4. Download the JSON, save it as config/gmail_credentials.json (gitignored)
  5. First run opens a browser to authorize read-only Gmail access; the
     resulting token is cached at config/gmail_token.json (also gitignored)
     so you only do this once.

    python -m src.scrape_gmail --probe     # counts matches, inserts nothing
    python -m src.scrape_gmail             # counts + inserts into data/jobs.db
"""
from __future__ import annotations
import base64
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from bs4 import BeautifulSoup

from . import db
from .sources import title_ok, is_core, is_us_location

_CFG = Path(__file__).resolve().parent.parent / "config" / "profile.yml"
_CREDS = Path(__file__).resolve().parent.parent / "config" / "gmail_credentials.json"
_TOKEN = Path(__file__).resolve().parent.parent / "config" / "gmail_token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Known job-alert senders and how to pull job cards out of their HTML.
# "link_re" matches the anchor href for an individual job posting (not nav/
# unsubscribe/logo links); the anchor's own text is used as the title.
SENDERS = {
    "linkedin.com":  {"query": "from:jobs-noreply@linkedin.com OR from:jobalerts-noreply@linkedin.com",
                       "link_re": re.compile(r"linkedin\.com/(comm/)?jobs/view/")},
    "indeed.com":     {"query": "from:alert@indeed.com OR from:indeedapply@indeed.com",
                        "link_re": re.compile(r"indeed\.com/(rc/clk|viewjob)")},
    "ziprecruiter.com": {"query": "from:noreply@ziprecruiter.com",
                          "link_re": re.compile(r"ziprecruiter\.com/(jobs|CIK)")},
    "glassdoor.com":  {"query": "from:noreply@glassdoor.com",
                        "link_re": re.compile(r"glassdoor\.com/(job-listing|partner/jobListing)")},
    "jooble.org":     {"query": "from:noreply@jooble.org",
                        "link_re": re.compile(r"jooble\.org/(desc|away)")},
}


def _cfg() -> dict:
    if yaml and _CFG.exists():
        try:
            return yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _gmail_cfg() -> dict:
    return _cfg().get("gmail", {}) or {}


def _service():
    """Authorized Gmail API client. Raises with a clear message if the
    one-time Google Cloud setup (see module docstring) hasn't been done."""
    if not _CREDS.exists():
        raise RuntimeError(
            f"missing {_CREDS.name} — see src/scrape_gmail.py docstring for "
            "the one-time Google Cloud Console setup")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if _TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS), SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def _extract_html(payload) -> str:
    """Gmail messages are a MIME tree; walk it for the text/html part."""
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
    for part in payload.get("parts", []) or []:
        html = _extract_html(part)
        if html:
            return html
    return ""


def _parse_digest(html: str, link_re: re.Pattern) -> list[tuple[str, str, str]]:
    """Returns [(title, company, url), ...] job cards found in one digest email.

    Company is a best-effort guess: the nearest non-empty text sibling/parent
    text near the job link, since digest layouts vary and don't tag "company"
    explicitly. Good enough as a hint — the fit-scorer and apply-link resolver
    both re-derive/verify from the real posting anyway."""
    soup = BeautifulSoup(html, "html.parser")
    seen_urls = set()
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not link_re.search(href) or href in seen_urls:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) > 140:
            continue
        seen_urls.add(href)
        company = ""
        # walk up a couple of ancestor blocks looking for a plausible company line
        node = a
        for _ in range(4):
            node = node.find_parent(["td", "div", "tr"])
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            if title in text:
                rest = text.replace(title, "", 1).strip(" -|•")
                if rest and 2 <= len(rest) <= 80:
                    company = rest.split("  ")[0].split(" | ")[0].strip()
                    break
        out.append((title, company, href))
    return out


def run(conn, *, days=3, probe=False, verbose=True) -> int:
    cfg = _gmail_cfg()
    if not cfg.get("enabled", True) and not probe:
        if verbose:
            print("  gmail: skipped (gmail.enabled: false in config/profile.yml)")
        return 0
    try:
        service = _service()
    except Exception as e:
        if verbose:
            print(f"  [warn] gmail: {e}")
        return 0

    added = 0
    for domain, meta in SENDERS.items():
        q = f"({meta['query']}) newer_than:{days}d"
        try:
            resp = service.users().messages().list(userId="me", q=q, maxResults=25).execute()
        except Exception as e:
            if verbose:
                print(f"  [warn] gmail/{domain}: {type(e).__name__}")
            continue
        msg_ids = [m["id"] for m in resp.get("messages", [])]
        seen_here = 0
        for mid in msg_ids:
            try:
                msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            except Exception:
                continue
            html = _extract_html(msg.get("payload", {}))
            if not html:
                continue
            for title, company, url in _parse_digest(html, meta["link_re"]):
                if not title_ok(title):
                    continue
                if probe:
                    seen_here += 1
                    continue
                if db.upsert_job(conn, url=url, title=title, company=company,
                                 location="", source=f"gmail:{domain}",
                                 is_core=is_core(title)):
                    added += 1
                    seen_here += 1
                if company:
                    db.touch_company(conn, company, source=f"gmail:{domain}")
        if verbose and seen_here:
            print(f"  gmail {domain}: {'found' if probe else '+new'} {seen_here}")
    if not probe:
        conn.commit()
    if verbose:
        print(f"  gmail: {'found' if probe else '+new'} {added} job(s) total")
    return added


if __name__ == "__main__":
    probe = "--probe" in sys.argv[1:]
    c = db.connect()
    db.init(c)
    run(c, probe=probe)
