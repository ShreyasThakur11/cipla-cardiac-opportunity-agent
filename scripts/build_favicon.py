"""Generate the site icons.

One mark, drawn once, emitted at every size the browser and the phone home
screen ask for. A cardiac trace in white on the same teal the charts use for a
priority space, so the tab matches the page it opens.

    python scripts/build_favicon.py

Writes into docs/:

    favicon.ico          16, 32 and 48 px, the file the theme links by default
    favicon.svg          vector, used by browsers that prefer it
    apple-touch-icon.png 180 px, iOS home screen
    icon-192.png         Android home screen
    icon-512.png         splash screen and store listing
    site.webmanifest     the name and the icon set, declared once
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PROJECT_ROOT / "docs"

TEAL = (31, 111, 107)  # #1f6f6b, the priority colour in every chart
WHITE = (255, 255, 255)

# The mark is designed on a 64 by 64 grid and scaled up to draw, so the same
# numbers describe both the raster and the vector version.
GRID = 64
CORNER_RADIUS = 12
STROKE = 6

# A single cardiac complex: baseline, small upstroke, tall spike, recovery.
TRACE = [(7, 35), (19, 35), (25, 24), (31, 46), (38, 17), (44, 35), (57, 35)]


def draw_mark(size: int) -> Image.Image:
    """Render the mark at `size` pixels, supersampled for clean edges."""
    scale = max(1, 512 // GRID)
    canvas = GRID * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        [(0, 0), (canvas - 1, canvas - 1)],
        radius=CORNER_RADIUS * scale,
        fill=TEAL,
    )

    points = [(x * scale, y * scale) for x, y in TRACE]
    draw.line(points, fill=WHITE, width=STROKE * scale, joint="curve")

    # Round the two open ends so the trace does not finish on a hard corner.
    radius = (STROKE * scale) // 2
    for x, y in (points[0], points[-1]):
        draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], fill=WHITE)

    return image.resize((size, size), Image.LANCZOS)


def build_svg() -> str:
    points = " ".join(f"{x},{y}" for x, y in TRACE)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" '
        f'role="img" aria-label="Cardiac Opportunity Agent">\n'
        f'  <rect width="{GRID}" height="{GRID}" rx="{CORNER_RADIUS}" '
        f'fill="#1f6f6b"/>\n'
        f'  <polyline points="{points}" fill="none" stroke="#ffffff" '
        f'stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f"</svg>\n"
    )


MANIFEST = {
    "name": "Cardiac Opportunity Agent",
    "short_name": "Cardiac Agent",
    "description": (
        "Ranks the opportunity spaces in the India Cardiac market where Cipla "
        "has a sustainable right to win."
    ),
    # Relative to the manifest itself, so the project path is picked up without
    # having to hard-code the repository name.
    "start_url": ".",
    "scope": ".",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#1f6f6b",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "favicon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    ico_sizes = [16, 32, 48]
    draw_mark(256).save(DOCS / "favicon.ico", sizes=[(s, s) for s in ico_sizes])

    (DOCS / "favicon.svg").write_text(build_svg(), encoding="utf-8")
    draw_mark(180).save(DOCS / "apple-touch-icon.png")
    draw_mark(192).save(DOCS / "icon-192.png")
    draw_mark(512).save(DOCS / "icon-512.png")

    (DOCS / "site.webmanifest").write_text(json.dumps(MANIFEST, indent=2) + "\n", encoding="utf-8")

    for name in (
        "favicon.ico",
        "favicon.svg",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "site.webmanifest",
    ):
        path = DOCS / name
        print(f"  {name:22s} {path.stat().st_size:>7,} bytes")


if __name__ == "__main__":
    main()
