"""Renders the dashboard's brand mark (the SVG in command-center.tsx) as PNGs for emails and the Slack app icon."""
import math
import os

from PIL import Image, ImageDraw

ORANGE = "#F76F23"
PATHS = ([(3, 19), (11, 4), (15, 11), (11, 19)], [(13, 19), (17, 11), (21, 19)])  # closed paths, 24-unit viewBox
HERE = os.path.dirname(os.path.abspath(__file__))


def draw_mark(d, scale, ox, oy, width=2.0):
    """Strokes the closed paths like SVG (stroke-linejoin round): a quad per segment plus a disc at every corner."""
    r = width * scale / 2
    for path in PATHS:
        pts = [(ox + x * scale, oy + y * scale) for x, y in path]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            dx, dy = x2 - x1, y2 - y1
            n = math.hypot(dx, dy)
            px, py = -dy / n * r, dx / n * r
            d.polygon([(x1 + px, y1 + py), (x2 + px, y2 + py), (x2 - px, y2 - py), (x1 - px, y1 - py)], fill="white")
        for x, y in pts:
            d.ellipse([x - r, y - r, x + r, y + r], fill="white")


def render(size, rounded, mark_share, path, ss=4):
    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:   # .brand-mark: 8px radius on a 30px box
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 8 / 30, fill=ORANGE)
    else:         # Slack rounds app icons itself, so fill the whole square
        d.rectangle([0, 0, n, n], fill=ORANGE)
    scale = n * mark_share / 24
    off = (n - 24 * scale) / 2
    draw_mark(d, scale, off, off - 0.5 * scale)   # the mark spans y 4..19 of 24: nudge it to the optical centre
    out = img.resize((size, size), Image.LANCZOS)
    (out if rounded else out.convert("RGB")).save(path, optimize=True)


if __name__ == "__main__":
    root = os.path.dirname(HERE)
    render(96, True, 20 / 30, os.path.join(root, "public", "email-logo.png"))      # same proportions as the header icon
    render(1024, False, 0.62, os.path.join(HERE, "venture-studio-slack-icon.png"))
    print("rendered")
