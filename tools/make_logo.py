"""Generate the app logo / favicon. Run once: python tools/make_logo.py

Mark: a BOW with a TRISHOOLAM nocked on the string, for Rudrarjun —
  Arjun  -> the bow (dhanush)
  Rudra  -> the trishoolam (trident)
It also happens to say what the product does: it takes aim.

Drawn at 512 and downsampled. The binding constraint is 16x16 in a browser tab,
so: thick strokes, wide prong spacing, two-tone (white bow / orange trident) so
the two shapes separate instead of merging into one orange smear.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

GREEN = (12, 170, 65)      # brand shell   #0CAA41
GREEN_DK = (6, 110, 44)
ORANGE = (252, 128, 25)    # action        #FC8019
CREAM = (255, 252, 240)

S = 512
OUT = Path(__file__).resolve().parent.parent / "assets"


def _shell(size: int) -> Image.Image:
    """Rounded green tile with a vertical gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        gd.line([(0, y), (size, y)],
                fill=(int(GREEN[0] + (GREEN_DK[0] - GREEN[0]) * t),
                      int(GREEN[1] + (GREEN_DK[1] - GREEN[1]) * t),
                      int(GREEN[2] + (GREEN_DK[2] - GREEN[2]) * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], int(size * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def make(size: int = S, simple: bool = False) -> Image.Image:
    """simple=True drops the outer prongs — for tiny favicon sizes where three
    prongs collapse into a blob anyway."""
    img = _shell(size)
    d = ImageDraw.Draw(img)
    w = max(2, int(size * 0.058))          # stroke weight
    S_ = size

    # ── Bow (Arjun): horizontal arc bulging DOWN, string across the tips ──
    # A sideways bow put the trident off-centre and it read as a fork. Held
    # flat, the composition is symmetric and the trishoolam sits dead centre.
    bx0, by0, bx1, by1 = S_ * 0.12, S_ * 0.36, S_ * 0.88, S_ * 0.94
    d.arc([bx0, by0, bx1, by1], start=0, end=180, fill=CREAM, width=w)
    string_y = (by0 + by1) / 2
    d.line([(bx0 + w * 0.3, string_y), (bx1 - w * 0.3, string_y)],
           fill=CREAM, width=max(2, int(w * 0.42)))

    # ── Trishoolam (Rudra): nocked on the string, aimed UP ──
    cx = S_ * 0.5
    shaft_bottom = string_y + S_ * 0.06     # nocked just behind the string
    base_y = S_ * 0.34                      # where the prongs spring from
    d.line([(cx, shaft_bottom), (cx, base_y)], fill=ORANGE, width=w)

    spread = S_ * 0.155                     # gap out to the outer prongs
    d.line([(cx - spread, base_y), (cx + spread, base_y)],   # crossbar
           fill=ORANGE, width=w)

    def prong(x: float, tip_y: float):
        """Vertical prong from the crossbar up to a triangular point."""
        d.line([(x, base_y), (x, tip_y + S_ * 0.055)], fill=ORANGE, width=w)
        hw = w * 1.05
        d.polygon([(x, tip_y),
                   (x - hw, tip_y + S_ * 0.075),
                   (x + hw, tip_y + S_ * 0.075)], fill=ORANGE)

    if not simple:
        prong(cx - spread, S_ * 0.16)       # outer prongs stop short
        prong(cx + spread, S_ * 0.16)
    prong(cx, S_ * 0.07)                    # centre prong is the tallest
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    full = make(S)
    full.resize((512, 512), Image.LANCZOS).save(OUT / "logo.png")
    full.resize((180, 180), Image.LANCZOS).save(OUT / "logo-180.png")
    # Checked at 16px: all three prongs still read, so the full mark is used at
    # every size. (The `simple` single-prong variant reads as a dagger — worse.)
    full.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.png")
    full.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png")
    print("wrote logo.png, logo-180.png, favicon.png, favicon-32.png")
