#!/usr/bin/env python3
"""Build the app icon family — the Hitchwiki thumb standing on a stylised street map.

Standalone one-off asset builder (plain `python3`, needs Pillow + numpy, no app context).
The outputs are checked into git under `hitch/static/`; re-run it only to change the mark.
Because the container is where Pillow lives, that means:

    sudo docker cp hitch/scripts/build_logo.py hitchhiking-map:/tmp/build_logo.py
    sudo docker exec hitchhiking-map python3 /tmp/build_logo.py --out-dir /app/hitch/static

Writes `logo_512.png`, `logo_192.png`, `logo.png`, `icon.png` and `favicon.ico`.

The thumb is not drawn here and must never be redrawn: it is Hitchwiki's own mark, taken
verbatim from the hitchwiki-graphics repo. What this script replaces is everything the old
logo had *around* it — a flat gold gradient under a "HITCHWIKI" wordmark — with a map, so
the icon says at a glance that this is the hitchhiking *map* and not the wiki.

Three things about the drawing are deliberate:

* **The streets come from a binary space partition, not a grid.** A city reads as a city
  because its blocks are unequal and its streets inherit a hierarchy — the first cut is an
  arterial, the last an alley. An even grid of equal cells reads as graph paper, which is
  exactly what the first attempt looked like. The whole network is then drawn oversized and
  rotated, because streets parallel to the icon's own edges read as a pattern rather than
  as somewhere.
* **The ground under the thumb is deepened before the thumb lands on it.** The hand is
  near-white and so are the streets, so without that halo (and its drop shadow) the
  silhouette dissolves into whatever road it happens to cross.
* **Small sizes get their own master.** Below ~48 px the street network and the dashed
  route are mush and eat the hand; `icon.png` and `favicon.ico` are therefore rendered from
  a simplified composition with a larger thumb. Everything is composed once at 512 and
  downscaled, so every size shows the identical artwork rather than a re-rolled layout.
"""

import argparse
import io
import random
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# https://github.com/Hitchwiki/hitchwiki-graphics — the project's own thumb, hi-res with
# a clean alpha channel. Do not substitute a cut-out of the old logo: that one carries a
# soft gold outer glow which rings the hand in yellow wherever it crosses a white street.
THUMB_URL = "https://raw.githubusercontent.com/Hitchwiki/hitchwiki-graphics/master/thumb/thumb-hires.png"

# The gold of the old logo, top to bottom, kept verbatim: the background changes from a
# plain field to a map, but the brand colour it is drawn in does not.
GOLD_TOP = (227, 171, 1)
GOLD_BOT = (247, 220, 108)
ROAD = (255, 250, 233)
WATER = (150, 193, 197)
# The brown the wordmark used to be printed in, now carrying the planned route — the one
# piece of the old lockup that survives the wordmark's removal.
ROUTE = (110, 58, 18)

SS = 4  # supersample factor; everything is drawn at 512*SS and downscaled once
MASTER = 512
STREET_ANGLE = -11.0
SEED = 11


def gradient(size):
    y = np.linspace(0, 1, size, dtype=np.float32)[:, None]
    top = np.array(GOLD_TOP, dtype=np.float32)
    bot = np.array(GOLD_BOT, dtype=np.float32)
    row = top + (bot - top) * y
    return Image.fromarray(np.repeat(row[:, None, :], size, axis=1).astype(np.uint8), "RGB").convert("RGBA")


def catmull_rom(points, steps=24):
    """Sample a smooth curve through points — used for the river and the route."""
    p = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(len(p) - 3):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(
                tuple(
                    0.5
                    * (
                        (2 * p1[k])
                        + (-p0[k] + p2[k]) * t
                        + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                        + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3
                    )
                    for k in (0, 1)
                )
            )
    out.append(points[-1])
    return out


def street_cuts(extent, rnd):
    """Split the plane in two over and over; the cuts are the streets.

    Depth is the street's rank: it sets both width and opacity below, which is what gives
    the network an arterials-to-alleys hierarchy for free.
    """
    cuts = []

    def split(x0, y0, x1, y1, depth):
        w, h = x1 - x0, y1 - y0
        if depth > 5 or min(w, h) < 0.11 * extent:
            return
        # Near-square blocks would otherwise always split the same way and stripe.
        vertical = w > h if abs(w - h) > 0.02 * extent else rnd.random() < 0.5
        f = rnd.uniform(0.36, 0.64)
        if vertical:
            x = x0 + w * f
            cuts.append((depth, (x, y0), (x, y1)))
            split(x0, y0, x, y1, depth + 1)
            split(x, y0, x1, y1, depth + 1)
        else:
            y = y0 + h * f
            cuts.append((depth, (x0, y), (x1, y)))
            split(x0, y0, x1, y, depth + 1)
            split(x0, y, x1, y1, depth + 1)

    split(0, 0, extent, extent, 0)
    return cuts


def street_layer(size):
    extent = int(size * 1.7)  # oversized so the rotation below has material to crop from
    layer = Image.new("RGBA", (extent, extent), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rnd = random.Random(SEED)

    # Deepest first, so an arterial draws over the alleys that run into it.
    for depth, a, b in sorted(street_cuts(extent, rnd), key=lambda cut: -cut[0]):
        if max(abs(b[0] - a[0]), abs(b[1] - a[1])) < 0.14 * extent:
            continue  # a stub too short to read as a street reads as a glitch
        width = max(2, int(0.0175 * extent * (0.66**depth)))
        alpha = min(255, int(245 * (0.80**depth)) + 40)
        draw.line([a, b], fill=ROAD + (alpha,), width=width)

    layer = layer.rotate(STREET_ANGLE, resample=Image.BICUBIC, expand=False)
    off = (extent - size) // 2
    return layer.crop((off, off, off + size, off + size))


def water_layer(size):
    """A river. One cool accent is what stops the icon reading as a plain gold field."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).line(
        catmull_rom(
            [
                (-0.08 * size, 0.30 * size),
                (0.14 * size, 0.46 * size),
                (0.26 * size, 0.72 * size),
                (0.46 * size, 0.94 * size),
                (0.60 * size, 1.10 * size),
            ]
        ),
        fill=WATER + (255,),
        width=int(0.062 * size),
        joint="curve",
    )
    return layer


def dashed_line(draw, points, width, fill, dash, gap):
    """Dashed polyline with round caps — reads as a planned route, not another street."""
    on, run, segment = True, 0.0, [points[0]]
    for a, b in zip(points, points[1:]):
        run += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        segment.append(b)
        if run >= (dash if on else gap):
            if on and len(segment) > 1:
                draw.line(segment, fill=fill, width=width, joint="curve")
                for point in (segment[0], segment[-1]):
                    r = width / 2
                    draw.ellipse([point[0] - r, point[1] - r, point[0] + r, point[1] + r], fill=fill)
            on, run, segment = not on, 0.0, [b]
    if on and len(segment) > 1:
        draw.line(segment, fill=fill, width=width, joint="curve")


def render(thumb, route=True, thumb_scale=0.66):
    """Compose one master at MASTER px."""
    size = MASTER * SS
    img = gradient(size)
    img.alpha_composite(water_layer(size))
    img.alpha_composite(street_layer(size))

    if route:
        dashed_line(
            ImageDraw.Draw(img),
            catmull_rom(
                [
                    (-0.06 * size, 0.86 * size),
                    (0.24 * size, 0.70 * size),
                    (0.50 * size, 0.53 * size),
                    (0.76 * size, 0.34 * size),
                    (1.06 * size, 0.22 * size),
                ]
            ),
            int(0.030 * size),
            ROUTE + (255,),
            0.055 * size,
            0.038 * size,
        )

    # Deepen the ground where the hand will sit — see the module docstring.
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.sqrt(((xx - size / 2) / (size * 0.40)) ** 2 + ((yy - size * 0.52) / (size * 0.44)) ** 2)
    halo = Image.fromarray((np.clip(1.0 - r, 0, 1) ** 1.4 * 150).astype(np.uint8), "L")
    img.alpha_composite(
        Image.merge(
            "RGBA", (Image.new("L", (size, size), 176), Image.new("L", (size, size), 118), Image.new("L", (size, size), 12), halo)
        )
    )

    height = int(size * thumb_scale)
    width = max(1, round(thumb.width * height / thumb.height))
    hand = thumb.resize((width, height), Image.LANCZOS)
    # Centred, and kept inside the central 80% circle a maskable PWA icon may be cropped to.
    pos = ((size - width) // 2, int(size * 0.52) - height // 2)

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow.paste((74, 38, 6, 150), (pos[0], pos[1] + int(0.014 * size)), hand)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(0.020 * size)))
    img.alpha_composite(hand, pos)

    return img.resize((MASTER, MASTER), Image.LANCZOS)


def main():
    default_out = Path(__file__).resolve().parents[1] / "static"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thumb", help="local copy of thumb-hires.png (default: download)")
    parser.add_argument("--out-dir", type=Path, default=default_out)
    args = parser.parse_args()

    if args.thumb:
        thumb = Image.open(args.thumb).convert("RGBA")
    else:
        with urllib.request.urlopen(THUMB_URL, timeout=120) as response:
            thumb = Image.open(io.BytesIO(response.read())).convert("RGBA")

    full = render(thumb)
    small = render(thumb, route=False, thumb_scale=0.80)

    out = args.out_dir
    written = []
    for name, size in (("logo_512.png", 512), ("logo_192.png", 192), ("logo.png", 144)):
        # logo.png was 144x152 and is square now: the brand bar renders it at a hard
        # 24x24 (so it was being squashed) and the share card derives its width from the
        # image, so nothing had to change for it.
        #
        # Saved as RGB, not RGBA: the icon is a full-bleed square with no transparent
        # pixel anywhere, so the alpha channel is 25% of the file for nothing. A 256-colour
        # palette would be far smaller again, but it contours the gradient and the halo
        # behind the hand into visible rings — that one is not worth the bytes.
        full.resize((size, size), Image.LANCZOS).convert("RGB").save(out / name, optimize=True)
        written.append(name)

    small.resize((16, 16), Image.LANCZOS).save(out / "icon.png")
    # Multi-size .ico: browsers pick 32 for the tab on a HiDPI screen and 48 for a
    # bookmark tile, and downscaling a 16px source for those looks worse than shipping them.
    small.save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    written += ["icon.png", "favicon.ico"]

    for name in written:
        print(f"{out / name} — {(out / name).stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
