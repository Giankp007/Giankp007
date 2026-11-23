"""Rendert die animierten SVG-Karten für das GitHub-Profil-README nach cards/.

  python scripts/render_cards.py            animiert (für GitHub)
  STATIC=1 python scripts/render_cards.py   nur Endzustand (für Screenshots)

Alles, was in einem <img> funktioniert: ein <style>-Block mit CSS-Keyframes,
SMIL-<animate>/<set> und per pyftsubset verkleinerte, als base64-WOFF
eingebettete Schriften. Keine Skripte, keine externen Ressourcen.
Unter prefers-reduced-motion ist jede Animation aus.
"""
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import OrderedDict
from datetime import date, timedelta
import re
from html import escape, unescape
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import config as C  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
STATIC = os.environ.get("STATIC") == "1"
OUT = ROOT / "cards"

# Farben von gian-kappeler.ch (style.css :root)
PAPER, PAPER_RAISE, PAPER_DEEP = "#F6F2E8", "#FCF9F0", "#EFEADC"
INK, MUTED, LINE = "#1D2B23", "#5E6E63", "#DDD5C2"
PINE_950, PINE_900, PINE_800 = "#10271D", "#163527", "#1D4432"
LEAF, LEAF_SOFT, SAGE, CREAM, CREAM_DIM = "#34684C", "#4E8465", "#A9C2B0", "#F3EFE2", "#CFD9CC"

MONTHS_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Zeitplan: jede Karte startet etwas später, die Seite läuft von oben nach unten ab
T_HERO, T_TILES, T_ACTIVITY, T_REPOS, T_GRAPH = 0.0, 1.6, 2.3, 3.4, 4.1

# --------------------------------------------------------------------------- Schriften

UNICODES = ",".join([
    "U+0020-007E", "U+00A0-00FF", "U+2013-2014", "U+2018-201E", "U+2022", "U+2026",
    "U+2190-2193", "U+2197", "U+2605", "U+2212",
])

FONTS = {  # Name -> (Datei, Achsen)
    "Fraunces": ("fonts/fraunces-latin.woff2", {"wght": 600, "opsz": 72}),
    "Schibsted": ("fonts/schibsted-latin.woff2", {"wght": 400}),
    "SchibstedBold": ("fonts/schibsted-latin.woff2", {"wght": 650}),
}
FAMILY = {"Fraunces": "F", "Schibsted": "S", "SchibstedBold": "B"}


class Font:
    """Statische, verkleinerte Schrift: Base64-WOFF + Breitenmessung."""

    def __init__(self, key: str):
        path, axes = FONTS[key]
        var = TTFont(ROOT / path)
        limits = {a.axisTag: axes.get(a.axisTag, a.defaultValue) for a in var["fvar"].axes}
        static = instancer.instantiateVariableFont(var, limits)
        static.flavor = None
        self.src = Path(TMP.name) / f"{key}.ttf"
        static.save(self.src)
        tt = self._subset(UNICODES, "measure")  # Messfont: gesamter Zeichenvorrat
        self.family = FAMILY[key]
        self.key = key
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"].metrics
        self.cache = {}

    def _subset(self, unicodes: str, tag: str) -> TTFont:
        """pyftsubset (= python -m fontTools.subset): nur benötigte Zeichen, als WOFF."""
        dst = Path(TMP.name) / f"{self.src.stem}-{tag}.woff"
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(self.src),
                        f"--unicodes={unicodes}", "--flavor=woff", "--with-zopfli",
                        "--layout-features=kern,liga", "--no-hinting",
                        "--desubroutinize", f"--output-file={dst}"], check=True)
        self.last = dst
        return TTFont(dst)

    def css(self, chars: str) -> str:
        """@font-face mit genau den Zeichen, die in der Karte vorkommen."""
        cps = ",".join(f"U+{ord(c):04X}" for c in sorted(set(chars) | {" "}))
        if cps not in self.cache:
            self._subset(cps, f"c{len(self.cache)}")
            self.cache[cps] = base64.b64encode(self.last.read_bytes()).decode()
        return (f"@font-face{{font-family:'{self.family}';"
                f"src:url(data:font/woff;base64,{self.cache[cps]}) format('woff')}}")

    def width(self, text: str, size: float) -> float:
        units = 0
        for ch in text:
            g = self.cmap.get(ord(ch)) or self.cmap.get(ord("?"))
            units += self.hmtx[g][0]
        return units * size / self.upm

    def wrap(self, text: str, size: float, max_w: float, max_lines: int = 2) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            test = f"{cur} {word}".strip()
            if self.width(test, size) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while self.width(lines[-1] + "…", size) > max_w and " " in lines[-1]:
                lines[-1] = lines[-1].rsplit(" ", 1)[0]
            lines[-1] += "…"
        return lines


TMP = tempfile.TemporaryDirectory()
print("Schriften vorbereiten …")
F = {k: Font(k) for k in FONTS}
SERIF, SANS, BOLD = F["Fraunces"], F["Schibsted"], F["SchibstedBold"]

# --------------------------------------------------------------------------- Bausteine

BASE_CSS = """
.f{font-family:'F',Georgia,serif;font-weight:normal}
.s{font-family:'S','Segoe UI',system-ui,sans-serif}
.b{font-family:'B','Segoe UI',system-ui,sans-serif;font-weight:normal}
.up{animation:up .8s cubic-bezier(.23,1,.32,1) both}
.fade{animation:fade .9s ease both}
.grow{transform-box:fill-box;transform-origin:50% 100%;animation:grow .9s cubic-bezier(.23,1,.32,1) both}
.pop{transform-box:fill-box;transform-origin:50% 50%;animation:pop .6s cubic-bezier(.34,1.56,.64,1) both}
.swing{transform-box:fill-box;transform-origin:50% 100%;animation:swing 1s cubic-bezier(.34,1.4,.64,1) both}
.zoom{transform-box:fill-box;transform-origin:50% 50%;animation:zoom 1.1s cubic-bezier(.23,1,.32,1) both}
.cell{animation:cell .5s ease-out both}
.draw{animation:draw 1.2s cubic-bezier(.23,1,.32,1) both}
.row{animation:fade .35s ease-out both}
.static-only{display:none}
@keyframes up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes pop{0%{opacity:0;transform:scale(.4)}100%{opacity:1;transform:scale(1)}}
@keyframes swing{0%{opacity:0;transform:translateY(60px) rotate(-5deg)}55%{opacity:1;transform:translateY(-6px) rotate(1.2deg)}100%{opacity:1;transform:none}}
@keyframes zoom{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:scale(1)}}
@keyframes cell{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
@keyframes draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important}
  .anim-only{display:none}
  .static-only{display:inline}
}
"""

STATIC_CSS = """
.f{font-family:'F',Georgia,serif;font-weight:normal}
.s{font-family:'S','Segoe UI',system-ui,sans-serif}
.b{font-family:'B','Segoe UI',system-ui,sans-serif;font-weight:normal}
.anim-only{display:none}
"""


def svg(w: int, h: int, body: str, fonts: list[Font], title: str) -> str:
    # Zeichen je Schrift einsammeln (class="f|s|b" am <text>)
    used = {f.family: "" for f in fonts}
    for cls, content in re.findall(r'<text [^>]*class="([fsb])"[^>]*>([^<]*)<', body):
        used[cls.upper()] = used.get(cls.upper(), "") + unescape(content)
    css = "".join(f.css(used[f.family]) for f in fonts if used.get(f.family)) \
        + (STATIC_CSS if STATIC else BASE_CSS)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">'
            f"<title>{escape(title)}</title><style>{css}</style>{body}</svg>")


def anim(cls: str, delay: float) -> str:
    """class + Verzögerung; im STATIC-Modus nichts (= Endzustand)."""
    if STATIC:
        return ""
    return f' class="{cls}" style="animation-delay:{delay:.2f}s"'


def text(x, y, s, cls, size, fill, extra="", anchor="start") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def counter(x, y, value: int, begin: float, cls, size, fill, anchor="start", frames=18,
            dur=1.1, fmt=lambda v: f"{v:,}".replace(",", "'")) -> str:
    """Zahl zählt hoch: SMIL-<set>-Frames schalten Textvarianten sichtbar.
    STATIC oder reduced-motion: nur der Endwert."""
    final = text(x, y, fmt(value), cls, size, fill, anchor=anchor)
    if STATIC:
        return final
    parts = [f'<g class="anim-only">']
    steps = sorted({round(value * (i / frames) ** 0.6) for i in range(frames + 1)})
    if steps[0] != 0:
        steps.insert(0, 0)
    n = len(steps)
    for i, v in enumerate(steps):
        t0 = begin + dur * i / max(n - 1, 1)
        t1 = begin + dur * (i + 1) / max(n - 1, 1)
        vis = "visible" if i == 0 else "hidden"
        sets = ""
        if i > 0:
            sets += f'<set attributeName="visibility" to="visible" begin="{t0:.2f}s" fill="freeze"/>'
        if i < n - 1:
            sets += f'<set attributeName="visibility" to="hidden" begin="{t1:.2f}s" fill="freeze"/>'
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" visibility="{vis}">{escape(fmt(v))}{sets}</text>')
    parts.append("</g>")
    return "".join(parts) + f'<g class="static-only">{final}</g>'


def write(name: str, content: str) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.svg").write_text(content, encoding="utf-8")
    print(f"  cards/{name}.svg  {len(content.encode()) / 1024:.1f} KB")


# --------------------------------------------------------------------------- Daten

def load_contributions():
    raw = json.loads((ROOT / "data" / "contributions.json").read_text(encoding="utf-8"))
    days = [(date.fromisoformat(d["date"]), d["count"]) for w in raw["weeks"] for d in w]
    return raw, days


def stats(days):
    today = days[-1][0]
    counts = {d: c for d, c in days}
    active = sum(1 for _, c in days if c > 0)
    busiest = max(days, key=lambda dc: dc[1])

    longest = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    # aktuelle Serie: heute darf noch leer sein
    cur, d = 0, today
    if counts.get(d, 0) == 0:
        d -= timedelta(days=1)
    while counts.get(d, 0) > 0:
        cur += 1
        d -= timedelta(days=1)

    months = OrderedDict()
    y, m = today.year, today.month
    for _ in range(12):
        months[(y, m)] = 0
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months = OrderedDict(reversed(list(months.items())))
    for d, c in days:
        if (d.year, d.month) in months:
            months[(d.year, d.month)] += c
    return dict(ndays=len(days), active=active, busiest=busiest, longest=longest, current=cur,
                months=months, total=sum(c for _, c in days))


# --------------------------------------------------------------------------- Karten

def pixel_portrait(path: Path, n: int = 64):
    """Foto -> Pixel-Art im Website-Grün. Hintergrund (grau) wird per Flood-Fill
    vom Rand entfernt, der Rest in 8 feste Helligkeitsstufen eingeteilt."""
    from PIL import Image, ImageFilter
    im = Image.open(path).convert("RGB").filter(ImageFilter.UnsharpMask(3, 180, 2))
    small = im.resize((n, n), Image.LANCZOS)
    pix = small.load()
    lum, bgish = {}, {}
    for y in range(n):
        for x in range(n):
            r, g, b = pix[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            sat = (mx - mn) / (mx + 1e-6)
            lum[x, y] = .299 * r + .587 * g + .114 * b
            bgish[x, y] = sat < .10 and 55 < lum[x, y] < 160
    bg = set()
    stack = [(x, y) for i in range(n) for (x, y) in ((0, i), (n - 1, i), (i, 0))]
    while stack:
        x, y = stack.pop()
        if (x, y) in bg or not (0 <= x < n and 0 <= y < n) or not bgish[x, y]:
            continue
        bg.add((x, y))
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    pal = [PINE_950, "#18382A", PINE_800, LEAF, LEAF_SOFT, "#7FA88D", SAGE, CREAM]
    thr = [45, 70, 95, 125, 155, 185, 215]
    return [[None if (x, y) in bg else pal[sum(lum[x, y] > t for t in thr)] for x in range(n)]
            for y in range(n)]


def hero():
    W, H = 880, 330
    t = T_HERO
    has_img = bool(C.PORTRAIT) and (ROOT / C.PORTRAIT).exists()
    tx = 56
    max_text_w = 500 if has_img else 760
    b = [f'<defs><clipPath id="card"><rect width="{W}" height="{H}" rx="20"/></clipPath>'
         f'<linearGradient id="glow" x1="0" y1="0" x2="1" y2="1">'
         f'<stop offset="0" stop-color="{PINE_800}"/><stop offset="1" stop-color="{PINE_950}"/></linearGradient></defs>',
         f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="url(#glow)"/></g>']

    # ohne ABOUT-Satz rutscht der Textblock nach unten, damit er mittig steht
    dy = 22 if not C.ABOUT.strip() else 0

    # Status als ruhige Zeile: keine Pille, kein Punkt
    b.append(f'<g{anim("fade", t + .1)}>'
             + text(tx, 82 + dy, C.STATUS.upper(), "b", 12, SAGE, ' letter-spacing="2.4"') + "</g>")

    # Name: Wort für Wort, darüber ein langsamer Glanz (SMIL gradientTransform)
    size, y = 66, 152 + dy
    x = tx
    for i, wd in enumerate(C.NAME.split()):
        b.append(f'<g{anim("up", t + .25 + i * .14)}>' + text(x, y, wd, "f", size, CREAM) + "</g>")
        x += SERIF.width(wd + " ", size)
    name_w = SERIF.width(C.NAME, size)
    if not STATIC:
        sweep = (f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="{tx}" y1="0" x2="{tx + 180}" y2="0">'
                 f'<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                 f'<stop offset=".5" stop-color="#E9F5EC" stop-opacity=".85"/>'
                 f'<stop offset="1" stop-color="#fff" stop-opacity="0"/>'
                 f'<animateTransform attributeName="gradientTransform" type="translate" '
                 f'values="-200 0;{name_w + 40:.0f} 0;{name_w + 40:.0f} 0" keyTimes="0;.2;1" dur="8s" '
                 f'begin="{t + 1.4:.2f}s" repeatCount="indefinite"/></linearGradient>')
        b.append(f'<defs>{sweep}</defs><g class="anim-only">'
                 + text(tx, y, C.NAME, "f", size, "url(#shine)") + "</g>")

    ul = 110
    b.append(f'<line x1="{tx}" y1="{y + 22}" x2="{tx + ul}" y2="{y + 22}" stroke="{SAGE}" stroke-width="2.5" '
             f'stroke-linecap="round" stroke-dasharray="{ul}" '
             + (f'class="draw" style="--len:{ul};animation-delay:{t + .7:.2f}s"' if not STATIC else "")
             + "/>")

    yy = y + 60
    for line in BOLD.wrap(C.ROLE, 15.5, max_text_w + 20):
        b.append(f'<g{anim("up", t + .55)}>' + text(tx, yy, line, "b", 15.5, SAGE) + "</g>")
        yy += 24
    yy += 4
    for i, line in enumerate(SANS.wrap(C.ABOUT, 16.5, max_text_w, 3) if C.ABOUT.strip() else []):
        b.append(f'<g{anim("up", t + .7 + i * .06)}>' + text(tx, yy, line, "s", 16.5, CREAM_DIM) + "</g>")
        yy += 24

    asc = ROOT / "assets" / "portrait-ascii.png"
    if has_img and C.PORTRAIT_STYLE == "ascii" and asc.exists():
        # Zeichen-Porträt: vorgezeichnete PNG, in Streifen von oben nach unten eingeblendet
        box, pad, strips = 250, 9, 32
        bx, by = W - 56 - box, (H - box) / 2
        inner = box - 2 * pad
        data = base64.b64encode(asc.read_bytes()).decode()
        sh = inner / strips
        defs = [f'<image id="asc" href="data:image/png;base64,{data}" x="{bx + pad}" y="{by + pad}" '
                f'width="{inner}" height="{inner}"/>']
        for k in range(strips):
            defs.append(f'<clipPath id="s{k}"><rect x="{bx}" y="{by + pad + k * sh - .2:.2f}" width="{box}" '
                        f'height="{sh + .4:.2f}"/></clipPath>')
        b.append("<defs>" + "".join(defs) + "</defs>"
                 f'<g{anim("fade", t + .3)}><rect x="{bx}" y="{by}" width="{box}" height="{box}" rx="18" '
                 f'fill="{PINE_900}" stroke="{SAGE}" stroke-opacity=".3"/></g>')
        for k in range(strips):
            b.append(f'<g clip-path="url(#s{k})"><g{anim("row", t + .4 + k * .045)}><use href="#asc"/></g></g>')
    elif has_img:
        # Pixel-Porträt: quadratische Kachel, mittig in der Höhe; Zeilen bauen sich von oben auf
        grid = pixel_portrait(ROOT / C.PORTRAIT, C.PIXEL_RES)
        n = len(grid)
        box, pad = 250, 9
        bx, by = W - 56 - box, (H - box) / 2
        ps = (box - 2 * pad) / n
        b.append(f'<defs><clipPath id="pic"><rect x="{bx}" y="{by}" width="{box}" height="{box}" rx="18"/></clipPath></defs>'
                 f'<g{anim("fade", t + .3)}><rect x="{bx}" y="{by}" width="{box}" height="{box}" rx="18" '
                 f'fill="{PINE_900}" stroke="{SAGE}" stroke-opacity=".3"/></g>'
                 f'<g clip-path="url(#pic)" shape-rendering="crispEdges">')
        ox, oy = bx + pad, by + pad
        for ry, row in enumerate(grid):
            rects, x0 = [], 0
            while x0 < n:
                c = row[x0]
                x1 = x0
                while x1 + 1 < n and row[x1 + 1] == c:
                    x1 += 1
                if c:
                    rects.append(f'<rect x="{ox + x0 * ps:.2f}" y="{oy + ry * ps:.2f}" '
                                 f'width="{(x1 - x0 + 1) * ps + .3:.2f}" height="{ps + .3:.2f}" fill="{c}"/>')
                x0 = x1 + 1
            if rects:
                b.append(f'<g{anim("row", t + .4 + ry * .016)}>' + "".join(rects) + "</g>")
        b.append("</g>")
    write("hero", svg(W, H, "".join(b), [SERIF, SANS, BOLD], f"{C.NAME}: {C.ROLE}"))


def tiles():
    W, H = 300, 210
    for i, tl in enumerate(C.TILES):
        t = T_TILES + i * .18
        a = tl["accent"]
        b = [f'<defs><clipPath id="c"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18"/></clipPath></defs>',
             f'<g{anim("swing", t)}>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="{PAPER_RAISE}"/>',
             f'<rect x="0" y="0" width="{W}" height="6" fill="{a}" clip-path="url(#c)"/>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="none" stroke="{LINE}" stroke-width="1.5"/>',
             text(26, 44, tl["kicker"], "b", 11.5, a, ' letter-spacing="2.2"'),
             text(24, 92, tl["title"], "f", 34, INK)]
        y = 122
        for line in SANS.wrap(tl["text"], 15, W - 50):
            b.append(text(26, y, line, "s", 15, MUTED))
            y += 21
        b.append(f'<line x1="26" x2="{W - 26}" y1="{H - 50}" y2="{H - 50}" stroke="{LINE}"/>')
        link = tl["link"]
        while BOLD.width(link, 13) > W - 90:
            link = link[:-2]
        b.append(text(26, H - 23, link, "b", 13, a))
        b.append(text(W - 26, H - 21, "↗", "b", 19, a, anchor="end"))
        b.append("</g>")
        write(tl["file"], svg(W, H, "".join(b), [SERIF, SANS, BOLD], f'{tl["title"]}: {tl["text"]}'))


def activity(st, fetched: str):
    W, H = 880, 236
    t = T_ACTIVITY
    b = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="{PAPER}" stroke="{LINE}" stroke-width="1.5"/>',
         f'<g{anim("up", t)}>' + text(40, 48, "Aktivität", "f", 21, INK)
         + text(40 + SERIF.width("Aktivität", 21) + 12, 47, f"Beiträge pro Monat · Stand {fetched}", "s", 13, MUTED)
         + "</g>"]

    months = list(st["months"].items())
    mx = max(v for _, v in months) or 1
    best = max(range(len(months)), key=lambda i: months[i][1])
    x0, base, chart_h, bw, gap = 42, 190, 100, 24, 12
    b.append(f'<line x1="{x0 - 4}" x2="{x0 + 12 * (bw + gap) - gap + 4}" y1="{base}" y2="{base}" '
             f'stroke="{LINE}" stroke-width="1.2"/>')
    for i, ((yr, mo), v) in enumerate(months):
        x = x0 + i * (bw + gap)
        h = max(3, v / mx * chart_h) if v else 2
        col = LEAF if i == best else SAGE
        b.append(f'<rect x="{x}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="4" fill="{col}"'
                 f'{anim("grow", t + .3 + i * .06)}/>')
        b.append(text(x + bw / 2, base + 18, MONTHS_DE[mo - 1], "b" if i == best else "s", 11,
                      INK if i == best else MUTED, anchor="middle"))
        if i == best:
            b.append(f'<g{anim("fade", t + 1.2)}>'
                     + text(x + bw / 2, base - h - 7, str(v), "b", 12, PINE_800, anchor="middle") + "</g>")

    # Kennzahlen als 2x2-Raster
    sx = 520
    b.append(f'<line x1="{sx - 28}" x2="{sx - 28}" y1="76" y2="{H - 28}" stroke="{LINE}"/>')
    bd, bc = st["busiest"]
    cells = [
        ("Beiträge im Jahr", st["total"], None),
        ("Aktuelle Serie", st["current"], f"Tage · längste {st['longest']}"),
        ("Aktive Tage", st["active"], f"von {st['ndays']}"),
        ("Aktivster Tag", None, f"{bc} Beiträge"),
    ]
    for i, (lbl, val, sub) in enumerate(cells):
        cx = sx + (i % 2) * 180
        cy = 92 + (i // 2) * 72
        tt = t + .4 + i * .12
        b.append(f'<g{anim("up", tt)}>' + text(cx, cy, lbl.upper(), "b", 10.5, MUTED, ' letter-spacing="1.5"') + "</g>")
        if val is not None:
            b.append(f'<g{anim("fade", tt)}>' + counter(cx, cy + 30, val, tt + .2, "f", 26, PINE_800) + "</g>")
            vw = SERIF.width(f"{val:,}".replace(",", "'"), 26)
            if sub:
                b.append(f'<g{anim("fade", tt + .8)}>' + text(cx + vw + 8, cy + 29, sub, "s", 12, MUTED) + "</g>")
        else:
            day = f"{bd.day}. {MONTHS_DE[bd.month - 1]} {bd.year}"
            b.append(f'<g{anim("fade", tt)}>' + text(cx, cy + 29, day, "f", 21, PINE_800) + "</g>")
            b.append(f'<g{anim("fade", tt + .8)}>'
                     + text(cx, cy + 48, f"{WEEKDAYS_DE[bd.weekday()]} · {sub}", "s", 12, MUTED) + "</g>")
    write("activity", svg(W, H, "".join(b), [SERIF, SANS, BOLD],
                          f"{st['total']} Beiträge in 12 Monaten, Serie {st['current']} Tage"))


def repos():
    data = json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))
    data = [r for r in data if f"{C.USER}/{r['name']}" in C.FEATURED_REPOS]
    W, H = 300, 196
    for i, r in enumerate(data):
        t = T_REPOS + i * .14
        lang = r.get("primaryLanguage") or {"name": "", "color": MUTED}
        name = r["name"]
        size = 21
        while SERIF.width(name, size) > W - 48 - 44 and size > 13:
            size -= .5
        b = [f'<g{anim("up", t)}>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="{PAPER_RAISE}" stroke="{LINE}" stroke-width="1.5"/>',
             f'<g transform="translate(22 26)" fill="none" stroke="{LEAF}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
             f'<path d="M3 2.5h10.5v13H5a2 2 0 0 0-2 2z"/><path d="M3 17.5a2 2 0 0 1 2-2h8.5"/></g>',
             text(48, 43, name, "f", size, INK),
             text(W - 22, 44, "↗", "b", 17, LEAF, anchor="end")]
        y = 76
        desc = "".join(ch for ch in (r.get("description") or "") if ord(ch) in SANS.cmap).strip()
        for line in SANS.wrap(desc, 13.5, W - 44, 3):
            b.append(text(22, y, line, "s", 13.5, MUTED))
            y += 20
        ul = W - 44
        b.append(f'<line x1="22" x2="{W - 22}" y1="{H - 42}" y2="{H - 42}" stroke="{LINE}" stroke-dasharray="{ul}"'
                 + (f' class="draw" style="--len:{ul};animation-delay:{t + .3:.2f}s"' if not STATIC else "") + "/>")
        fx = 22
        if lang["name"]:
            b.append(f'<circle cx="{fx + 5}" cy="{H - 21.5}" r="5" fill="{lang["color"] or MUTED}"/>')
            b.append(text(fx + 16, H - 17, lang["name"], "b", 12.5, INK))
            fx += 16 + BOLD.width(lang["name"], 12.5) + 14
        others = [n["name"] for n in r["languages"]["nodes"] if n["name"] != lang["name"]][:2]
        if others:
            b.append(text(fx, H - 17, " · ".join(others), "s", 12.5, MUTED))
        if r["stargazerCount"]:
            b.append(text(W - 22, H - 17, f"★ {r['stargazerCount']}", "b", 12.5, INK, anchor="end"))
        b.append("</g>")
        write(f"repo-{name.lower()}", svg(W, H, "".join(b), [SERIF, SANS, BOLD], f"{name}: {r.get('description') or ''}"))
    return data


def graph(raw, days):
    weeks = raw["weeks"]
    cell, gap = 12, 3.2
    step = cell + gap
    gx, gy = 70, 84
    W = int(gx + len(weeks) * step + 36)
    H = 246
    t = T_GRAPH
    nz = sorted(c for _, c in days if c > 0)

    def q(p):
        return nz[min(len(nz) - 1, int(len(nz) * p))] if nz else 1

    levels = [q(.25), q(.5), q(.75)]
    colors = [PAPER_DEEP, SAGE, LEAF_SOFT, LEAF, PINE_800]

    def color(c):
        if c == 0:
            return colors[0]
        for i, lv in enumerate(levels):
            if c <= lv:
                return colors[i + 1]
        return colors[4]

    total = raw["total"]
    b = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20" fill="{PAPER}" stroke="{LINE}" stroke-width="1.5"/>',
         f'<g{anim("up", t)}>' + text(40, 48, "Beitragsgraph", "f", 21, INK) + "</g>",
         f'<g{anim("fade", t + .1)}>' + counter(W - 40, 49, total, t + .2, "f", 21, PINE_800, anchor="end")
         + text(W - 44 - SERIF.width(f"{total:,}".replace(",", "'"), 21), 48, "Beiträge im letzten Jahr ", "s", 13, MUTED,
                anchor="end") + "</g>"]
    for i, wd in ((0, "Mo"), (2, "Mi"), (4, "Fr")):
        b.append(text(gx - 12, gy + i * step + cell - 2, wd, "s", 11, MUTED, anchor="end"))
    last_month = None
    for wi, wk in enumerate(weeks):
        d0 = date.fromisoformat(wk[0]["date"])
        if d0.month != last_month and d0.day <= 7 and wi < len(weeks) - 1:
            b.append(text(gx + wi * step, gy - 12, MONTHS_DE[d0.month - 1], "s", 11.5, MUTED))
            last_month = d0.month
        delay = t + .3 + wi * .028
        cells = []
        for d in wk:
            di = (date.fromisoformat(d["date"]).weekday())  # Mo = 0
            cells.append(f'<rect x="{gx + wi * step:.1f}" y="{gy + di * step:.1f}" width="{cell}" height="{cell}" '
                         f'rx="3" fill="{color(d["count"])}"/>')
        b.append(f'<g{anim("cell", delay)}>' + "".join(cells) + "</g>")
    # Legende
    ly = gy + 7 * step + 26
    lx = W - 40 - 5 * step - BOLD.width("Mehr", 11.5) - 8
    b.append(text(lx - 8, ly + 10, "Weniger", "s", 11.5, MUTED, anchor="end"))
    for i, c in enumerate(colors):
        b.append(f'<rect x="{lx + i * step:.1f}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{c}"/>')
    b.append(text(lx + 5 * step + 4, ly + 10, "Mehr", "s", 11.5, MUTED))
    write("graph", svg(W, H, "".join(b), [SERIF, SANS, BOLD], f"Beitragsgraph: {total} Beiträge im letzten Jahr"))


def main():
    raw, days = load_contributions()
    st = stats(days)
    fetched = date.fromisoformat(raw["fetched_at"][:10])
    print(f"Karten rendern ({'STATIC' if STATIC else 'animiert'}) …")
    hero()
    tiles()
    activity(st, f"{fetched.day}. {MONTHS_DE[fetched.month - 1]} {fetched.year}")
    repos()
    graph(raw, days)


if __name__ == "__main__":
    main()
