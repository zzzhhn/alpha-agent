"""
Reusable wireframe generation toolkit for engineering blueprints.
Provides helper functions for creating professional dark-theme UI mockups.

Usage:
    from wireframe_base import WireframeCanvas, Theme

    canvas = WireframeCanvas(1800, 1000, title="Module 1: Dashboard")
    canvas.draw_card((66, 56, 500, 300), "Service Health")
    canvas.draw_sparkline(80, 200, 400, 60, color=Theme.GREEN)
    canvas.save("01_dashboard.png")
"""
import os
from PIL import Image, ImageDraw, ImageFont


class Theme:
    """Dark theme color palette — consistent across all wireframes."""
    BG = "#0F1117"
    CARD_BG = "#1A1D27"
    CARD_BORDER = "#2A2D3A"
    HEADER_BG = "#151821"
    SIDEBAR_BG = "#111318"

    ACCENT = "#2E75B6"
    GREEN = "#22C55E"
    RED = "#EF4444"
    YELLOW = "#F59E0B"
    PURPLE = "#8B5CF6"
    PINK = "#EC4899"
    ORANGE = "#F97316"
    CYAN = "#06B6D4"
    INDIGO = "#4F46E5"

    TEXT = "#E5E7EB"
    TEXT_DIM = "#9CA3AF"

    CHART_LINE = "#3B82F6"
    CHART_FILL = "#1E3A5F"

    # Module accent colors (up to 10 modules)
    MODULE_COLORS = [ACCENT, GREEN, YELLOW, PURPLE, PINK, ORANGE, CYAN, INDIGO, RED, "#65A30D"]


def get_font(size=14, bold=False):
    """Load a system font with fallback."""
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class WireframeCanvas:
    """A high-level wireframe drawing surface with built-in UI primitives."""

    def __init__(self, width=1800, height=1000, title="", subtitle="",
                 sidebar_items=None, active_sidebar=0, show_sidebar=True):
        self.W = width
        self.H = height
        self.img = Image.new("RGB", (width, height), Theme.BG)
        self.d = ImageDraw.Draw(self.img)
        self.SX = 66 if show_sidebar else 16  # content start x

        if show_sidebar and sidebar_items:
            self._draw_sidebar(sidebar_items, active_sidebar)
        if title:
            self._draw_header(title, subtitle)

    def _draw_sidebar(self, items, active_index):
        d = self.d
        d.rectangle([0, 0, 50, self.H], fill=Theme.SIDEBAR_BG)
        d.line([(50, 0), (50, self.H)], fill=Theme.CARD_BORDER, width=1)
        for i, label in enumerate(items):
            color = Theme.MODULE_COLORS[i % len(Theme.MODULE_COLORS)]
            yy = 60 + i * 52
            if i == active_index:
                d.rectangle([0, yy - 4, 50, yy + 36], fill="#1E2538")
                d.rectangle([0, yy - 4, 3, yy + 36], fill=Theme.ACCENT)
            font = get_font(9)
            tw = d.textlength(label, font=font)
            d.text((25 - tw / 2, yy + 8), label,
                   fill=color if i == active_index else Theme.TEXT_DIM, font=font)

    def _draw_header(self, title, subtitle=""):
        d = self.d
        d.rectangle([50 if self.SX > 16 else 0, 0, self.W, 44], fill=Theme.HEADER_BG)
        d.line([(50 if self.SX > 16 else 0, 44), (self.W, 44)], fill=Theme.CARD_BORDER, width=1)
        font = get_font(15, bold=True)
        d.text((self.SX, 12), title, fill=Theme.TEXT, font=font)
        if subtitle:
            sfont = get_font(11)
            x = self.SX + d.textlength(title, font=font) + 16
            d.text((x, 16), subtitle, fill=Theme.TEXT_DIM, font=sfont)

    # ── Primitives ──

    def draw_card(self, xy, title=None, border_color=None):
        """Draw a card container with optional title bar."""
        x1, y1, x2, y2 = xy
        bc = border_color or Theme.CARD_BORDER
        self.d.rounded_rectangle(xy, radius=6, fill=Theme.CARD_BG, outline=bc)
        if title:
            font = get_font(13, bold=True)
            self.d.text((x1 + 12, y1 + 10), title, fill=Theme.TEXT_DIM, font=font)
            self.d.line([(x1 + 1, y1 + 32), (x2 - 1, y1 + 32)], fill=Theme.CARD_BORDER, width=1)

    def draw_status_dot(self, x, y, color=None, size=8):
        c = color or Theme.GREEN
        self.d.ellipse([x, y, x + size, y + size], fill=c)

    def draw_bar(self, x, y, w, h, fill_pct, color=None):
        """Horizontal progress/gauge bar."""
        c = color or Theme.ACCENT
        self.d.rectangle([x, y, x + w, y + h], fill="#1E2130")
        self.d.rectangle([x, y, x + int(w * min(fill_pct, 1.0)), y + h], fill=c)

    def draw_sparkline(self, x, y, w, h, color=None, points=20, seed=42):
        """Mini trend line chart."""
        import random
        rng = random.Random(seed)
        c = color or Theme.CHART_LINE
        vals = [rng.random() for _ in range(points)]
        for i in range(1, len(vals)):
            vals[i] = vals[i] * 0.4 + vals[i - 1] * 0.6
        mn, mx = min(vals), max(vals)
        span = mx - mn or 1
        coords = []
        for i, v in enumerate(vals):
            px = x + (i / (points - 1)) * w
            py = y + h - ((v - mn) / span) * h
            coords.append((px, py))
        for i in range(len(coords) - 1):
            self.d.line([coords[i], coords[i + 1]], fill=c, width=2)

    def draw_badge(self, x, y, text, color=None, w=None):
        """Small colored badge/tag."""
        c = color or Theme.ACCENT
        font = get_font(9, bold=True)
        tw = w or (self.d.textlength(text, font=font) + 16)
        self.d.rounded_rectangle([x, y, x + tw, y + 20], radius=3, fill=c)
        self.d.text((x + 8, y + 3), text, fill="white", font=font)

    def draw_kpi(self, x, y, label, value, color=None):
        """KPI metric display (label + large value)."""
        c = color or Theme.TEXT
        self.d.text((x, y), label, fill=Theme.TEXT_DIM, font=get_font(10))
        self.d.text((x, y + 18), str(value), fill=c, font=get_font(16, bold=True))

    def draw_table_row(self, x, y, cells, col_widths, header=False):
        """Draw one row of a simple table."""
        font = get_font(10, bold=header)
        color = Theme.ACCENT if header else Theme.TEXT_DIM
        cx = x
        for cell, cw in zip(cells, col_widths):
            self.d.text((cx, y), str(cell), fill=color, font=font)
            cx += cw

    def text(self, x, y, content, color=None, size=11, bold=False):
        """Convenience text drawing."""
        self.d.text((x, y), content, fill=color or Theme.TEXT_DIM, font=get_font(size, bold))

    def footer(self, text):
        """Bottom annotation bar."""
        self.d.text((self.SX, self.H - 20), text, fill=Theme.TEXT_DIM, font=get_font(9))

    def page_break_line(self, y):
        """Horizontal divider."""
        self.d.line([(self.SX, y), (self.W - 16, y)], fill=Theme.CARD_BORDER, width=1)

    # ── Output ──

    def save(self, path):
        """Save the wireframe as PNG."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.img.save(path, "PNG")
        print(f"  ✓ {os.path.basename(path)} ({os.path.getsize(path) // 1024} KB)")
