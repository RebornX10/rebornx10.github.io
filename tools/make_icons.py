"""Generate the PWA icon set (an atom mark in the app accent colour on the dark
app background). Run once with Pillow installed; the PNGs are committed so the
runtime never needs Pillow:

    pip install Pillow && python tools/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "static"
BG = (15, 17, 23, 255)        # #0f1117  (app dark background)
ACCENT = (110, 168, 254, 255)  # #6ea8fe  (app accent)
SS = 4                         # supersampling for smooth edges


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if maskable:                       # full-bleed: the OS applies its own mask
        d.rectangle([0, 0, s, s], fill=BG)
        atom = 0.52                    # keep the mark inside the safe zone
    else:                              # rounded-rect app tile
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.18), fill=BG)
        atom = 0.62

    cx = cy = s / 2
    a = s * atom / 2          # orbit semi-major
    b = a * 0.42             # orbit semi-minor
    ring = max(2, int(s * 0.020))
    for ang in (0, 60, 120):
        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - a, cy - b, cx + a, cy + b],
                                      outline=ACCENT, width=ring)
        img.alpha_composite(layer.rotate(ang, center=(cx, cy), resample=Image.BICUBIC))

    nr = s * 0.075           # nucleus
    d.ellipse([cx - nr, cy - nr, cx + nr, cy + nr], fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    draw_icon(192).save(OUT / "icon-192.png")
    draw_icon(512).save(OUT / "icon-512.png")
    draw_icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
    draw_icon(180).save(OUT / "apple-touch-icon.png")
    draw_icon(32).save(OUT / "favicon.png")
    print("wrote icons to", OUT)


if __name__ == "__main__":
    main()
