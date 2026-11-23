"""Zeichnet das Porträt einmalig aus dem Foto (lokal ausführen, Ergebnis wird committet).

  python scripts/make_portrait.py pixel [Auflösung]   -> assets/portrait-pixel.png  (Standard 128)
  python scripts/make_portrait.py ascii [Zeilen]      -> assets/portrait-ascii.png  (Standard 84)

Beide lesen assets/portrait-src.jpg (quadratisch, Gesicht mittig) und entfernen den grauen
Fotohintergrund per Flood-Fill vom Rand. render_cards.py bettet die PNG ein; welche,
bestimmt PORTRAIT_STYLE in config.py.
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "portrait-src.jpg"

# Verlauf der Website-Farben: Pine 950 -> Pine 800 -> Leaf -> Sage -> Cream
STOPS = ["#10271D", "#1D4432", "#34684C", "#6F9B80", "#A9C2B0", "#F3EFE2"]


def background_mask(img: Image.Image) -> set:
    """Grauer, kaum gesättigter Fotohintergrund, zusammenhängend vom Rand aus."""
    w, h = img.size
    pix = img.load()

    def bgish(x, y):
        r, g, b = pix[x, y]
        mx, mn = max(r, g, b), min(r, g, b)
        lum = .299 * r + .587 * g + .114 * b
        return (mx - mn) / (mx + 1e-6) < .10 and 50 < lum < 165

    bg = set()
    stack = [(x, 0) for x in range(w)] + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    while stack:
        x, y = stack.pop()
        if (x, y) in bg or not (0 <= x < w and 0 <= y < h) or not bgish(x, y):
            continue
        bg.add((x, y))
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return bg


def palette(levels: int) -> list:
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in STOPS]
    out = []
    for i in range(levels):
        t = i / (levels - 1) * (len(rgb) - 1)
        k = min(int(t), len(rgb) - 2)
        f = t - k
        out.append(tuple(round(rgb[k][j] + (rgb[k + 1][j] - rgb[k][j]) * f) for j in range(3)))
    return out


def make_pixel(n: int = 128, levels: int = 12, blur: float = 1.2, scale: int = 4) -> None:
    """Pixel-Art: leicht geglättet (ruhige Haut), 12 Grünstufen, Hintergrund transparent.
    Wird mit NEAREST hochskaliert gespeichert, damit sie überall scharf bleibt."""
    im = Image.open(SRC).convert("RGB").filter(ImageFilter.GaussianBlur(blur))
    small = im.resize((n, n), Image.LANCZOS)
    bg = background_mask(small)
    pix = small.load()
    lum = {(x, y): .299 * pix[x, y][0] + .587 * pix[x, y][1] + .114 * pix[x, y][2]
           for y in range(n) for x in range(n)}
    fg = sorted(v for p, v in lum.items() if p not in bg)
    lo, hi = fg[int(len(fg) * .02)], fg[int(len(fg) * .985)]
    pal = palette(levels)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    o = out.load()
    for (x, y), v in lum.items():
        if (x, y) not in bg:
            t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
            o[x, y] = pal[min(levels - 1, int(t * levels))] + (255,)
    out = out.resize((n * scale, n * scale), Image.NEAREST)
    out.save(ROOT / "assets" / "portrait-pixel.png", optimize=True)
    print(f"{n}x{n} Pixel, {levels} Stufen -> assets/portrait-pixel.png")


RAMP = " .'`,:;-~=+*cxoO#%8@"
FONTS = [r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def make_ascii(rows: int = 84, size: int = 720) -> None:
    """Zeichen-Porträt (Helligkeit + etwas Kante), als PNG vorgezeichnet."""
    edge = float(os.environ.get("EDGE", ".25"))
    gamma = float(os.environ.get("GAMMA", "1.1"))
    blur = float(os.environ.get("BLUR", ".7"))
    font_path = next(p for p in FONTS if Path(p).exists())
    lh = size / rows
    font = ImageFont.truetype(font_path, round(lh * 1.05))
    cw = font.getlength("M")
    cols = int(size / cw)
    small = Image.open(SRC).convert("RGB").resize((cols, rows), Image.LANCZOS)
    gray = ImageOps.autocontrast(small.convert("L").filter(ImageFilter.GaussianBlur(blur)), cutoff=1)
    edges = gray.filter(ImageFilter.GaussianBlur(.6)).filter(ImageFilter.FIND_EDGES)
    g, e = gray.load(), edges.load()
    bg = background_mask(small)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (size - cols * cw) / 2
    for y in range(rows):
        for x in range(cols):
            if (x, y) in bg:
                continue
            v = min(1.0, (g[x, y] / 255) ** gamma + edge * e[x, y] / 255 + .03)
            k = max(1, min(len(RAMP) - 1, round(v * (len(RAMP) - 1))))
            d.text((x0 + x * cw, y * lh), RAMP[k], font=font,
                   fill=(243, 239, 226) if k / (len(RAMP) - 1) > .3 else (169, 194, 176))
    img.quantize(colors=12, method=Image.Quantize.FASTOCTREE).save(ROOT / "assets" / "portrait-ascii.png", optimize=True)
    print(f"{cols}x{rows} Zeichen -> assets/portrait-ascii.png")


if __name__ == "__main__":
    style = sys.argv[1] if len(sys.argv) > 1 else "pixel"
    arg = [int(sys.argv[2])] if len(sys.argv) > 2 else []
    make_pixel(*arg) if style == "pixel" else make_ascii(*arg)
