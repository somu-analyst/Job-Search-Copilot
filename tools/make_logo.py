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

    # ── outer prongs: sweep OUT from the collar, then straighten UP so their
    # points run PARALLEL to the central blade. All three prongs of a trishoolam
    # face the same way — angling the tips outward made them read as backward
    # hooks once the whole thing was rotated to fly sideways.
    for s in (-1, 1):
        x0 = cx + s * B * 0.095         # leaves the collar
        out_x = cx + s * B * 0.255      # control point: the belly of the curve
        tip_x = cx + s * B * 0.195      # settles here, then runs straight up
        tip_y = base_y - head_h * 0.80
        path = _bez((x0, base_y),
                    (out_x, base_y - head_h * 0.30),
                    (tip_x, tip_y + B * 0.085))
        d.line(path, fill=color, width=int(w * 0.82), joint="curve")
        # point aimed straight up, same direction as the central blade
        d.polygon([(tip_x, tip_y),
                   (tip_x - w * 0.85, tip_y + B * 0.085),
                   (tip_x + w * 0.85, tip_y + B * 0.085)], fill=color)
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
        d, S_, (S_ * 0.40, S_ * 0.16, S_ * 0.62, S_ * 0.84), aim_y, w)

    draw_hand = (S_ * 0.285, aim_y)
    sw = max(2, int(w * 0.42))
    d.line([tip_t, draw_hand], fill=CREAM, width=sw)     # string, drawn back
    d.line([tip_b, draw_hand], fill=CREAM, width=sw)

    # Trishoolam nocked on the string: shaft reaches back to the draw hand, head
    # clears the bow on the far side — the way a nocked arrow actually sits.
    # Oversizing it made the head swallow the bow.
    _paste_trishool(img, int(S_ * 0.58), S_ * 0.605, aim_y, rot=-90, shaft=0.56)

    d = ImageDraw.Draw(img)                              # redraw over the layer
    hx, hy, hr = S_ * 0.170, S_ * 0.300, S_ * 0.068
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=CREAM)
    sh, hip = (S_ * 0.180, S_ * 0.405), (S_ * 0.175, S_ * 0.630)
    d.line([sh, hip], fill=CREAM, width=int(limb * 1.8))
    d.line([sh, grip], fill=CREAM, width=int(limb))      # locked-out bow arm
    elbow = (S_ * 0.080, S_ * 0.460)                     # elbow behind the body
    d.line([sh, elbow], fill=CREAM, width=int(limb))
    d.line([elbow, draw_hand], fill=CREAM, width=int(limb))
    d.line([hip, (S_ * 0.285, S_ * 0.870)], fill=CREAM, width=int(limb))
    d.line([hip, (S_ * 0.070, S_ * 0.870)], fill=CREAM, width=int(limb))
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


def _archer_layer(box: int, arrow_color=ORANGE) -> Image.Image:
    """Arjuna at full draw, aimed right, on a transparent square.

    The arrow here is a PLAIN arrow, not a trishoolam: in the stacked mark the
    trishoolam is its own element below, and drawing it twice made the tile read
    as clutter rather than as two symbols."""
    L = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    B = float(box)
    w, limb = B * 0.042, B * 0.048
    aim_y = B * 0.50

    # bow: limbs curve toward the target, string is the chord behind
    bx0, by0, bx1, by1 = B * 0.44, B * 0.06, B * 0.74, B * 0.94
    d.arc([bx0, by0, bx1, by1], start=270, end=90, fill=CREAM, width=int(w))
    cx_bow = (bx0 + bx1) / 2
    grip = (bx1 - w * 0.4, aim_y)

    # string at FULL DRAW -> a deep V back at the cheek
    draw_hand = (B * 0.315, aim_y)
    sw = max(2, int(w * 0.45))
    d.line([(cx_bow, by0), draw_hand], fill=CREAM, width=sw)
    d.line([(cx_bow, by1), draw_hand], fill=CREAM, width=sw)

    # arrow: nocked at the draw hand, flying right past the grip
    tipx = B * 0.99
    d.line([(draw_hand[0], aim_y), (tipx - B * 0.06, aim_y)],
           fill=arrow_color, width=int(w * 0.85))
    hh = w * 1.15
    d.polygon([(tipx, aim_y), (tipx - B * 0.085, aim_y - hh),
               (tipx - B * 0.085, aim_y + hh)], fill=arrow_color)
    # fletching
    d.line([(draw_hand[0] + B * 0.01, aim_y - B * 0.045),
            (draw_hand[0] + B * 0.06, aim_y)], fill=arrow_color, width=int(w * 0.5))
    d.line([(draw_hand[0] + B * 0.01, aim_y + B * 0.045),
            (draw_hand[0] + B * 0.06, aim_y)], fill=arrow_color, width=int(w * 0.5))

    hx, hy, hr = B * 0.205, B * 0.275, B * 0.076
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=CREAM)
    sh, hip = (B * 0.215, B * 0.395), (B * 0.205, B * 0.635)
    d.line([sh, hip], fill=CREAM, width=int(limb * 1.8))
    d.line([sh, grip], fill=CREAM, width=int(limb))          # locked-out bow arm
    elbow = (B * 0.095, B * 0.450)                           # elbow behind body
    d.line([sh, elbow], fill=CREAM, width=int(limb))
    d.line([elbow, draw_hand], fill=CREAM, width=int(limb))
    d.line([hip, (B * 0.330, B * 0.905)], fill=CREAM, width=int(limb))
    d.line([hip, (B * 0.075, B * 0.905)], fill=CREAM, width=int(limb))
    return L


def _fit(layer: Image.Image, max_w: float, max_h: float) -> Image.Image:
    """Crop a layer to its ink and scale it to fit a box, keeping aspect.
    Without the crop, the transparent padding is what gets scaled and the two
    elements overlap even though the maths says they shouldn't."""
    bb = layer.getbbox()
    if bb:
        layer = layer.crop(bb)
    k = min(max_w / layer.width, max_h / layer.height)
    return layer.resize((max(1, int(layer.width * k)),
                         max(1, int(layer.height * k))), Image.LANCZOS)


def opt_stacked(size=S):
    """Arjuna's bow ABOVE, Shiva's trishoolam BELOW — the two halves of the name,
    each in its own zone so neither crowds the other."""
    img = _shell(size)
    S_ = float(size)

    a = _fit(_archer_layer(int(S_ * 1.1)), S_ * 0.74, S_ * 0.40)     # top zone
    img.alpha_composite(a, (int(S_ * 0.5 - a.width / 2),
                            int(S_ * 0.10)))

    t = _fit(trishool_layer(int(S_ * 0.9), shaft=0.30), S_ * 0.40, S_ * 0.36)
    img.alpha_composite(t, (int(S_ * 0.5 - t.width / 2),
                            int(S_ * 0.58)))                          # bottom zone
    return img


def opt_thirdeye(size=S):
    """Shiva's third eye — the eye that SEES. The right mark for a search tool:
    it looks for what you can't. Tripundra (three ash stripes) above, the
    vertical eye below, pupil as the orange accent.

    Built to survive 16px: one big shape, one accent dot, three fat stripes.
    """
    img = _shell(size)
    d = ImageDraw.Draw(img)
    B = float(size)
    cx = B * 0.5

    # ── Tripundra: three stripes. Kept thin and short on purpose — they're the
    # context, not the subject. The EYE has to be the thing you see first.
    sw = B * 0.042
    for i, y in enumerate((B * 0.145, B * 0.225, B * 0.305)):
        inset = B * 0.20 + i * B * 0.022     # each lower stripe a touch shorter
        d.rounded_rectangle([inset, y - sw / 2, B - inset, y + sw / 2],
                            radius=sw / 2, fill=CREAM)

    # ── The eye: a vertical almond (pointed top and bottom), from two bezier
    # edges so it reads as an EYE rather than a circle.
    top, bot = B * 0.375, B * 0.935
    half = B * 0.255                    # how far the lids bulge out
    midy = (top + bot) / 2
    right = _bez((cx, top), (cx + half * 1.62, midy), (cx, bot), n=44)
    left = _bez((cx, bot), (cx - half * 1.62, midy), (cx, top), n=44)
    d.polygon(right + left, fill=CREAM)

    # iris + pupil — the accent lands exactly where the eye is looking
    r_i = B * 0.128
    d.ellipse([cx - r_i, midy - r_i, cx + r_i, midy + r_i], fill=ORANGE)
    r_p = B * 0.056
    d.ellipse([cx - r_p, midy - r_p, cx + r_p, midy + r_p], fill=(16, 38, 26))
    # catchlight — what makes an eye read as alive rather than as a target
    r_c = B * 0.028
    d.ellipse([cx + r_i * 0.32 - r_c, midy - r_i * 0.46 - r_c,
               cx + r_i * 0.32 + r_c, midy - r_i * 0.46 + r_c], fill=CREAM)
    return img


OPTIONS = {1: opt_archer, 2: opt_upright, 3: opt_crossed, 4: opt_mark,
           5: opt_stacked, 6: opt_thirdeye}


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
