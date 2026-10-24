#!/usr/bin/env python3
"""
generate_halftone.py - turn a portrait photo into a black-and-white halftone.

Dot size follows the brightness of the photo: shadows (hair, beard, suit)
get large dots, highlights (skin, teeth, shirt) get small dots or none.
The result is a real dot pattern, not a grey image with a filter on it.

Only needs Pillow and NumPy.

Examples
--------
# Photo -> transparent PNG with black dots and a soft circular edge
python scripts/generate_halftone.py my-photo.jpg -o assets/enosh-halftone.png

# Same, on white, with finer dots and a vector copy
python scripts/generate_halftone.py my-photo.jpg -o out.png --background white \
    --cell 7 --svg out.svg

# Crop a square around the face first (x, y, width, height in source pixels)
python scripts/generate_halftone.py my-photo.jpg --crop 420,180,1600,1600

# Light dots for dark backgrounds
python scripts/generate_halftone.py my-photo.jpg --invert -o light.png

The input photo is only read, never modified.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


# --------------------------------------------------------------------------
# Loading and tone preparation
# --------------------------------------------------------------------------
def load_luminance(path: str | Path) -> Image.Image:
    """Open an image as 8-bit grayscale. Transparent areas count as white."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white, rgba)
    return img.convert("L")


def square_crop(img: Image.Image, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    """Crop to the given box, or to a centred square if no box is given."""
    if crop:
        x, y, w, h = crop
        return img.crop((x, y, x + w, y + h))
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, (h - side) // 2 - side // 12)  # nudge up a little: faces sit high in portraits
    return img.crop((left, top, left + side, top + side))


def prepare_tone(img: Image.Image, size: int, blur: float = 0.0, cutoff: float = 1.0,
                 gamma: float = 1.0, sharpen: float = 0.6) -> np.ndarray:
    """Resize to the working size and return luminance in [0, 1] (1 = white).

    blur    - Gaussian blur (in working pixels) applied first. Use it when the
              input is already a halftone so its old dots melt into tone.
    cutoff  - percent of darkest/brightest pixels clipped by autocontrast.
    gamma   - >1 darkens midtones, <1 lightens them.
    sharpen - unsharp-mask strength; keeps glasses frames and hair edges crisp.
    """
    img = img.resize((size, size), Image.LANCZOS)
    if blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img = ImageOps.autocontrast(img, cutoff=cutoff)
    if sharpen > 0:
        img = img.filter(ImageFilter.UnsharpMask(radius=max(2, size // 300),
                                                 percent=int(sharpen * 150), threshold=2))
    lum = np.asarray(img, dtype=np.float32) / 255.0
    if gamma != 1.0:
        lum = np.power(lum, gamma)
    return lum


# --------------------------------------------------------------------------
# Halftone geometry
# --------------------------------------------------------------------------
def _bilinear(arr: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = arr.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    a = arr[y0, x0] * (1 - fx) + arr[y0, x0 + 1] * fx
    b = arr[y0 + 1, x0] * (1 - fx) + arr[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def compute_dots(lum: np.ndarray, cell: float, angle: float = 45.0, gain: float = 1.15,
                 highlight: float = 0.08, min_radius: float = 0.07, invert: bool = False,
                 mask: str = "circle", mask_radius: float = 0.49, fade: float = 0.16
                 ) -> list[tuple[float, float, float]]:
    """Return dots as (x, y, r) in the pixel space of `lum`.

    Each grid cell gets one dot whose area tracks the cell's darkness.
    highlight - darkness below this is treated as paper white (keeps teeth
                and skin highlights clean).
    mask      - "circle" fades dots out towards a circular edge; "none" keeps
                the full square.
    """
    h, w = lum.shape
    # Average tone over roughly one cell so each dot reflects its area, not one pixel.
    box = max(1, int(round(cell * 0.6)))
    smooth = np.asarray(
        Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(box / 2)),
        dtype=np.float32) / 255.0

    cx, cy = w / 2.0, h / 2.0
    half_diag = math.hypot(w, h) / 2.0
    n = int(math.ceil(half_diag / cell)) + 1
    idx = np.arange(-n, n + 1, dtype=np.float32) * cell
    gx, gy = np.meshgrid(idx, idx)
    t = math.radians(angle)
    x = cx + gx * math.cos(t) - gy * math.sin(t)
    y = cy + gx * math.sin(t) + gy * math.cos(t)
    keep = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    x, y = x[keep], y[keep]

    tone = _bilinear(smooth, x, y)
    dark = tone if invert else 1.0 - tone
    dark = np.clip((dark - highlight) / (1.0 - highlight), 0.0, 1.0)

    if mask == "circle":
        rad = min(w, h) * mask_radius
        d = np.hypot(x - cx, y - cy) / rad
        inner = 1.0 - fade
        wgt = np.clip((1.0 - d) / max(fade, 1e-6), 0.0, 1.0)
        wgt = wgt * wgt * (3 - 2 * wgt)  # smoothstep
        wgt[d <= inner] = 1.0
        dark = dark * wgt

    r = cell * np.sqrt(dark / math.pi) * gain
    r = np.minimum(r, cell * 0.72)
    ok = r >= cell * min_radius
    return list(zip(x[ok].tolist(), y[ok].tolist(), r[ok].tolist()))


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def render_png(dots, size: int, work_size: int, background: str = "transparent",
               dot_color=(0, 0, 0), supersample: int = 3) -> Image.Image:
    """Rasterise dots with supersampling so edges are smooth."""
    s = size * supersample / work_size
    canvas = Image.new("L", (size * supersample, size * supersample), 0)
    draw = ImageDraw.Draw(canvas)
    for x, y, r in dots:
        X, Y, R = x * s, y * s, r * s
        draw.ellipse((X - R, Y - R, X + R, Y + R), fill=255)
    alpha = canvas.resize((size, size), Image.LANCZOS)
    if background == "white":
        bg = Image.new("RGB", (size, size), (255, 255, 255))
        fg = Image.new("RGB", (size, size), dot_color)
        return Image.composite(fg, bg, alpha)
    out = Image.new("RGBA", (size, size), dot_color + (0,))
    out.putalpha(alpha)
    return out


def write_svg(dots, path: str | Path, work_size: int, size: int, color: str = "#000000",
              background: str | None = None) -> None:
    """Write the dots as a static SVG (one path, no scripts, valid XML)."""
    s = size / work_size
    parts = []
    for x, y, r in dots:
        X, Y, R = x * s, y * s, r * s
        parts.append(f"M{X - R:.1f} {Y:.1f}a{R:.2f} {R:.2f} 0 1 0 {2 * R:.2f} 0"
                     f"a{R:.2f} {R:.2f} 0 1 0 {-2 * R:.2f} 0")
    bg = f'<rect width="{size}" height="{size}" fill="{background}"/>' if background else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
           f'viewBox="0 0 {size} {size}">{bg}<path fill="{color}" d="{"".join(parts)}"/></svg>\n')
    Path(path).write_text(svg, encoding="utf-8")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def main() -> None:
    p = argparse.ArgumentParser(description="Convert a portrait photo into a halftone dot portrait.")
    p.add_argument("input", help="source photo (jpg/png); it is never modified")
    p.add_argument("-o", "--output", default="assets/enosh-halftone.png", help="output PNG path")
    p.add_argument("--size", type=int, default=1254, help="output width/height in px (square)")
    p.add_argument("--crop", help="x,y,w,h crop box in source pixels (default: centred square)")
    p.add_argument("--cell", type=float, default=8.0,
                   help="dot spacing in output px; smaller = finer detail (default 8)")
    p.add_argument("--angle", type=float, default=45.0, help="screen angle in degrees")
    p.add_argument("--blur", type=float, default=0.0,
                   help="pre-blur in output px; use ~0.5*old dot spacing when re-screening a halftone")
    p.add_argument("--cutoff", type=float, default=1.0, help="autocontrast clip percent")
    p.add_argument("--gamma", type=float, default=1.0, help=">1 darker midtones, <1 lighter")
    p.add_argument("--sharpen", type=float, default=0.6, help="edge sharpening strength (0 = off)")
    p.add_argument("--gain", type=float, default=1.15, help="dot size multiplier")
    p.add_argument("--highlight", type=float, default=0.08,
                   help="darkness treated as white; raise to keep teeth/skin cleaner")
    p.add_argument("--mask", choices=["circle", "none"], default="circle")
    p.add_argument("--fade", type=float, default=0.16, help="soft-edge width as a fraction of the radius")
    p.add_argument("--background", choices=["transparent", "white"], default="transparent")
    p.add_argument("--dot-color", default="#000000")
    p.add_argument("--invert", action="store_true", help="dots for light areas (use on dark backgrounds)")
    p.add_argument("--svg", help="also write a vector SVG copy to this path")
    a = p.parse_args()

    src = Path(a.input)
    out = Path(a.output)
    if src.resolve() == out.resolve():
        raise SystemExit("Refusing to overwrite the source photo. Pick a different --output.")

    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    img = square_crop(load_luminance(src), crop)  # type: ignore[arg-type]

    work = a.size  # work at output resolution; cell and blur are in output px
    lum = prepare_tone(img, work, blur=a.blur, cutoff=a.cutoff, gamma=a.gamma, sharpen=a.sharpen)
    dots = compute_dots(lum, a.cell, angle=a.angle, gain=a.gain, highlight=a.highlight,
                        invert=a.invert, mask=a.mask, fade=a.fade)

    color = _hex_to_rgb(a.dot_color)
    if a.invert and a.dot_color == "#000000":
        color = (255, 255, 255)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_png(dots, a.size, work, a.background, color).save(out, optimize=True)
    print(f"wrote {out}  ({len(dots)} dots, {a.size}x{a.size})")

    if a.svg:
        write_svg(dots, a.svg, work, a.size, "#%02x%02x%02x" % color,
                  "#ffffff" if a.background == "white" else None)
        print(f"wrote {a.svg}")


if __name__ == "__main__":
    main()
