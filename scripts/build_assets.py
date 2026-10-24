#!/usr/bin/env python3
"""
build_assets.py - rebuild every image used by the profile README.

Edit the CONFIG block below (name, rows, projects, tools), then run:

    python scripts/build_assets.py

It writes:
    assets/profile-banner.svg   terminal banner (vector source, portrait + font embedded)
    assets/profile-banner.png   2x render of the banner, the file README.md shows
    assets/project-*.svg        one clickable card per featured project
    assets/tools.svg            tools & technologies panel

Needs Pillow and fontTools (pip install pillow fonttools brotli).
The PNG render needs Playwright with Chromium (pip install playwright &&
playwright install chromium). Without it the SVGs are still written and the
existing PNG is left alone.

Fonts: JetBrains Mono (SIL Open Font License 1.1). The script looks for the
TTFs in scripts/fonts/ and otherwise downloads the official release once into
~/.cache/enosh-profile-fonts. Only the characters actually used are embedded.
"""
from __future__ import annotations

import base64
import io
import math
import os
import re
import sys
import textwrap
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ==========================================================================
# CONFIG - everything you might want to change lives here
# ==========================================================================
CONFIG = {
    "github_user": "DrEnosh",
    "prompt_user": "enosh@github",
    "prompt_cmd": "cat README.md",
    "name": "Dr. Enosh A Paulson",
    "tagline": "BUILDING AI FOR A HEALTHIER TOMORROW",
    "intro": ("Dentist turned healthcare AI and medical informatics enthusiast, "
              "exploring how AI can solve real-world healthcare problems."),
    "caption": ("BDS", "HEALTHCARE AI"),
    "sections": [
        ("PROFILE", [
            ("ROLE", "Healthcare AI | Medical Informatics | AI & Data Science"),
            ("EDUCATION", "PGDMI, AI & Data Science in Healthcare | IIHMR Bangalore"),
            ("ADDITIONAL EDUCATION", "Online MBA in Healthcare Management | Manipal"),
        ]),
        ("FOCUS", [
            ("FOCUS", "Clinical AI, Hospital AI Implementation, Machine Learning, "
                      "Digital Health, Clinical Decision Support"),
            ("INTERESTS", "Healthcare Data Science, Medical Imaging, Predictive Analytics, "
                          "LLMs, Health-Tech Product Development"),
            ("CURRENTLY", "Learning, building prototypes, exploring healthcare AI "
                          "opportunities, and developing practical technical skills."),
        ]),
    ],
    "next_cmd": "ls ~/projects",
    "projects": [
        {
            "slug": "dentoroute",
            "name": "DentoRoute",
            "subtitle": "Probabilistic Dental Triage & Referral Research Prototype",
            "detail": "Turns model probabilities into conservative referral routes; "
                      "unsure cases go to a human",
            "tags": ["RESEARCH PROTOTYPE", "SYNTHETIC DATA"],
            "repo": "DrEnosh/dentoroute",
        },
        {
            "slug": "panoslice",
            "name": "PanoSlice",
            "subtitle": "Experimental AI-Based Panoramic Dental Image Analysis",
            "detail": "In-browser U-Net tooth segmentation on an OPG with an "
                      "estimated 3D jaw and linked slices",
            "tags": ["EXPERIMENTAL", "IN-BROWSER"],
            "repo": "DrEnosh/panoslice",
        },
        {
            "slug": "forecasting",
            "name": "Healthcare Forecasting",
            "subtitle": "Hospital Admission Forecasting and Time-Series Prediction",
            "detail": "Six-location admission study comparing SARIMA, ETS, Prophet "
                      "and XGBoost",
            "tags": ["TIME SERIES", "SYNTHETIC DATA"],
            "repo": "DrEnosh/hospital-admission-forecasting",
        },
    ],
    "tools": [
        ("LANGUAGES", ["Python", "SQL"]),
        ("ML & AI", ["PyTorch", "Machine Learning", "Deep Learning", "LLMs"]),
        ("APPS & APIS", ["FastAPI", "Streamlit"]),
        ("ANALYTICS", ["Power BI"]),
        ("WORKFLOW", ["Git & GitHub"]),
    ],
}

# Palette
BG = "#0A0E13"
PANEL = "#0F151C"
CYAN = "#22D3EE"
YELLOW = "#FACC15"
TEXT = "#E6EDF3"
MUTED = "#9AA6B2"
DIM = "#5B6672"
PAPER = "#ECEFF1"          # portrait disc
INK = (10, 14, 19)         # portrait dot colour

FAMILY = "ProfileMono"
FALLBACK = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
ADV = 0.6                  # advance width of the monospace font, in em

FONT_URL = "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip"
FONT_FILES = {"regular": "JetBrainsMono-Regular.ttf", "bold": "JetBrainsMono-Bold.ttf"}


# ==========================================================================
# Fonts
# ==========================================================================
def find_fonts() -> dict[str, Path] | None:
    candidates = [ROOT / "scripts" / "fonts", Path.home() / ".cache" / "enosh-profile-fonts"]
    for d in candidates:
        found = {k: d / v for k, v in FONT_FILES.items()}
        if all(p.exists() for p in found.values()):
            return found
    cache = candidates[1]
    try:
        print("downloading JetBrains Mono (one time)...")
        cache.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(FONT_URL, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for v in FONT_FILES.values():
                (cache / v).write_bytes(z.read(f"fonts/ttf/{v}"))
        return {k: cache / v for k, v in FONT_FILES.items()}
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not get JetBrains Mono ({exc}); SVGs will use system monospace")
        return None


def font_css(fonts: dict[str, Path] | None, text: str) -> str:
    """@font-face rules with subset WOFF2 fonts embedded as data URIs."""
    if not fonts:
        return ""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    chars = "".join(sorted(set(text + " ")))
    rules = []
    for weight, key in (("400", "regular"), ("700", "bold")):
        font = TTFont(fonts[key])
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern"]
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(options=opts)
        sub.populate(text=chars)
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        rules.append(f"@font-face{{font-family:'{FAMILY}';font-weight:{weight};"
                     f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "".join(rules)


# ==========================================================================
# SVG helpers
# ==========================================================================
def tw(s: str, size: float, spacing: float = 0.0) -> float:
    """Text width for the monospace font."""
    return len(s) * (size * ADV + spacing)


def wrap(s: str, size: float, width: float) -> list[str]:
    """Wrap to the column width, preferring breaks after ' | ' and ', ' so that
    items like 'Clinical Decision Support' stay on one line."""
    maxc = max(8, int(width // (size * ADV)))
    if len(s) <= maxc:
        return [s]
    atoms = re.split(r"(?<=[|,]) ", s)
    lines: list[str] = []
    cur = ""
    for atom in atoms:
        if len(atom) > maxc:  # one item longer than a line: fall back to word wrap
            if cur:
                lines.append(cur)
            parts = textwrap.wrap(atom, maxc, break_long_words=False)
            lines.extend(parts[:-1])
            cur = parts[-1]
            continue
        cand = f"{cur} {atom}" if cur else atom
        if len(cand) <= maxc:
            cur = cand
        else:
            lines.append(cur)
            cur = atom
    if cur:
        lines.append(cur)
    return lines


def t(x, y, s, size, fill, weight=400, spacing=0.0, anchor="start", opacity=1.0, extra="") -> str:
    attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"'
    if weight != 400:
        attrs += f' font-weight="{weight}"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    if anchor != "start":
        attrs += f' text-anchor="{anchor}"'
    if opacity != 1.0:
        attrs += f' opacity="{opacity}"'
    return f"<text {attrs}{extra}>{escape(s)}</text>"


def spans(x, y, size, parts, weight=400) -> str:
    """One text line made of differently coloured runs: parts = [(text, colour), ...]."""
    inner = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in parts)
    w = f' font-weight="{weight}"' if weight != 400 else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{w} xml:space="preserve">{inner}</text>'


def dots_line(x1, y1, x2, y2, color=CYAN, opacity=0.5, gap=7, width=2.0) -> str:
    """Dotted rule made from round-capped zero-length dashes."""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
            f'stroke-opacity="{opacity}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-dasharray="0.01 {gap}"/>')


def svg_doc(w: int, h: int, body: str, css: str, title: str, desc: str) -> str:
    style = (f"{css}text{{font-family:'{FAMILY}',{FALLBACK};"
             f"font-variant-ligatures:none;}}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{escape(title)}</title>\n<desc id="d">{escape(desc)}</desc>\n'
            f'<!-- Generated by scripts/build_assets.py. Font: JetBrains Mono, SIL OFL 1.1 (subset). -->\n'
            f'<style>{style}</style>\n{body}\n</svg>\n')


def frame(w, h, rx=14) -> str:
    return (f'<rect x="0.75" y="0.75" width="{w - 1.5}" height="{h - 1.5}" rx="{rx}" fill="{BG}" '
            f'stroke="{CYAN}" stroke-opacity="0.55" stroke-width="1.5"/>')


# ==========================================================================
# Portrait
# ==========================================================================
def portrait_data_uri(path: Path, px: int = 820) -> str:
    """Halftone PNG (black dots + alpha) -> tinted, resized, palette PNG data URI."""
    img = Image.open(path).convert("RGBA")
    alpha = img.getchannel("A").resize((px, px), Image.LANCZOS)
    out = Image.new("RGBA", (px, px), INK + (0,))
    out.putalpha(alpha)
    out = out.quantize(colors=48, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ==========================================================================
# Banner
# ==========================================================================
def build_banner(css_for) -> tuple[str, str]:
    c = CONFIG
    W = 1200
    PAD = 28
    TOP = 46                      # title bar height
    LX0, LX1 = PAD, 452           # left column
    RX0, RX1 = 492, W - PAD - 6   # right column
    body: list[str] = []
    all_text: list[str] = []

    def add_text(s):
        all_text.append(s)

    # ---- right column flow (computed first so the height is known) -------
    y = TOP + 104
    right: list[str] = []
    right.append(t(RX0, y, c["name"], 42, TEXT, 700))
    add_text(c["name"])
    y += 38
    right.append(t(RX0, y, c["tagline"], 18, YELLOW, 700, spacing=2.4))
    add_text(c["tagline"])
    y += 40
    for line in wrap(c["intro"], 17, RX1 - RX0):
        right.append(t(RX0, y, line, 17, MUTED))
        add_text(line)
        y += 27
    y += 14

    LABEL_SIZE, VAL_SIZE, LH = 15, 18, 26
    longest = max(len(lbl) for _, rows in c["sections"] for lbl, _ in rows)
    label_w = longest * (LABEL_SIZE * ADV + 0.6)
    vx = RX0 + label_w + 26
    for title, rows in c["sections"]:
        # section header: yellow marker, cyan title, dotted rule to the edge
        head = f"{title}"
        right.append(spans(RX0, y, 15, [("▸ ", YELLOW), (head, CYAN)], weight=700))
        add_text("▸ " + head)
        hx = RX0 + tw("▸ " + head, 15) + 14
        right.append(dots_line(hx, y - 5, RX1, y - 5, opacity=0.45))
        y += 36
        for label, value in rows:
            lines = wrap(value, VAL_SIZE, RX1 - vx)
            right.append(t(RX0, y, label, LABEL_SIZE, CYAN, 700, spacing=0.6, opacity=0.92))
            add_text(label)
            lx = RX0 + tw(label, LABEL_SIZE, 0.6) + 10
            right.append(dots_line(lx, y - 4, vx - 12, y - 4, opacity=0.4, gap=6, width=1.6))
            for i, line in enumerate(lines):
                right.append(t(vx, y + i * LH, line, VAL_SIZE, TEXT))
                add_text(line)
            y += LH * len(lines) + 10
        y += 10

    content_bottom = y
    # closing prompt line
    footer_y = content_bottom + 40
    H = footer_y + 36

    # ---- frame + title bar ----------------------------------------------
    body.append(frame(W, H))
    body.append(f'<path d="M0.75 {TOP} H{W - 0.75}" stroke="{CYAN}" stroke-opacity="0.28" stroke-width="1"/>')
    for i, op in enumerate((0.9, 0.55, 0.3)):
        body.append(f'<circle cx="{PAD + 4 + i * 22}" cy="{TOP / 2}" r="5.5" fill="none" '
                    f'stroke="{CYAN}" stroke-opacity="{op}" stroke-width="1.5"/>')
    bar = f"{c['prompt_user']}: ~/profile"
    body.append(t(W / 2, TOP / 2 + 5, bar, 13, DIM, anchor="middle"))
    body.append(t(W - PAD, TOP / 2 + 5, "README.md", 13, DIM, anchor="end"))
    add_text(bar + "README.md")

    # ---- prompt line + separator -----------------------------------------
    py = TOP + 42
    body.append(spans(PAD + 4, py, 19, [(f"{c['prompt_user']}:~$ ", CYAN), (c["prompt_cmd"], TEXT)], 700))
    add_text(f"{c['prompt_user']}:~$ {c['prompt_cmd']}")
    body.append(dots_line(PAD + 4, TOP + 64, W - PAD - 4, TOP + 64, opacity=0.5))

    # ---- left column: portrait disc ---------------------------------------
    area_top, area_bot = TOP + 80, content_bottom
    cx = (LX0 + LX1) / 2 + 2
    disc_r = 194
    ring = disc_r + 12
    cap_gap = 58                                   # ring -> caption baseline
    group_h = 2 * (ring + 9) + cap_gap
    cy = area_top + (area_bot - area_top - group_h) / 2 + ring + 9
    body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{ring}" fill="none" stroke="{CYAN}" '
                f'stroke-opacity="0.5" stroke-width="1.5"/>')
    body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{ring + 9}" fill="none" stroke="{CYAN}" '
                f'stroke-opacity="0.35" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="0.01 7"/>')
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        out = 16 if ang in (90, 270) else 10
        x1, y1 = cx + math.cos(a) * (ring - 6), cy + math.sin(a) * (ring - 6)
        x2, y2 = cx + math.cos(a) * (ring + out), cy + math.sin(a) * (ring + out)
        body.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                    f'stroke="{CYAN}" stroke-width="1.5" stroke-opacity="0.85"/>')
    body.append(f'<clipPath id="disc"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{disc_r}"/></clipPath>')
    body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{disc_r}" fill="{PAPER}"/>')
    side = disc_r * 2 - 4
    uri = portrait_data_uri(ASSETS / "enosh-halftone.png")
    body.append(f'<image x="{cx - side / 2:.1f}" y="{cy - side / 2:.1f}" width="{side}" height="{side}" '
                f'xlink:href="{uri}" href="{uri}" clip-path="url(#disc)" preserveAspectRatio="xMidYMid meet"/>')
    a_txt, b_txt = c["caption"]
    cap = f"{a_txt}  →  {b_txt}"
    cap_y = cy + ring + cap_gap
    body.append(spans(cx - tw(cap, 15, 2.0) / 2, cap_y, 15,
                      [(a_txt, CYAN), ("  →  ", YELLOW), (b_txt, CYAN)], 700)
                .replace("<text ", '<text letter-spacing="2" ', 1))
    add_text(cap)

    # ---- column divider + right column -------------------------------------
    body.append(f'<line x1="{RX0 - 22}" y1="{area_top}" x2="{RX0 - 22}" y2="{content_bottom - 8}" '
                f'stroke="{CYAN}" stroke-opacity="0.18" stroke-width="1"/>')
    body.extend(right)

    # ---- footer prompt --------------------------------------------------------
    body.append(dots_line(PAD + 4, footer_y - 32, W - PAD - 4, footer_y - 32, opacity=0.5))
    fp = [(f"{c['prompt_user']}:~$ ", CYAN), (c["next_cmd"], TEXT)]
    body.append(spans(PAD + 4, footer_y, 19, fp, 700))
    fx = PAD + 4 + tw(f"{c['prompt_user']}:~$ {c['next_cmd']}", 19) + 6
    body.append(f'<rect x="{fx:.1f}" y="{footer_y - 17}" width="11" height="21" fill="{YELLOW}" opacity="0.9"/>')
    add_text(f"{c['prompt_user']}:~$ {c['next_cmd']}")

    rows_desc = "; ".join(f"{l.title()}: {v}" for _, rows in c["sections"] for l, v in rows)
    desc = (f"Terminal-style profile card. Left: dotted halftone portrait. Right: {c['name']}, "
            f"{c['tagline'].capitalize()}. {c['intro']} {rows_desc}")
    svg = svg_doc(W, int(H), "\n".join(body), css_for("".join(all_text)), f"{c['name']} - profile", desc)
    return svg, desc


# ==========================================================================
# Project cards
# ==========================================================================
def build_project(p: dict, idx: int, css_for) -> str:
    W, H = 1200, 150
    body = [frame(W, H, 12)]
    text = []
    x0 = 34
    body.append(t(x0, 52, f"{idx:02d}", 22, YELLOW, 700))
    nx = x0 + 58
    body.append(t(nx, 52, p["name"], 28, TEXT, 700))
    url = f"github.com/{p['repo']} ↗"
    body.append(t(W - 34, 50, url, 15, DIM, anchor="end"))
    body.append(t(nx, 86, p["subtitle"], 18, CYAN))
    body.append(t(nx, 118, p["detail"], 16, MUTED))
    # tag pills, right aligned on the subtitle row
    tx = W - 34
    for tag in reversed(p["tags"]):
        w = tw(tag, 13, 1.0) + 22
        tx -= w
        body.append(f'<rect x="{tx:.1f}" y="70" width="{w:.1f}" height="24" rx="5" fill="none" '
                    f'stroke="{YELLOW}" stroke-opacity="0.7" stroke-width="1.2"/>')
        body.append(t(tx + w / 2, 87, tag, 13, YELLOW, 700, spacing=1.0, anchor="middle"))
        tx -= 10
        text.append(tag)
    body.append(f'<rect x="{x0 - 16}" y="30" width="3" height="90" rx="1.5" fill="{CYAN}" opacity="0.7"/>')
    text += [f"{idx:02d}", p["name"], url, p["subtitle"], p["detail"]]
    desc = f"{p['name']}: {p['subtitle']}. {p['detail']}. Repository: github.com/{p['repo']}"
    return svg_doc(W, H, "\n".join(body), css_for("".join(text)), p["name"], desc)


# ==========================================================================
# Tools panel
# ==========================================================================
def build_tools(css_for) -> str:
    c = CONFIG
    W = 1200
    PAD = 34
    body, text = [], []
    y = 50
    cmd = [(f"{c['prompt_user']}:~$ ", CYAN), ("ls ~/tools", TEXT), ("   # things I use or explore", DIM)]
    text.append("".join(s for s, _ in cmd))
    head = spans(PAD, y, 18, cmd, 700)
    body.append(head)
    y += 22
    sep_y = y
    y += 46
    lbl_w = max(len(g) for g, _ in c["tools"]) * (15 * ADV + 0.6)
    px0 = PAD + lbl_w + 40
    for group, items in c["tools"]:
        body.append(t(PAD, y, group, 15, CYAN, 700, spacing=0.6, opacity=0.92))
        text.append(group)
        body.append(dots_line(PAD + tw(group, 15, 0.6) + 10, y - 4, px0 - 14, y - 4, opacity=0.4, gap=6, width=1.6))
        x = px0
        for item in items:
            w = tw(item, 17) + 34
            body.append(f'<rect x="{x:.1f}" y="{y - 23}" width="{w:.1f}" height="33" rx="6" fill="{PANEL}" '
                        f'stroke="{CYAN}" stroke-opacity="0.5" stroke-width="1.2"/>')
            body.append(f'<circle cx="{x + 13:.1f}" cy="{y - 6.5:.1f}" r="2.6" fill="{YELLOW}"/>')
            body.append(t(x + 22, y - 0.5, item, 17, TEXT))
            text.append(item)
            x += w + 12
        y += 48
    H = y - 4
    body.insert(0, frame(W, H, 12))
    body.insert(2, dots_line(PAD, sep_y, W - PAD, sep_y, opacity=0.5))
    flat = ", ".join(i for _, items in c["tools"] for i in items)
    desc = f"Tools and technologies I use or explore: {flat}."
    return svg_doc(W, H, "\n".join(body), css_for("".join(text)), "Tools & Technologies", desc)


# ==========================================================================
# PNG render
# ==========================================================================
def render_png(svg_path: Path, png_path: Path, scale: int = 2) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; skipped PNG render")
        return False
    import re
    head = svg_path.read_text(encoding="utf-8")[:400]
    w = int(re.search(r'width="(\d+)"', head).group(1))
    h = int(re.search(r'height="(\d+)"', head).group(1))
    html = (f'<html><body style="margin:0;background:transparent">'
            f'<img id="i" src="{svg_path.resolve().as_uri()}" width="{w}" height="{h}" '
            f'style="display:block"></body></html>')
    tmp = png_path.with_suffix(".render.html")
    tmp.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as pw:
            exe = os.environ.get("CHROMIUM_PATH")
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
            page.goto(tmp.resolve().as_uri())
            page.wait_for_timeout(400)
            page.locator("#i").screenshot(path=str(png_path), omit_background=True)
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)
    # Shrink: 256-colour palette keeps the look and cuts the size a lot.
    img = Image.open(png_path).convert("RGBA")
    img.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(
        png_path, optimize=True)
    return True


def main() -> None:
    if not (ASSETS / "enosh-halftone.png").exists():
        sys.exit("assets/enosh-halftone.png is missing. Create it with scripts/generate_halftone.py first.")
    fonts = find_fonts()
    css_for = lambda s: font_css(fonts, s)  # noqa: E731

    banner, _ = build_banner(css_for)
    (ASSETS / "profile-banner.svg").write_text(banner, encoding="utf-8")
    print("wrote assets/profile-banner.svg")
    for i, p in enumerate(CONFIG["projects"], 1):
        (ASSETS / f"project-{p['slug']}.svg").write_text(build_project(p, i, css_for), encoding="utf-8")
        print(f"wrote assets/project-{p['slug']}.svg")
    (ASSETS / "tools.svg").write_text(build_tools(css_for), encoding="utf-8")
    print("wrote assets/tools.svg")
    if render_png(ASSETS / "profile-banner.svg", ASSETS / "profile-banner.png"):
        print("wrote assets/profile-banner.png")


if __name__ == "__main__":
    main()
