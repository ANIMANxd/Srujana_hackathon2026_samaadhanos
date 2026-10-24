"""Markdown -> PDF for artifacts, rendered with reportlab (pure Python, offline).

The renderer understands only the constructs the templates emit - headings,
paragraphs, blockquotes, bullet lists, pipe tables, horizontal rules - so a
template change never needs a parser change. It reads no network, no clock and
no config: the PDF is a plain rendering of the markdown beside it, produced
offline (architecture.md principle 5).

Two substitutions happen for the PDF only; the markdown keeps the original:

- the rupee sign becomes "Rs ", because reportlab's built-in fonts are
  Western-encoded and cannot draw U+20B9;
- anything else outside that encoding becomes "?", so one odd character in
  engine text can never abort the render.

Any exception escapes to the caller, which returns the markdown with a warning
instead (task B8): the draft is never lost with the PDF.
"""

import html
import re
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HEADING_MARKS = {"# ": "h1", "## ": "h2", "### ": "h3"}
RULE = re.compile(r"^:?-{3,}:?$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_CODE = re.compile(r"`([^`]+)`")


def render_pdf(markdown: str, *, title: str, case_id: str) -> bytes:
    """Render one artifact's markdown to PDF bytes. Raises on failure."""
    text = markdown.replace("\u20b9", "Rs ")
    story = _story(text)
    if not story:
        raise ValueError("nothing to render")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="SamadhaanOS (draft)",
        subject=f"DRAFT artifact for case {case_id} - not legal advice",
        invariant=1,  # byte-stable output for the same draft
    )
    doc.build(
        story, onFirstPage=_page_marker(case_id), onLaterPages=_page_marker(case_id)
    )
    return buffer.getvalue()


def _page_marker(case_id: str):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(
            A4[0] / 2,
            10 * mm,
            f"DRAFT - SamadhaanOS - case {case_id} - not legal advice - page {doc.page}",
        )
        canvas.restoreState()

    return draw


# --------------------------------------------------------------- parsing ----


def _styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=5
    )
    return {
        "h1": ParagraphStyle(
            "h1",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            spaceBefore=11,
            spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": body,
        "quote": ParagraphStyle(
            "quote",
            parent=body,
            fontName="Helvetica-Oblique",
            leftIndent=10,
            textColor=colors.HexColor("#333333"),
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=body, leftIndent=14, bulletIndent=3, spaceAfter=2
        ),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.8, leading=10),
        "cell_head": ParagraphStyle(
            "cell_head", fontName="Helvetica-Bold", fontSize=7.8, leading=10
        ),
    }


def _inline(text: str) -> str:
    """Escape engine text for reportlab's mini-HTML, then restore our markup."""
    escaped = html.escape(text, quote=False)
    with_bold = BOLD.sub(r"<b>\1</b>", escaped)
    return INLINE_CODE.sub(r'<font face="Courier">\1</font>', with_bold)


def _story(markdown: str) -> list:
    """Turn the markdown into reportlab flowables, line by line."""
    styles = _styles()
    flowables: list = []
    paragraph: list[str] = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0

    def flush() -> None:
        if paragraph:
            text = _inline(" ".join(paragraph))
            if text.strip():
                flowables.append(Paragraph(text, styles["body"]))
            paragraph.clear()

    while index < len(lines):
        line = lines[index].strip()

        if not line:
            flush()
            index += 1
            continue

        if line.startswith("|"):
            flush()
            group = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                group.append(lines[index].strip())
                index += 1
            flowables.extend(_table(group, styles))
            continue

        heading_mark = next(
            (mark for mark in HEADING_MARKS if line.startswith(mark)), None
        )
        if heading_mark is not None:
            flush()
            body = line[len(heading_mark) :].strip()
            flowables.append(
                Paragraph(_inline(body), styles[HEADING_MARKS[heading_mark]])
            )
            index += 1
            continue

        if line.startswith(">"):
            flush()
            quoted = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(lines[index].strip().lstrip(">").strip())
                index += 1
            flowables.append(Paragraph(_inline(" ".join(quoted)), styles["quote"]))
            continue

        if line.startswith("---"):
            flush()
            flowables.append(
                HRFlowable(width="100%", thickness=0.6, spaceBefore=4, spaceAfter=6)
            )
            index += 1
            continue

        if line.startswith("- "):
            flush()
            while index < len(lines) and lines[index].strip().startswith("- "):
                item = lines[index].strip()[2:]
                bullet = " "
                if item.startswith("[ ] "):
                    bullet = "[ ]"
                    item = item[4:]
                flowables.append(
                    Paragraph(_inline(item), styles["bullet"], bulletText=bullet)
                )
                index += 1
            continue

        paragraph.append(line)
        index += 1

    flush()
    return flowables


def _table(group: list[str], styles: dict[str, ParagraphStyle]) -> list:
    """One pipe table: header row (bold) over body rows, widths by content."""
    rows: list[list[str]] = []
    for line in group:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(RULE.match(cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return []

    header, body = rows[0], rows[1:]
    width = A4[0] - 36 * mm
    weights = [
        min(
            max(max((len(row[col]) for row in rows if col < len(row)), default=0), 6),
            40,
        )
        for col in range(len(header))
    ]
    total = sum(weights) or 1
    col_widths = [width * w / total for w in weights]

    def cell(text: str, head: bool) -> Paragraph:
        return Paragraph(_inline(text or " "), styles["cell_head" if head else "cell"])

    data = [[cell(text, head=True) for text in header]]
    data += [[cell(text, head=False) for text in row] for row in body]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eceff1")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b0b0b0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 5)]
