"""Generate logo candidates with a free image model.

    python tools/gen_logo_ai.py                  # Pollinations (FLUX) - FREE, no key
    python tools/gen_logo_ai.py gemini            # Nano Banana - needs Gemini billing

Nano Banana (gemini-2.5-flash-image) is the better model but it is NOT in
Gemini's free tier, and the current key 429s on even the free text model.
Pollinations serves FLUX with no key and no cost, so it's the default.

Candidates land in assets/ai/ — nothing overwrites the hand-drawn mark until
you pick one.
"""
from __future__ import annotations
import base64
import sys
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "assets" / "ai"

# The brand is fixed, so state it rather than leaving it to the model. Image
# models drift toward gradients, shadows and stray text — the prompt has to
# push back on all three or the result won't survive being shrunk to an icon.
PROMPT = (
    "Flat vector app icon, square with rounded corners. "
    "Arjuna the Mahabharata archer in side profile at full draw: front arm "
    "locked straight, bowstring pulled back to his cheek, body taut, about to "
    "release. The nocked arrow is a Shiva trishoolam trident with a long "
    "leaf-shaped central blade and two curved outer prongs, all three points "
    "facing forward. "
    "Bold minimal flat vector, thick clean strokes, solid shapes, strong "
    "silhouette, high contrast, centred, generous margin. "
    "Deep green background, cream white archer and bow, bright orange "
    "trishoolam. "
    "No text, no letters, no words, no watermark, no gradient, no shadow, "
    "no photorealism, no 3d."
)


def pollinations(prompt: str, n: int = 4, model: str = "flux"):
    """Free, keyless FLUX endpoint."""
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        url = (f"https://image.pollinations.ai/prompt/{quote(prompt)}"
               f"?width=1024&height=1024&nologo=true&model={model}&seed={i * 7}")
        r = requests.get(url, timeout=180)
        if r.status_code != 200 or len(r.content) < 2000:
            print(f"  [{i}] failed HTTP {r.status_code}")
            continue
        f = OUT / f"poll-{model}-{i}.png"
        f.write_bytes(r.content)
        print(f"  [{i}] wrote {f.name}  ({len(r.content)//1024} KB)")


def gemini(prompt: str, n: int = 3, model: str = "gemini-2.5-flash-image"):
    """Nano Banana. Needs a billing-enabled Gemini key."""
    from src.ai import _gemini_key
    key = _gemini_key()
    if not key:
        print("no gemini key")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    api = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for i in range(1, n + 1):
        r = requests.post(api, params={"key": key},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseModalities": ["IMAGE"]}},
                          timeout=120)
        if r.status_code != 200:
            err = r.json().get("error", {}).get("message", "")[:120]
            print(f"  [{i}] HTTP {r.status_code}: {err}")
            continue
        for p in (r.json()["candidates"][0]["content"]["parts"]):
            blob = p.get("inlineData") or p.get("inline_data")
            if blob and blob.get("data"):
                f = OUT / f"nano-{i}.png"
                f.write_bytes(base64.b64decode(blob["data"]))
                print(f"  [{i}] wrote {f.name}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "pollinations"
    if which.startswith("gem") or which.startswith("nano"):
        print("generating with Nano Banana (needs billing) …")
        gemini(PROMPT)
    else:
        print("generating with Pollinations / FLUX (free, no key) …")
        pollinations(PROMPT, n=4)
