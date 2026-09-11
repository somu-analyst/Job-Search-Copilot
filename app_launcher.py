# -*- coding: utf-8 -*-
"""Launch Job Search Copilot as a desktop app window - no browser tab required.

Same idea as the NYSE project's dashboard_app.py, best rung first (every rung
except the first needs nothing installed):
    1. pywebview - a real native window (WebView2, ships with Windows). Needs
                   `pip install pywebview` (optional; falls through if absent).
    2. Chrome    - `chrome.exe --app=URL`, a chrome-less app window. Tried first
                   (not Edge): if Chrome is already your running browser, this
                   reuses its existing process instead of cold-starting a second
                   browser engine just for this window.
    3. Edge      - same flag, if Chrome isn't installed.
    4. default browser - last resort, an ordinary tab.

Starts the Streamlit server first if the port is dead - opening a window at a
dead port just shows a connection error.

Usage:
    python app_launcher.py             # start server if needed, open the window
    python app_launcher.py --no-serve  # window only, assume the server is up
"""
import os
import socket
import subprocess
import sys
import time

PORT = 8601  # pinned, matching run_app.bat - keeps this app from ever port-bumping
             # into the NYSE bot's dashboard (which reacts to 8502 being busy)
URL = f"http://localhost:{PORT}"
ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "app.py")


def _port_open(port=PORT, host="127.0.0.1", timeout=0.6):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def ensure_server(wait=60):
    """Start Streamlit headless if the port is dead. Returns True once it answers."""
    if _port_open():
        print(f"[app] server already up on {PORT}")
        return True
    if not os.path.exists(APP):
        print(f"[app] cannot find {APP}")
        return False
    print("[app] starting Streamlit...")
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.port", str(PORT), "--server.address", "127.0.0.1",
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT,
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                       | getattr(subprocess, "DETACHED_PROCESS", 0)),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    for _ in range(wait * 2):
        if _port_open():
            print(f"[app] server ready on {PORT}")
            return True
        time.sleep(0.5)
    print("[app] server did not come up in time")
    return False


def _find(*candidates):
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def open_window():
    """Open the app window via the best rung available."""
    try:
        import webview  # noqa: F401  (optional dependency)
        print("[app] opening native window (pywebview)")
        webview.create_window("Job Search Copilot", URL,
                              width=1500, height=950, resizable=True)
        webview.start()
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[app] pywebview failed ({e}), falling back")

    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    lad = os.environ.get("LOCALAPPDATA", "")
    edge = _find(os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
                 os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"))
    chrome = _find(os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                   os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                   os.path.join(lad, "Google", "Chrome", "Application", "chrome.exe"))
    for exe, name in ((chrome, "Chrome"), (edge, "Edge")):
        if exe:
            print(f"[app] opening {name} app window")
            subprocess.Popen([exe, f"--app={URL}", "--window-size=1500,950"],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return True

    import webbrowser
    print("[app] falling back to the default browser (ordinary tab)")
    return webbrowser.open(URL, new=2)


if __name__ == "__main__":
    if "--no-serve" not in sys.argv:
        if not ensure_server():
            sys.exit(1)
    open_window()
