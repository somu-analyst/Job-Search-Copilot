"""Generate the app logo / favicon. Run: python tools/make_logo.py [option]

Mark: a bow and a trishoolam, for Rudrarjun.
  Arjun -> the bow (dhanush)      Rudra -> the trishoolam (trident)

The trishoolam is drawn in its proper form, not as three plain arrows:
  - a leaf-shaped central blade (lance head), longest of the three
  - two S-curved outer prongs that sweep out and then back in to sharp points
  - a collar (bandha) where the prongs meet the shaft
It's built pointing UP on its own layer, then rotated — so the same true shape
is reused whether it's flying right out of a bow or standing upright.

Options (pass as argv[1], default 1):
  1  archer   — the boy at full draw, loosing the trishoolam
  2  upright  — trishoolam standing, bow as a crescent behind it
  3  crossed  — bow and trishoolam crossed, like a crest
  4  mark     — bow + trishoolam only, no figure (used for the favicon)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

GREEN = (12, 170, 65)      # brand shell  #0CAA41
GREEN_DK = (6, 110, 44)
ORANGE = (252, 128, 25)    # action       #FC8019
CREAM = (255, 252, 240)

S = 512
OUT = Path(__file__).resolve().parent.parent / "assets"


# ── helpers ─────────────────────────────────────────────────────────────────
def _bez(p0, p1, p2, n=26):
    """Quadratic bezier -> point list (PIL has no curve primitive)."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def _shell(size: int) -> Image.Image:
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


def trishool_layer(box: int, shaft: float = 0.42, color=ORANGE) -> Image.Image:
    """Trishoolam pointing UP on a transparent square. `shaft` = fraction of the
    box given to the shaft below the collar."""
    L = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    B = float(box)
    w = B * 0.062                       # stroke weight
    cx = B * 0.5
    base_y = B * (1 - shaft)            # collar sits here
    head_h = base_y - B * 0.06          # room for the blades above the collar

    # shaft (danda)
    d.line([(cx, B * 0.98), (cx, base_y)], fill=color, width=int(w))
    # collar / bandha
    d.rounded_rectangle([cx - B * 0.115, base_y - w * 0.55,
                         cx + B * 0.115, base_y + w * 0.55],
                        radius=w * 0.4, fill=color)

    # ── central blade: a leaf / lance head, the longest prong
    tip = B * 0.045
    bw = B * 0.058                      # half-width at the belly of the leaf
    belly = base_y - head_h * 0.42
    d.polygon([(cx, tip),
               (cx + bw, belly),
               (cx + bw * 0.42, base_y - w * 0.3),
               (cx - bw * 0.42, base_y - w * 0.3),
               (cx - bw, belly)], fill=color)

    # ── outer prongs: sweep OUT from the collar, then back IN to a point
    for s in (-1, 1):
        x0 = cx + s * B * 0.10          # leaves the collar
        out_x = cx + s * B * 0.245      # widest point
        tip_x = cx + s * B * 0.175      # curls back in
        tip_y = base_y - head_h * 0.80
        path = _bez((x0, base_y),
                    (out_x, base_y - head_h * 0.42),   # control: bulge outward
                    (tip_x, tip_y + B * 0.05))
        d.line(path, fill=color, width=int(w * 0.85), joint="curve")
        # sharp point on the end, aimed up and slightly inward
        d.polygon([(tip_x - s * B * 0.012, tip_y),
                   (tip_x + s * B * 0.055, tip_y + B * 0.075),
                   (tip_x - s * B * 0.052, tip_y + B * 0.062)], fill=color)
    return L


def _paste_trishool(img, box, cx, cy, rot=0, shaft=0.42):
    """Place a trishoolam, rotated (deg, CCW). rot=-90 -> points right."""
    t = trishool_layer(box, shaft=shaft)
    if rot:
        t = t.rotate(rot, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))


def _bow(d, S_, box, aim_y, w):
    """Bow with limbs curving toward the target (right); returns tips + grip."""
    bx0, by0, bx1, by1 = box
    d.arc([bx0, by0, bx1, by1], start=270, end=90, fill=CREAM, width=int(w))
    cx_bow = (bx0 + bx1) / 2
    return (cx_bow, by0), (cx_bow, by1), (bx1 - w * 0.4, aim_y)


# ── the four options ────────────────────────────────────────────────────────
def opt_archer(size=S):
    """The boy at FULL DRAW: front arm locked out, draw hand back at the cheek,
    string bent into a deep V. A straight string = an unloaded bow, no story."""
    img = _shell(size)
    d = ImageDraw.Draw(img)
    S_ = float(size)
    w, limb = S_ * 0.038, S_ * 0.040
    aim_y = S_ * 0.50

    tip_t, tip_b, grip = _bow(
        d, S_, (S_ * 0.42, S_ * 0.15, S_ * 0.68, S_ * 0.85), aim_y, w)

    draw_hand = (S_ * 0.305, aim_y)
    sw = max(2, int(w * 0.42))
    d.line([tip_t, draw_hand], fill=CREAM, width=sw)     # string, drawn back
    d.line([tip_b, draw_hand], fill=CREAM, width=sw)

    _paste_trishool(img, int(S_ * 0.62), S_ * 0.63, aim_y, rot=-90, shaft=0.50)

    d = ImageDraw.Draw(img)                              # redraw over the layer
    hx, hy, hr = S_ * 0.205, S_ * 0.295, S_ * 0.070
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=CREAM)
    sh, hip = (S_ * 0.215, S_ * 0.405), (S_ * 0.205, S_ * 0.625)
    d.line([sh, hip], fill=CREAM, width=int(limb * 1.8))
    d.line([sh, grip], fill=CREAM, width=int(limb))      # locked-out bow arm
    elbow = (S_ * 0.105, S_ * 0.455)                     # elbow behind the body
    d.line([sh, elbow], fill=CREAM, width=int(limb))
    d.line([elbow, draw_hand], fill=CREAM, width=int(limb))
    d.line([hip, (S_ * 0.315, S_ * 0.855)], fill=CREAM, width=int(limb))
    d.line([hip, (S_ * 0.095, S_ * 0.855)], fill=CREAM, width=int(limb))
    return img


def opt_upright(size=S):
    """Trishoolam standing; the bow behind it as a crescent."""
    img = _shell(size)
    d = ImageDraw.Draw(img)
    S_ = float(size)
    w = S_ * 0.055
    # bow laid horizontally behind, limbs curving up toward the trishool's point
    d.arc([S_ * 0.13, S_ * 0.34, S_ * 0.87, S_ * 1.06], start=180, end=360,
          fill=CREAM, width=int(w))
    d.line([(S_ * 0.145, S_ * 0.70), (S_ * 0.855, S_ * 0.70)],
           fill=CREAM, width=int(w * 0.45))              # string
    _paste_trishool(img, int(S_ * 0.78), S_ * 0.5, S_ * 0.47, shaft=0.30)
    return img


def opt_crossed(size=S):
    """Bow and trishoolam crossed, like a family crest."""
    img = _shell(size)
    d = ImageDraw.Draw(img)
    S_ = float(size)
    w = S_ * 0.050
    d.arc([S_ * 0.30, S_ * 0.10, S_ * 0.74, S_ * 0.90], start=270, end=90,
          fill=CREAM, width=int(w))
    d.line([(S_ * 0.52, S_ * 0.10), (S_ * 0.52, S_ * 0.90)],
           fill=CREAM, width=int(w * 0.45))
    _paste_trishool(img, int(S_ * 0.72), S_ * 0.5, S_ * 0.5, rot=-32, shaft=0.44)
    return img


def opt_mark(size=S):
    """Bow + trishoolam, no figure — the version that survives 16px."""
    img = _shell(size)
    d = ImageDraw.Draw(img)
    S_ = float(size)
    w = S_ * 0.058
    aim_y = S_ * 0.5
    tip_t, tip_b, _ = _bow(
        d, S_, (S_ * 0.13, S_ * 0.13, S_ * 0.47, S_ * 0.87), aim_y, w)
    d.line([tip_t, (S_ * 0.22, aim_y)], fill=CREAM, width=int(w * 0.45))
    d.line([tip_b, (S_ * 0.22, aim_y)], fill=CREAM, width=int(w * 0.45))
    _paste_trishool(img, int(S_ * 0.74), S_ * 0.60, aim_y, rot=-90, shaft=0.46)
    return img


OPTIONS = {1: opt_archer, 2: opt_upright, 3: opt_crossed, 4: opt_mark}


def write(choice: int = 1):
    OUT.mkdir(exist_ok=True)
    main = OPTIONS[choice](S)
    main.resize((512, 512), Image.LANCZOS).save(OUT / "logo.png")
    main.resize((180, 180), Image.LANCZOS).save(OUT / "logo-180.png")
    mark = opt_mark(S)                       # tab always gets the legible mark
    mark.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.png")
    mark.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png")
    print(f"wrote logo (option {choice}) + favicon (bow mark)")


if __name__ == "__main__":
    write(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
