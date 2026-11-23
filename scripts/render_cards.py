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
T_HERO, T_TILES, T_ACTIVITY, T_REPOS, T_GRAPH = 0.0, 1.3, 2.1, 3.4, 4.2

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
.pulse{transform-box:fill-box;transform-origin:50% 50%;animation:pulse 2.2s ease-out infinite}
.wiggle{animation:wiggle 4s ease-in-out infinite}
.static-only{display:none}
@keyframes up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes pop{0%{opacity:0;transform:scale(.4)}100%{opacity:1;transform:scale(1)}}
@keyframes swing{0%{opacity:0;transform:translateY(60px) rotate(-5deg)}55%{opacity:1;transform:translateY(-6px) rotate(1.2deg)}100%{opacity:1;transform:none}}
@keyframes zoom{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:scale(1)}}
@keyframes cell{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
@keyframes draw{from{stroke-dashoffset:var(--len)}to{stroke-dashoffset:0}}
@keyframes pulse{0%{opacity:.7;transform:scale(1)}100%{opacity:0;transform:scale(2.8)}}
@keyframes wiggle{0%,78%,100%{transform:translate(0,0)}83%{transform:translate(4px,-4px)}88%{transform:translate(0,0)}93%{transform:translate(3px,-3px)}}
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
.anim-only,.pulse{display:none}
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

def hero():
    W, H = 880, 330
    t = T_HERO
    has_img = bool(C.PORTRAIT) and (ROOT / C.PORTRAIT).exists()
    tx = 52
    max_text_w = 520 if has_img else 760
    b = [f'<defs><clipPath id="card"><rect width="{W}" height="{H}" rx="20"/></clipPath>'
         f'<linearGradient id="glow" x1="0" y1="0" x2="1" y2="1">'
         f'<stop offset="0" stop-color="{PINE_800}"/><stop offset="1" stop-color="{PINE_950}"/></linearGradient>'
         f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
         f'<circle cx="2" cy="2" r="1.1" fill="{CREAM}" fill-opacity=".06"/></pattern></defs>',
         f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="url(#glow)"/>'
         f'<rect width="{W}" height="{H}" fill="url(#dots)"/>'
         f'<circle cx="{W - 120}" cy="{H + 40}" r="230" fill="{LEAF_SOFT}" fill-opacity=".16"/></g>']

    # Status-Pille mit pulsierendem Punkt
    pill_w = BOLD.width(C.STATUS, 13) + 46
    b.append(f'<g{anim("up", t + .1)}>'
             f'<rect x="{tx}" y="44" width="{pill_w:.0f}" height="30" rx="15" fill="{CREAM}" fill-opacity=".07" '
             f'stroke="{SAGE}" stroke-opacity=".35"/>'
             f'<circle cx="{tx + 18}" cy="59" r="4.5" fill="#7FBE99"{anim("pulse", t + .9)}/>'
             f'<circle cx="{tx + 18}" cy="59" r="4.5" fill="#7FBE99"/>'
             + text(tx + 32, 63.5, C.STATUS, "b", 13, CREAM) + "</g>")

    # Name: Wort für Wort, darüber ein wandernder Glanz (SMIL gradientTransform)
    size, y = 70, 148
    x = tx
    words = C.NAME.split()
    for i, wd in enumerate(words):
        b.append(f'<g{anim("up", t + .25 + i * .14)}>' + text(x, y, wd, "f", size, CREAM) + "</g>")
        x += SERIF.width(wd + " ", size)
    name_w = SERIF.width(C.NAME, size)
    if not STATIC:
        sweep = (f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="{tx}" y1="0" x2="{tx + 180}" y2="0">'
                 f'<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                 f'<stop offset=".5" stop-color="#E9F5EC" stop-opacity=".95"/>'
                 f'<stop offset="1" stop-color="#fff" stop-opacity="0"/>'
                 f'<animateTransform attributeName="gradientTransform" type="translate" '
                 f'values="-200 0;{name_w + 40:.0f} 0;{name_w + 40:.0f} 0" keyTimes="0;.28;1" dur="5s" '
                 f'begin="{t + 1.1:.2f}s" repeatCount="indefinite"/></linearGradient>')
        b.append(f'<defs>{sweep}</defs><g class="anim-only">'
                 + text(tx, y, C.NAME, "f", size, "url(#shine)") + "</g>")

    # Unterstrich zeichnet sich
    ul = 120
    b.append(f'<line x1="{tx}" y1="{y + 22}" x2="{tx + ul}" y2="{y + 22}" stroke="{SAGE}" stroke-width="3" '
             f'stroke-linecap="round" stroke-dasharray="{ul}" '
             + (f'class="draw" style="--len:{ul};animation-delay:{t + .7:.2f}s"' if not STATIC else "")
             + "/>")

    # Rolle + ein Satz über mich
    yy = y + 62
    for line in BOLD.wrap(C.ROLE, 16, max_text_w + 10):
        b.append(f'<g{anim("up", t + .55)}>' + text(tx, yy, line, "b", 16, SAGE) + "</g>")
        yy += 26
    yy += 4
    for i, line in enumerate(SANS.wrap(C.ABOUT, 17, max_text_w, 3)):
        b.append(f'<g{anim("up", t + .7 + i * .06)}>' + text(tx, yy, line, "s", 17, CREAM_DIM) + "</g>")
        yy += 25

    # Porträt (optional)
    if has_img:
        img = base64.b64encode((ROOT / C.PORTRAIT).read_bytes()).decode()
        s, px, py = 236, W - 236 - 52, (H - 236) / 2
        b.append(f'<defs><clipPath id="pic"><rect x="{px}" y="{py}" width="{s}" height="{s}" rx="22"/></clipPath></defs>'
                 f'<g{anim("zoom", t + .45)}>'
                 f'<rect x="{px - 9}" y="{py - 9}" width="{s + 18}" height="{s + 18}" rx="28" fill="none" '
                 f'stroke="{SAGE}" stroke-opacity=".45" stroke-width="1.5"/>'
                 f'<image href="data:image/jpeg;base64,{img}" x="{px}" y="{py}" width="{s}" height="{s}" '
                 f'clip-path="url(#pic)" preserveAspectRatio="xMidYMid slice"/></g>')
    write("hero", svg(W, H, "".join(b), [SERIF, SANS, BOLD], f"{C.NAME}: {C.ROLE}"))


def tiles():
    W, H = 300, 220
    for i, tl in enumerate(C.TILES):
        t = T_TILES + i * .18
        a = tl["accent"]
        b = [f'<defs><clipPath id="c"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18"/></clipPath></defs>',
             f'<g{anim("swing", t)}>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="{PAPER_RAISE}"/>',
             f'<rect x="0" y="0" width="{W}" height="7" fill="{a}" clip-path="url(#c)"/>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="none" stroke="{LINE}" stroke-width="1.5"/>',
             text(26, 46, tl["kicker"], "b", 12, a, ' letter-spacing="2.2"'),
             f'<circle cx="{W - 40}" cy="44" r="7" fill="none" stroke="{a}" stroke-width="2"{anim("pulse", t + 1.0)}/>',
             f'<circle cx="{W - 40}" cy="44" r="7" fill="{a}"/>',
             text(24, 98, tl["title"], "f", 36, INK)]
        y = 130
        for line in SANS.wrap(tl["text"], 15.5, W - 50):
            b.append(text(26, y, line, "s", 15.5, MUTED))
            y += 22
        b.append(f'<line x1="26" x2="{W - 26}" y1="{H - 52}" y2="{H - 52}" stroke="{LINE}"/>')
        link = tl["link"]
        while BOLD.width(link, 13.5) > W - 90:
            link = link[:-2]
        b.append(text(26, H - 25, link, "b", 13.5, a))
        b.append(f'<g{anim("wiggle", t + 2.4)}>' + text(W - 26, H - 23, "↗", "b", 20, a, anchor="end") + "</g>")
        b.append("</g>")
        write(tl["file"], svg(W, H, "".join(b), [SERIF, SANS, BOLD], f'{tl["title"]}: {tl["text"]}'))


def activity(st, fetched: str):
    W, H = 880, 360
    t = T_ACTIVITY
    b = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20" fill="{PAPER}" stroke="{LINE}" stroke-width="1.5"/>',
         f'<g{anim("up", t)}>' + text(44, 62, "Beiträge pro Monat", "f", 30, INK)
         + text(46, 90, f"Die letzten 12 Monate · Stand {fetched}", "s", 14.5, MUTED) + "</g>"]

    # Balken
    months = list(st["months"].items())
    mx = max(v for _, v in months) or 1
    best = max(range(len(months)), key=lambda i: months[i][1])
    x0, base, chart_h, bw, gap = 46, 310, 170, 30, 13
    b.append(f'<line x1="{x0 - 6}" x2="{x0 + 12 * (bw + gap) - gap + 6}" y1="{base}" y2="{base}" stroke="{LINE}" stroke-width="1.5"/>')
    for i, ((yr, mo), v) in enumerate(months):
        x = x0 + i * (bw + gap)
        h = max(4, v / mx * chart_h) if v else 3
        col = LEAF if i == best else SAGE
        b.append(f'<rect x="{x}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="6" fill="{col}"'
                 f'{anim("grow", t + .3 + i * .07)}/>')
        lbl = MONTHS_DE[mo - 1]
        b.append(text(x + bw / 2, base + 22, lbl, "b" if i == best else "s", 12.5,
                      INK if i == best else MUTED, anchor="middle"))
        if i == best:
            by = base - h - 14
            vw = BOLD.width(str(v), 14) + 20
            b.append(f'<g{anim("pop", t + .3 + 12 * .07 + .35)}>'
                     f'<rect x="{x + bw / 2 - vw / 2:.1f}" y="{by - 19:.1f}" width="{vw:.1f}" height="26" rx="13" fill="{PINE_900}"/>'
                     + text(x + bw / 2, by - 1.5, str(v), "b", 14, CREAM, anchor="middle") + "</g>")

    # Kennzahlen rechts
    sx = 590
    b.append(f'<line x1="{sx - 26}" x2="{sx - 26}" y1="44" y2="{H - 44}" stroke="{LINE}"/>')
    bd, bc = st["busiest"]
    items = [
        ("Beiträge im Jahr", st["total"], None),
        ("Aktuelle Serie", st["current"], f"längste: {st['longest']} Tage"),
        ("Aktive Tage", st["active"], f"von {st['ndays']}"),
    ]
    y = 70
    for i, (lbl, val, sub) in enumerate(items):
        tt = t + .5 + i * .15
        b.append(f'<g{anim("up", tt)}>' + text(sx, y, lbl.upper(), "b", 11.5, MUTED, ' letter-spacing="1.6"') + "</g>")
        b.append(f'<g{anim("fade", tt)}>' + counter(sx, y + 38, val, tt + .2, "f", 36, PINE_800)
                 + "</g>")
        if sub:
            vw = SERIF.width(f"{val:,}".replace(",", "'"), 36)
            b.append(f'<g{anim("fade", tt + .9)}>' + text(sx + vw + 12, y + 37, sub, "s", 13.5, MUTED) + "</g>")
        y += 74
    b.append(f'<g{anim("up", t + 1.05)}>'
             + text(sx, y, "AKTIVSTER TAG", "b", 11.5, MUTED, ' letter-spacing="1.6"')
             + text(sx, y + 27, f"{WEEKDAYS_DE[bd.weekday()]}, {bd.day}. {MONTHS_DE[bd.month - 1]} {bd.year}", "b", 17, INK)
             + text(sx, y + 49, f"{bc} Beiträge an einem Tag", "s", 13.5, MUTED) + "</g>")
    write("activity", svg(W, H, "".join(b), [SERIF, SANS, BOLD],
                          f"{st['total']} Beiträge in 12 Monaten, Serie {st['current']} Tage"))


def repos():
    data = json.loads((ROOT / "data" / "repos.json").read_text(encoding="utf-8"))
    W, H = 430, 170
    for i, r in enumerate(data):
        t = T_REPOS + i * .14
        lang = r.get("primaryLanguage") or {"name": "", "color": MUTED}
        name = r["name"]
        size = 23
        while SERIF.width(name, size) > W - 80 and size > 15:
            size -= 1
        b = [f'<g{anim("up", t)}>',
             f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="{PAPER_RAISE}" stroke="{LINE}" stroke-width="1.5"/>',
             # Repo-Symbol
             f'<g transform="translate(24 28)" fill="none" stroke="{LEAF}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
             f'<path d="M3 2.5h10.5v13H5a2 2 0 0 0-2 2z"/><path d="M3 17.5a2 2 0 0 1 2-2h8.5"/></g>',
             text(52, 45, name, "f", size, INK),
             f'<g{anim("wiggle", t + 3)}>' + text(W - 24, 46, "↗", "b", 19, LEAF, anchor="end") + "</g>"]
        y = 80
        desc = "".join(ch for ch in (r.get("description") or "") if ord(ch) in SANS.cmap).strip()
        for line in SANS.wrap(desc, 14.5, W - 48, 2):
            b.append(text(24, y, line, "s", 14.5, MUTED))
            y += 21
        ul = W - 48
        b.append(f'<line x1="24" x2="{W - 24}" y1="{H - 44}" y2="{H - 44}" stroke="{LINE}" stroke-dasharray="{ul}"'
                 + (f' class="draw" style="--len:{ul};animation-delay:{t + .3:.2f}s"' if not STATIC else "") + "/>")
        fx = 24
        if lang["name"]:
            b.append(f'<circle cx="{fx + 6}" cy="{H - 22.5}" r="6" fill="{lang["color"] or MUTED}"/>')
            b.append(text(fx + 18, H - 18, lang["name"], "b", 13, INK))
            fx += 18 + BOLD.width(lang["name"], 13) + 20
        others = [n["name"] for n in r["languages"]["nodes"] if n["name"] != lang["name"]][:2]
        if others:
            b.append(text(fx, H - 18, " · ".join(others), "s", 13, MUTED))
        if r["stargazerCount"]:
            b.append(text(W - 24, H - 18, f"★ {r['stargazerCount']}", "b", 13, INK, anchor="end"))
        b.append("</g>")
        write(f"repo-{name.lower()}", svg(W, H, "".join(b), [SERIF, SANS, BOLD], f"{name}: {r.get('description') or ''}"))
    return data


def graph(raw, days):
    weeks = raw["weeks"]
    cell, gap = 12, 3.2
    step = cell + gap
    gx, gy = 70, 92
    W = int(gx + len(weeks) * step + 36)
    H = 262
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
         f'<g{anim("up", t)}>' + text(44, 54, "Beitragsgraph", "f", 26, INK) + "</g>",
         f'<g{anim("fade", t + .1)}>' + counter(W - 40, 54, total, t + .2, "f", 26, PINE_800, anchor="end")
         + text(W - 44 - SERIF.width(f"{total:,}".replace(",", "'"), 26), 53, "Beiträge im letzten Jahr ", "s", 14, MUTED,
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
