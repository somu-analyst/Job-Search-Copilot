#!/usr/bin/env python
"""Workday assisted-apply — automates the tedious parts, YOU press Submit.

    python apply_assist.py <job_url> [path\\to\\resume.pdf]

What it does:
  1. Opens a real Chrome window with a PERSISTENT profile (data/browser_profile)
     — log in to each bank's Workday once; you stay logged in forever after.
  2. Navigates to the job and clicks Apply -> "Autofill with Resume" when found.
  3. Uploads your resume PDF into any file-drop on the page.
  4. Fills obvious fields it can recognize (name / email / phone) if empty.
  5. STOPS. The window stays open — review every page, answer the attestation
     questions yourself, and click Submit yourself. It never submits for you.

Field mappings vary per bank; this improves per tenant as we tune selectors.
"""
import sys
import time
from pathlib import Path

PROFILE_DIR = Path(__file__).parent / "data" / "browser_profile"

# your details for basic autofill (mirrors career-ops profile)
ME = {
    "first": "Srinivasa Rao", "last": "Somu",
    "email": "connect.ssrao@gmail.com", "phone": "7329340127",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    resume_pdf = sys.argv[2] if len(sys.argv) > 2 else ""

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False,
            viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)

        # Step 1: click the Apply button if visible
        for sel in ['a[data-automation-id="adventureButton"]',
                    'a:has-text("Apply")', 'button:has-text("Apply")']:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    print("[apply] clicked Apply")
                    time.sleep(2)
                    break
            except Exception:
                continue

        # Step 2: prefer "Autofill with Resume" when Workday offers it
        try:
            el = page.locator('a:has-text("Autofill with Resume"), '
                              'button:has-text("Autofill with Resume")').first
            if el.is_visible(timeout=3000):
                el.click()
                print("[apply] chose Autofill with Resume")
                time.sleep(2)
        except Exception:
            pass

        # Step 3: upload resume into any file input
        if resume_pdf and Path(resume_pdf).exists():
            try:
                page.locator('input[type="file"]').first.set_input_files(
                    resume_pdf, timeout=5000)
                print(f"[apply] uploaded {resume_pdf}")
            except Exception:
                print("[apply] no file input yet — upload manually when asked")

        # Step 4: gentle autofill of empty basic fields
        fills = {
            'input[data-automation-id*="legalNameSection_firstName"]': ME["first"],
            'input[data-automation-id*="legalNameSection_lastName"]': ME["last"],
            'input[data-automation-id*="email"]': ME["email"],
            'input[data-automation-id*="phone-number"]': ME["phone"],
        }
        for sel, val in fills.items():
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1500) and not el.input_value():
                    el.fill(val)
                    print(f"[apply] filled {sel.split('*=')[-1]}")
            except Exception:
                continue

        print("\n>>> Review the application in the browser window.")
        print(">>> First time at this bank: create the account / sign in — it stays saved.")
        print(">>> Answer attestation/visa questions yourself. YOU click Submit.")
        print(">>> Close the browser window when finished.")
        try:
            page.wait_for_event("close", timeout=0)   # wait until user closes
        except Exception:
            pass
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
