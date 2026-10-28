"""Turn a Markdown CV into HTML (print to PDF), DOCX, and line diffs. No raw HTML ever passes through."""
import difflib
import html
import io
import re

from docx import Document as DocxDocument
from docx.shared import Inches, Pt, RGBColor

# A few built-in, single-column, ATS-safe looks -- font and colour variation only, never a table, column or
# image (those are exactly what breaks an applicant-tracking-system parser, the reason `to_docx` stays plain
# in the first place). "classic" is the original, unchanged look; it stays the default everywhere so existing
# downloads look the same unless a person picks something else.
TEMPLATES = {
    "classic": {"label": "Classic", "font": "Calibri", "heading_font": "Calibri", "accent": "111111", "body_pt": 10.5, "print_pt": 11, "line_height": 1.45, "upper_h2": True},
    "modern": {"label": "Modern", "font": "Calibri", "heading_font": "Georgia", "accent": "2A5DB0", "body_pt": 10.5, "print_pt": 11, "line_height": 1.45, "upper_h2": False},
    "compact": {"label": "Compact", "font": "Arial", "heading_font": "Arial", "accent": "111111", "body_pt": 9.5, "print_pt": 9.5, "line_height": 1.3, "upper_h2": True},
    "serif": {"label": "Serif", "font": "Times New Roman", "heading_font": "Times New Roman", "accent": "111111", "body_pt": 11, "print_pt": 11.5, "line_height": 1.4, "upper_h2": True},
    "forest": {"label": "Forest", "font": "Verdana", "heading_font": "Georgia", "accent": "1F5A44", "body_pt": 10, "print_pt": 10, "line_height": 1.5, "upper_h2": False},
    "slate": {"label": "Slate", "font": "Arial", "heading_font": "Verdana", "accent": "3B4A63", "body_pt": 10.5, "print_pt": 10.5, "line_height": 1.4, "upper_h2": True},
}
DEFAULT_TEMPLATE = "classic"

_BULLET = re.compile(r"^\s*(?:[-*•])\s+(.*)$")
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_INLINE = re.compile(r"\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _blocks(markdown: str):
    """Yield ('h1'|'h2'|'h3'|'li'|'p'|'hr', text) per line, skipping blanks."""
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            yield "hr", ""
            continue
        m = _HEADING.match(line)
        if m:
            yield f"h{len(m.group(1))}", m.group(2).strip()
            continue
        m = _BULLET.match(line)
        if m:
            yield "li", m.group(1).strip()
            continue
        yield "p", line.strip()


def _inline_html(text: str) -> str:
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos : m.start()]))
        if m.group(1) is not None:
            out.append(f"<strong>{html.escape(m.group(1))}</strong>")
        elif m.group(2) is not None:
            out.append(f"<em>{html.escape(m.group(2))}</em>")
        else:
            out.append(f'<a href="{html.escape(m.group(4), quote=True)}" rel="noopener noreferrer">{html.escape(m.group(3))}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def to_html(markdown: str) -> str:
    """Safe HTML body: everything is escaped first; only headings, lists, bold, italic and http(s) links are produced."""
    parts, in_list = [], False
    for kind, text in _blocks(markdown):
        if kind != "li" and in_list:
            parts.append("</ul>")
            in_list = False
        if kind == "li":
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_html(text)}</li>")
        elif kind == "hr":
            parts.append("<hr>")
        elif kind == "p":
            parts.append(f"<p>{_inline_html(text)}</p>")
        else:
            parts.append(f"<{kind}>{_inline_html(text)}</{kind}>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


def _add_runs(paragraph, text: str) -> None:
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos : m.start()])
        if m.group(1) is not None:
            paragraph.add_run(m.group(1)).bold = True
        elif m.group(2) is not None:
            paragraph.add_run(m.group(2)).italic = True
        else:
            paragraph.add_run(f"{m.group(3)} ({m.group(4)})")  # plain text keeps ATS parsers happy
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def to_docx(markdown: str, template: str = DEFAULT_TEMPLATE) -> bytes:
    """A plain, single-column DOCX: real headings and bullets, no tables, images or text boxes (ATS friendly).
    `template` picks a font/colour look from TEMPLATES; an unknown name falls back to the default rather than
    erroring, since this only ever reaches here from a validated choice or a trusted default."""
    style = TEMPLATES.get(template, TEMPLATES[DEFAULT_TEMPLATE])
    accent = RGBColor.from_string(style["accent"])
    doc = DocxDocument()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Inches(0.8)
    section.top_margin = section.bottom_margin = Inches(0.7)
    normal = doc.styles["Normal"]
    normal.font.name = style["font"]
    normal.font.size = Pt(style["body_pt"])
    for kind, text in _blocks(markdown):
        if kind in ("h1", "h2", "h3"):
            heading = doc.add_heading("", level={"h1": 0, "h2": 1, "h3": 2}[kind])
            _add_runs(heading, text)
            if template != DEFAULT_TEMPLATE:  # "classic" keeps the original look untouched (Word's own heading style)
                for run in heading.runs:
                    run.font.name = style["heading_font"]
                    run.font.color.rgb = accent
                    if kind == "h2" and style["upper_h2"]:
                        run.font.all_caps = True  # a display property: the underlying text (and so ATS parsing) is untouched
        elif kind == "li":
            _add_runs(doc.add_paragraph(style="List Bullet"), text)
        elif kind == "p":
            _add_runs(doc.add_paragraph(), text)
    doc.core_properties.author = ""
    doc.core_properties.title = ""
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def line_diff(old: str, new: str) -> list[tuple[str, str]]:
    """[(tag, line)] with tag one of 'same', 'del', 'add' for a side-by-side-free unified view."""
    a, b = old.splitlines(), new.splitlines()
    rows = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            rows += [("same", line) for line in a[i1:i2]]
        else:
            rows += [("del", line) for line in a[i1:i2]]
            rows += [("add", line) for line in b[j1:j2]]
    return rows
