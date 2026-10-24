"""Small charts drawn as inline SVG on the server: no JavaScript, no chart library, no third-party requests.

Every chart carries a <title> and <desc> for screen readers, labels are escaped (they come from the database), and colours
come from CSS classes so the charts follow the light and dark themes. Callers give plain (label, value) rows."""
import math
from itertools import count

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()
_ids = count(1)


def _frame(width, height, title, desc, body, css="so-chart"):
    uid = f"chart{next(_ids)}"
    return mark_safe(
        f'<svg class="{css}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{uid}t {uid}d" xmlns="http://www.w3.org/2000/svg">'
        f'<title id="{uid}t">{escape(title)}</title><desc id="{uid}d">{escape(desc)}</desc>{body}</svg>'
    )


def _short(n) -> str:
    n = int(n)
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 10000 else f"{n:,}"


def hbar_svg(rows, title, desc="", label_width=150, width=640, row=34) -> str:
    """Horizontal bars, biggest first as given. rows: [(label, value)]."""
    rows = [(str(label), max(0, int(value))) for label, value in rows]
    if not rows:
        return ""
    top = max(v for _, v in rows) or 1
    room = width - label_width - 70
    parts = []
    for i, (label, value) in enumerate(rows):
        y = i * row
        bar = max(3, round(room * value / top)) if value else 0
        parts.append(
            f'<text x="{label_width - 10}" y="{y + 21}" text-anchor="end">{escape(label)}</text>'
            f'<rect class="so-bar" x="{label_width}" y="{y + 6}" width="{bar}" height="{row - 12}" rx="5"/>'
            f'<text x="{label_width + bar + 8}" y="{y + 21}" font-weight="700">{escape(_short(value))}</text>'
        )
    return _frame(width, len(rows) * row, title, desc or title, "".join(parts))


def column_svg(rows, title, desc="", width=640, height=190) -> str:
    """Vertical columns over time. rows: [(label, value)] oldest first."""
    rows = [(str(label), max(0, int(value))) for label, value in rows]
    if not rows:
        return ""
    top = max(v for _, v in rows) or 1
    plot_h, base = height - 44, height - 28
    step = width / len(rows)
    bar_w = step * 0.62
    parts = [f'<line class="so-axis" x1="0" y1="{base}" x2="{width}" y2="{base}"/>']
    for i, (label, value) in enumerate(rows):
        h = round(plot_h * value / top) if value else 0
        x = i * step + (step - bar_w) / 2
        parts.append(f'<rect class="so-bar" x="{x:.1f}" y="{base - h}" width="{bar_w:.1f}" height="{h}" rx="4"/>')
        if value == top and value:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{base - h - 6}" text-anchor="middle" font-weight="700">{escape(_short(value))}</text>')
        if i % 2 == 0 or len(rows) <= 8:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 8}" text-anchor="middle">{escape(label)}</text>')
    return _frame(width, height, title, desc or title, "".join(parts))


def donut_svg(rows, title, desc="", size=200) -> str:
    """A ring split into shares. rows: [(label, value)]. Colours so-c1.. in order; the caller draws the legend."""
    rows = [(str(label), max(0, int(value))) for label, value in rows if value]
    total = sum(v for _, v in rows)
    if not total:
        return ""
    r, cx = 70, size / 2
    parts, offset = [], 0.0
    for i, (label, value) in enumerate(rows):
        share = 100 * value / total
        parts.append(
            f'<circle class="so-ring so-ring{(i % 6) + 1}" cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke-width="30" pathLength="100" '
            f'stroke-dasharray="{share:.3f} {100 - share:.3f}" stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 {cx} {cx})"/>'
        )
        offset += share
    parts.append(f'<text x="{cx}" y="{cx - 2}" text-anchor="middle" font-size="26" font-weight="800">{escape(_short(total))}</text>')
    parts.append(f'<text x="{cx}" y="{cx + 18}" text-anchor="middle">openings</text>')
    return _frame(size, size, title, desc or title, "".join(parts), css="so-chart so-donut")


@register.simple_tag
def hbar_chart(rows, title, desc=""):
    return mark_safe(hbar_svg(rows, title, desc))


@register.simple_tag
def column_chart(rows, title, desc=""):
    return mark_safe(column_svg(rows, title, desc))


@register.simple_tag
def donut_chart(rows, title, desc=""):
    return mark_safe(donut_svg(rows, title, desc))
