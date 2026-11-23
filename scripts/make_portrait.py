"""Zeichnet das ASCII-Porträt einmalig aus dem Foto (lokal ausführen, Ergebnis wird committet).

  python scripts/make_portrait.py [Zeilen]

Liest assets/portrait-src.jpg, entfernt den grauen Hintergrund, setzt das Bild aus
Schriftzeichen zusammen (Helligkeit + Kanten, damit auch dunkles Haar eine Kontur hat)
und speichert assets/portrait-ascii.png (transparent) + assets/portrait-ascii.txt.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 84
SIZE = 720             # Ausgabe in px (im SVG ~232 px breit → auch auf Retina scharf)
RAMP = " .'`,:;-~=+*cxoO#%8@"
INK, MID = (243, 239, 226), (169, 194, 176)   # Cream, Sage

FONT_CANDIDATES = [r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def main():
    font_path = next(p for p in FONT_CANDIDATES if Path(p).exists())
    lh = SIZE / ROWS
    font = ImageFont.truetype(font_path, round(lh * 1.05))
    cw = font.getlength("M")
    cols = int(SIZE / cw)

    src = Image.open(ROOT / "assets" / "portrait-src.jpg").convert("RGB")
    small = src.resize((cols, ROWS), Image.LANCZOS)
    gray = ImageOps.autocontrast(small.convert("L"), cutoff=1)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    pix, g, e = small.load(), gray.load(), edges.load()

    # Hintergrund: grau, kaum Sättigung -> Flood-Fill vom Rand
    def bgish(x, y):
        r, gg, b = pix[x, y]
        mx, mn = max(r, gg, b), min(r, gg, b)
        lum = .299 * r + .587 * gg + .114 * b
        return (mx - mn) / (mx + 1e-6) < .10 and 55 < lum < 165

    bg, stack = set(), [(x, 0) for x in range(cols)] + [(0, y) for y in range(ROWS)] + [(cols - 1, y) for y in range(ROWS)]
    while stack:
        x, y = stack.pop()
        if (x, y) in bg or not (0 <= x < cols and 0 <= y < ROWS) or not bgish(x, y):
            continue
        bg.add((x, y))
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    lines = []
    for y in range(ROWS):
        row = ""
        for x in range(cols):
            if (x, y) in bg:
                row += " "
                continue
            v = min(1.0, .95 * (g[x, y] / 255) ** 1.6 + .75 * e[x, y] / 255 + .04)
            row += RAMP[max(1, min(len(RAMP) - 1, round(v * (len(RAMP) - 1))))]
        lines.append(row)

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (SIZE - cols * cw) / 2
    for y, row in enumerate(lines):
        for x, ch in enumerate(row):
            if ch != " ":
                dense = RAMP.index(ch) / (len(RAMP) - 1)
                d.text((x0 + x * cw, y * lh), ch, font=font, fill=INK if dense > .3 else MID)
    # wenige Farben + Transparenz -> kleine PNG
    img.quantize(colors=12, method=Image.Quantize.FASTOCTREE).save(ROOT / "assets" / "portrait-ascii.png", optimize=True)
    (ROOT / "assets" / "portrait-ascii.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{cols}x{ROWS} Zeichen -> assets/portrait-ascii.png")


if __name__ == "__main__":
    main()
