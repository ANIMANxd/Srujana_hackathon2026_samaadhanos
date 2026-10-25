#!/usr/bin/env python3
"""Generate the synthetic sample-document corpus in `sample_data/`.

What this is
------------
A deterministic, offline generator for the paper a micro or small supplier in
India actually holds: a purchase order, a GST tax invoice, a delivery challan,
a goods receipt note, an Udyam registration data extract, GST return extracts,
a written objection, a remittance advice, and WhatsApp chat exports. Each
document is written twice from one content model: an A4 PDF (real bytes, real
text layer) and a `.txt` twin the existing `/extract-evidence` endpoint can
read.

What this is not
----------------
Not law, not a real document, not a government form. Golden rules 9, 11 and 17
of AGENTS.md apply to every page:

* every party name ends in "(synthetic)" or "(fictional)";
* every GSTIN uses the "29SYN..." placeholder shape, which is not a valid
  GSTIN (wrong length and a "SYN" PAN), so it cannot belong to anyone;
* every page carries a SPECIMEN banner, a diagonal SPECIMEN watermark and a
  footer saying the document is fictional;
* there is **no** Udyam certificate, e-way bill, MSEFC form or notice: those
  are issued by authorities or portals, so faking one would break golden rule
  9. The Udyam page is a data extract, clearly labelled "NOT A CERTIFICATE".

How to run
----------
    python sample_data/generate_samples.py

Requires `reportlab` (already a runtime dependency for `/generate-artifact`);
PyMuPDF and Pillow are used only by this development script, and are recorded
in `docs/dependencies.md`.

The digital PDFs are byte-stable (`rl_config.invariant`). The degraded scans
are rebuilt from rendering, so their bytes may change between runs of a
different Pillow or PyMuPDF version.
"""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape

# Set before any reportlab document is built: fixed ID and timestamps, so a
# regenerated digital PDF is byte-identical.
from reportlab import rl_config

rl_config.invariant = 1

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_RIGHT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------- furniture --

PAGE_W, PAGE_H = A4
LEFT = RIGHT = 18 * mm
TOP = 26 * mm
BOTTOM = 22 * mm
FRAME_W = PAGE_W - LEFT - RIGHT

INK = colors.HexColor("#161616")
MUTED = colors.HexColor("#5c5c5c")
RULE = colors.HexColor("#b3b3b3")
WASH = colors.HexColor("#f2f1ed")
BANNER = colors.HexColor("#7a1f1f")

BANNER_TEXT = "SPECIMEN - SYNTHETIC DATA - NOT A REAL DOCUMENT"
FOOTER = (
    "SamadhaanOS sample corpus - all parties, GSTINs and amounts are fictional. "
    "Not a tax, legal or government document."
)
DISCLAIMER = (
    "Generated for the SamadhaanOS sample corpus - every party, GSTIN and amount "
    "is fictional."
)

STYLES: dict[str, ParagraphStyle] = {
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=8.8, leading=11.6, textColor=INK
    ),
    "small": ParagraphStyle(
        "small", fontName="Helvetica", fontSize=7.6, leading=9.8, textColor=MUTED
    ),
    "note": ParagraphStyle(
        "note", fontName="Helvetica-Oblique", fontSize=7.6, leading=9.8, textColor=MUTED
    ),
    "bold": ParagraphStyle(
        "bold", fontName="Helvetica-Bold", fontSize=8.8, leading=11.6, textColor=INK
    ),
    "h1": ParagraphStyle(
        "h1", fontName="Helvetica-Bold", fontSize=14.5, leading=17, textColor=INK
    ),
    "title": ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=INK,
        alignment=TA_RIGHT,
    ),
    "title_sub": ParagraphStyle(
        "title_sub",
        fontName="Helvetica",
        fontSize=7.4,
        leading=9.4,
        textColor=MUTED,
        alignment=TA_RIGHT,
    ),
    "cell": ParagraphStyle(
        "cell", fontName="Helvetica", fontSize=8.0, leading=10.2, textColor=INK
    ),
    "cell_r": ParagraphStyle(
        "cell_r",
        fontName="Helvetica",
        fontSize=8.0,
        leading=10.2,
        textColor=INK,
        alignment=TA_RIGHT,
    ),
    "head": ParagraphStyle(
        "head",
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=9.8,
        textColor=colors.white,
    ),
    "head_r": ParagraphStyle(
        "head_r",
        fontName="Helvetica-Bold",
        fontSize=7.8,
        leading=9.8,
        textColor=colors.white,
        alignment=TA_RIGHT,
    ),
}

# ---------------------------------------------------------------- amounts ----


def D(value: str | int | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def inr(value: Decimal) -> str:
    """Indian digit grouping with two decimals: 1250000 -> 12,50,000.00."""
    q = D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"{sign}{whole}.{frac}"


def pct(value: Decimal) -> str:
    """A tidy percentage label: Decimal('9.00') -> '9', Decimal('2.50') -> '2.5'."""
    text = format(D(value).normalize(), "f")
    return "0" if text == "0" else text


_ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve "
    "Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_TENS = ("Zero Ten Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety").split()


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def words_inr(value: Decimal) -> str:
    """Whole-rupee Indian words. The corpus uses whole-rupee totals only."""
    n = int(D(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if n == 0:
        return "Rupees Zero Only"
    crore, rem = divmod(n, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rem = divmod(rem, 1_000)
    hundred, rem = divmod(rem, 100)
    parts: list[str] = []
    if crore:
        parts.append(f"{_two(crore)} Crore")
    if lakh:
        parts.append(f"{_two(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two(thousand)} Thousand")
    if hundred:
        parts.append(f"{_ONES[hundred]} Hundred")
    if rem:
        parts.append(_two(rem))
    return "Rupees " + " ".join(parts) + " Only"


# ------------------------------------------------------------ content model --


@dataclass(frozen=True)
class P:
    text: str
    style: str = "body"
    space: float = 3.0


@dataclass(frozen=True)
class KVT:
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class T:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    fractions: tuple[float, ...]
    aligns: tuple[str, ...] = ()
    size: float = 8.0
    repeat: bool = True


@dataclass(frozen=True)
class Totals:
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Rule:
    before: float = 2.0
    after: float = 8.0


@dataclass(frozen=True)
class Gap:
    h: float = 6.0


@dataclass(frozen=True)
class Letterhead:
    company: str
    lines: tuple[str, ...]
    title: str
    subtitle: str


@dataclass(frozen=True)
class Note:
    text: str


Block = P | KVT | T | Totals | Rule | Gap | Letterhead | Note | PageBreak


@dataclass
class Sheet:
    title: str
    blocks: list[Block]

    def text(self) -> str:
        lines = [BANNER_TEXT, DISCLAIMER, ""]
        for block in self.blocks:
            if isinstance(block, P):
                lines.append(block.text)
                if block.space >= 8:
                    lines.append("")
            elif isinstance(block, KVT):
                lines.extend(f"{k}: {v}" for k, v in block.rows)
            elif isinstance(block, T):
                lines.append("  ".join(block.header))
                lines.extend("  ".join(row) for row in block.rows)
            elif isinstance(block, Totals):
                lines.extend(f"{k}: {v}" for k, v in block.rows if k)
            elif isinstance(block, Letterhead):
                lines.append(block.company)
                lines.append(block.title)
                lines.append(block.subtitle)
                lines.extend(block.lines)
            elif isinstance(block, Note):
                lines.append(block.text)
            elif isinstance(block, Gap):
                lines.append("")
            elif isinstance(block, Rule):
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


# -------------------------------------------------------------- PDF render --


class _NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs) -> None:
        rl_canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved: list[dict] = []

    def showPage(self) -> None:  # noqa: N802 - reportlab's spelling
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._footer(total)
            rl_canvas.Canvas.showPage(self)
        rl_canvas.Canvas.save(self)

    def _footer(self, total: int) -> None:
        self.saveState()
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(LEFT, 17 * mm, PAGE_W - RIGHT, 17 * mm)
        self.setFillColor(MUTED)
        self.setFont("Helvetica", 6.6)
        self.drawString(LEFT, 12.5 * mm, FOOTER)
        self.drawRightString(
            PAGE_W - RIGHT, 12.5 * mm, f"Page {self._pageNumber} of {total}"
        )
        self.restoreState()


def _decorate(canvas, doc) -> None:  # noqa: ARG001 - reportlab callback
    canvas.saveState()
    stamp = _watermark_png()
    width, height = 820, 620
    canvas.drawImage(
        str(stamp),
        PAGE_W / 2 - width / 2,
        PAGE_H / 2 - height / 2,
        width=width,
        height=height,
        mask="auto",
    )
    canvas.restoreState()

    canvas.saveState()
    canvas.setFillColor(BANNER)
    canvas.rect(0, PAGE_H - 15 * mm, PAGE_W, 15 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 9.4 * mm, BANNER_TEXT)
    canvas.restoreState()


def _watermark_png() -> Path:
    """A faint raster watermark, so the PDF text layer carries no noise.

    Drawing the word as text would put "SPECIMEN" lines into the page's text
    layer, ahead of the real content, and every text extractor would have to
    filter them out. An image cannot leak into the text layer.
    """
    import tempfile

    from PIL import Image, ImageDraw, ImageFont

    path = Path(tempfile.gettempdir()) / "samadhaan-specimen-watermark.png"
    if path.is_file():
        return path
    image = Image.new("RGBA", (820, 620), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=74)
    except TypeError:  # Pillow < 10.1 has no size argument
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), "SPECIMEN", font=font)
    draw.text(
        ((820 - (box[2] - box[0])) / 2, (620 - (box[3] - box[1])) / 2),
        "SPECIMEN",
        font=font,
        fill=(90, 90, 90, 30),
    )
    image = image.rotate(30, resample=Image.BICUBIC, expand=False)
    image.save(path)
    return path


def _letterhead_table(block: Letterhead) -> Table:
    left = [Paragraph(escape(block.company), STYLES["h1"])]
    left += [Paragraph(escape(line), STYLES["small"]) for line in block.lines]
    right = [
        Paragraph(escape(block.title), STYLES["title"]),
        Paragraph(escape(block.subtitle), STYLES["title_sub"]),
    ]
    table = Table(
        [[left, right]],
        colWidths=[FRAME_W * 0.62, FRAME_W * 0.38],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _kvt(block: KVT) -> Table:
    rows = [
        [
            Paragraph(escape(label), STYLES["small"]),
            Paragraph(escape(value), STYLES["body"]),
        ]
        for label, value in block.rows
    ]
    table = Table(rows, colWidths=[FRAME_W * 0.30, FRAME_W * 0.70])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e0da")),
            ]
        )
    )
    return table


def _table(block: T) -> Table:
    head_style = STYLES["head"]
    head_r = STYLES["head_r"]
    cell = ParagraphStyle("c", parent=STYLES["cell"], fontSize=block.size)
    cell_r = ParagraphStyle("cr", parent=STYLES["cell_r"], fontSize=block.size)
    data = []
    header = []
    for index, name in enumerate(block.header):
        style = head_r if block.aligns and block.aligns[index] == "R" else head_style
        header.append(Paragraph(escape(name), style))
    data.append(header)
    for row in block.rows:
        cells = []
        for index, value in enumerate(row):
            style = cell_r if block.aligns and block.aligns[index] == "R" else cell
            cells.append(Paragraph(escape(value), style))
        data.append(cells)

    table = Table(
        data,
        colWidths=[f * FRAME_W for f in block.fractions],
        repeatRows=1 if block.repeat and block.header else 0,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), WASH))
    table.setStyle(TableStyle(style))
    return table


def _totals(block: Totals) -> Table:
    rows = [
        [
            Paragraph(escape(label), STYLES["cell_r"]),
            Paragraph(escape(value), STYLES["cell_r"]),
        ]
        for label, value in block.rows
    ]
    table = Table(rows, colWidths=[FRAME_W * 0.34, FRAME_W * 0.20], hAlign="RIGHT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEABOVE", (0, 0), (-1, len(rows) - 1), 0.8, INK),
        ("FONTNAME", (0, len(rows) - 1), (-1, len(rows) - 1), "Helvetica-Bold"),
    ]
    table.setStyle(TableStyle(style))
    return table


def _story(sheet: Sheet) -> list:
    flow: list = []
    for block in sheet.blocks:
        if isinstance(block, P):
            flow.append(Paragraph(escape(block.text), STYLES[block.style]))
            flow.append(Spacer(1, block.space))
        elif isinstance(block, Letterhead):
            flow.append(_letterhead_table(block))
            flow.append(Spacer(1, 10))
        elif isinstance(block, KVT):
            flow.append(_kvt(block))
            flow.append(Spacer(1, 6))
        elif isinstance(block, T):
            flow.append(_table(block))
            flow.append(Spacer(1, 8))
        elif isinstance(block, Totals):
            flow.append(_totals(block))
            flow.append(Spacer(1, 8))
        elif isinstance(block, Rule):
            flow.append(
                HRFlowable(
                    width="100%",
                    thickness=0.8,
                    color=RULE,
                    spaceBefore=block.before,
                    spaceAfter=block.after,
                )
            )
        elif isinstance(block, Gap):
            flow.append(Spacer(1, block.h))
        elif isinstance(block, Note):
            flow.append(Paragraph(escape(block.text), STYLES["note"]))
            flow.append(Spacer(1, 4))
        elif isinstance(block, PageBreak):
            flow.append(PageBreak())
    return flow


def render_pdf(sheet: Sheet, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title=sheet.title,
        author="SamadhaanOS sample corpus (synthetic)",
        subject="Synthetic specimen - not a real document",
        creator="sample_data/generate_samples.py",
    )
    frame = Frame(
        LEFT,
        BOTTOM,
        FRAME_W,
        PAGE_H - TOP - BOTTOM,
        id="body",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_decorate)])
    doc.build(_story(sheet), canvasmaker=_NumberedCanvas)
    return doc.page


# ---------------------------------------------------------------- parties ----


@dataclass(frozen=True)
class Party:
    name: str
    gstin: str
    address: tuple[str, ...]
    udyam: str
    enterprise: str
    nic: str
    registered_on: str
    investment: str
    turnover: str
    email: str = "accounts@example.invalid"


SUPPLIES = Party(
    name="Sample Supplies Pvt Ltd (synthetic)",
    gstin="29SYN000000010Z1",
    address=(
        "Plot 14, Fictional Industrial Estate",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-000000000",
    enterprise="Small",
    nic="25990",
    registered_on="01/06/2023",
    investment="Rs 1,20,00,000",
    turnover="Rs 8,00,00,000",
)

MICRO = Party(
    name="Sample Micro Works (synthetic)",
    gstin="29SYN000000011Z1",
    address=(
        "Shed 3, Fictional Industrial Estate",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-000000001",
    enterprise="Micro",
    nic="25920",
    registered_on="01/04/2022",
    investment="Rs 40,00,000",
    turnover="Rs 2,00,00,000",
)

FABRICATORS = Party(
    name="Sample Fabricators Pvt Ltd (synthetic)",
    gstin="29SYN000000012Z1",
    address=(
        "Works 7, Fictional Industrial Estate",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-000000003",
    enterprise="Small",
    nic="25990",
    registered_on="10/01/2023",
    investment="Rs 6,00,00,000",
    turnover="Rs 40,00,00,000",
)

MAINTENANCE = Party(
    name="Sample Maintenance Services (synthetic)",
    gstin="29SYN000000013Z1",
    address=(
        "Unit 2, Fictional Trade Centre",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-000000006",
    enterprise="Micro",
    nic="33121",
    registered_on="15/08/2022",
    investment="Rs 25,00,000",
    turnover="Rs 1,10,00,000",
)

BUYER_CORP = Party(
    name="Sample Buyer Corp (synthetic)",
    gstin="29SYN000000000Z1",
    address=(
        "Plot 9, Fictional Trade Centre",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-900000000",
    enterprise="Not applicable",
    nic="not applicable",
    registered_on="01/01/2020",
    investment="not applicable",
    turnover="not applicable",
    email="purchase@example.invalid",
)

BUYER_TWO = Party(
    name="Sample Buyer Two Ltd (synthetic)",
    gstin="29SYN000000001Z1",
    address=(
        "Tower B, Fictional Trade Centre",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-900000001",
    enterprise="Not applicable",
    nic="not applicable",
    registered_on="01/01/2020",
    investment="not applicable",
    turnover="not applicable",
    email="purchase@example.invalid",
)

BUYER_FOUR = Party(
    name="Sample Buyer Four Ltd (synthetic)",
    gstin="29SYN000000003Z1",
    address=(
        "Block 4, Fictional Trade Centre",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-900000003",
    enterprise="Not applicable",
    nic="not applicable",
    registered_on="01/01/2020",
    investment="not applicable",
    turnover="not applicable",
    email="purchase@example.invalid",
)

BUYER_SEVEN = Party(
    name="Sample Buyer Seven Pvt Ltd (synthetic)",
    gstin="29SYN000000006Z1",
    address=(
        "Plot 21, Fictional Trade Centre",
        "Sample Nagar, Karnataka 560000, India",
    ),
    udyam="UDYAM-SYN-900000006",
    enterprise="Not applicable",
    nic="not applicable",
    registered_on="01/01/2020",
    investment="not applicable",
    turnover="not applicable",
    email="purchase@example.invalid",
)


def _address(party: Party) -> str:
    return ", ".join(party.address)


def _letterhead(
    party: Party, title: str, subtitle: str, *, gstin: bool = True
) -> Letterhead:
    lines = list(party.address)
    if gstin:
        lines.append(f"GSTIN: {party.gstin}")
    lines.append(f"Email: {party.email}")
    return Letterhead(
        company=party.name, lines=tuple(lines), title=title, subtitle=subtitle
    )


# --------------------------------------------------------------- documents --


def _invoice_totals(
    taxable: Decimal, tax_rate_pct: Decimal, target: Decimal | None
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(cgst, sgst, round_off, grand_total), each quantised to paise."""
    half = (tax_rate_pct / 2).quantize(Decimal("0.01"))
    cgst = (taxable * half / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sgst = cgst
    gross = taxable + cgst + sgst
    if target is None:
        return cgst, sgst, Decimal("0.00"), gross.quantize(Decimal("0.01"))
    round_off = (target - gross).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return cgst, sgst, round_off, target


@dataclass(frozen=True)
class LineItem:
    description: str
    hsn: str
    qty: str
    rate: str

    @property
    def amount(self) -> Decimal:
        return D(self.qty) * D(self.rate)


def build_invoice(
    *,
    supplier: Party,
    buyer: Party,
    invoice_no: str,
    invoice_date: str,
    delivery_date: str | None,
    po_no: str | None,
    credit_days: int,
    items: Sequence[LineItem],
    freight: Decimal,
    tax_rate_pct: Decimal,
    target_total: Decimal | None,
    include_gstin: bool = True,
    include_total: bool = True,
    include_delivery: bool = True,
    include_date: bool = True,
    subtitle: str = "ORIGINAL FOR RECIPIENT",
) -> Sheet:
    blocks: list[Block] = [
        _letterhead(supplier, "TAX INVOICE", subtitle, gstin=include_gstin),
        Gap(4),
    ]

    if include_gstin:
        blocks.append(
            P(f"Supplier: {supplier.name}   GSTIN: {supplier.gstin}", "bold", 1)
        )
        blocks.append(P(f"Bill to: {buyer.name}   GSTIN: {buyer.gstin}", "bold", 1))
    else:
        blocks.append(P(f"Supplier: {supplier.name}", "bold", 1))
        blocks.append(P(f"Bill to: {buyer.name}", "bold", 1))
    blocks.append(P(_address(supplier), "small", 1))
    blocks.append(P(_address(buyer), "small", 10))

    meta: list[tuple[str, str]] = [("Tax Invoice No", invoice_no)]
    if include_date:
        meta.append(("Date", invoice_date))
    if po_no:
        meta.append(("Your PO", po_no))
    if include_delivery and delivery_date:
        meta.append(("Delivery date", delivery_date))
    meta.append(("Payment terms", f"Net {credit_days} days"))
    meta.append(("Place of supply", "Karnataka (29)"))
    blocks.append(KVT(tuple(meta)))

    rows: list[tuple[str, str, str, str, str]] = []
    taxable = Decimal("0.00")
    for item in items:
        taxable += item.amount
        rows.append(
            (
                item.description,
                item.hsn,
                item.qty,
                inr(D(item.rate)),
                inr(item.amount),
            )
        )
    taxable += freight
    if freight:
        rows.append(
            (
                "Freight and packing (reimbursement)",
                "9965",
                "1",
                inr(freight),
                inr(freight),
            )
        )
    blocks.append(
        T(
            header=("Description", "HSN/SAC", "Qty", "Rate", "Amount"),
            rows=tuple(rows),
            fractions=(0.46, 0.12, 0.08, 0.16, 0.18),
            aligns=("L", "L", "R", "R", "R"),
        )
    )

    cgst, sgst, round_off, total = _invoice_totals(taxable, tax_rate_pct, target_total)
    half = (tax_rate_pct / 2).quantize(Decimal("0.01"))
    totals: list[tuple[str, str]] = [("Taxable value", inr(taxable))]
    totals.append((f"CGST @ {pct(half)}%", inr(cgst)))
    totals.append((f"SGST @ {pct(half)}%", inr(sgst)))
    if round_off != 0:
        totals.append(("Round off", inr(round_off)))
    if include_total:
        totals.append(("Grand Total", f"Rs {inr(total)}"))
    blocks.append(Totals(tuple(totals)))

    if include_total:
        blocks.append(P(f"Amount in words: {words_inr(total)}", "bold", 2))
    blocks.append(
        P(
            "Bank details: Fictional Bank A, A/c 000000000000, "
            "IFSC FICT0000001 (fictional, for layout only).",
            "small",
            8,
        )
    )
    blocks.append(
        Note(
            "SYNTHETIC SAMPLE - generated for the SamadhaanOS demo. Not a real tax "
            "invoice. No real party, GSTIN or supply is represented."
        )
    )
    blocks.append(P(f"For {supplier.name}", "body", 1))
    blocks.append(P("Authorised signatory (fictional)", "note", 2))
    return Sheet(title=f"Tax invoice {invoice_no}", blocks=blocks)


def build_po(
    *,
    buyer: Party,
    supplier: Party,
    po_no: str,
    order_date: str,
    delivery_date: str,
    credit_days: int,
    items: Sequence[LineItem],
    freight: Decimal,
    tax_rate_pct: Decimal,
) -> Sheet:
    taxable = sum((item.amount for item in items), Decimal("0.00")) + freight
    _, _, _, total = _invoice_totals(taxable, tax_rate_pct, None)
    # A purchase order estimates in whole rupees; the invoice carries the paise.
    total = total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    flip = items[0].qty if items else "1"
    blocks: list[Block] = [
        _letterhead(buyer, "PURCHASE ORDER", "SYNTHETIC SPECIMEN"),
        Gap(4),
        P(f"Buyer: {buyer.name}   GSTIN: {buyer.gstin}", "bold", 1),
        P(_address(buyer), "small", 8),
        P(f"Supplier: {supplier.name}   GSTIN: {supplier.gstin}", "bold", 1),
        P(_address(supplier), "small", 8),
        KVT(
            (
                ("PO No", po_no),
                ("Order date", order_date),
                ("Delivery date", delivery_date),
                ("Payment terms", f"Net {credit_days} days from delivery"),
                ("Delivery instructions", "Fictional Industrial Estate stores, gate 2"),
            )
        ),
        T(
            header=("Description", "HSN/SAC", "Qty", "Rate", "Basic value"),
            rows=tuple(
                (
                    item.description,
                    item.hsn,
                    item.qty,
                    inr(D(item.rate)),
                    inr(item.amount),
                )
                for item in items
            )
            + (
                (
                    "Freight and packing (reimbursement)",
                    "9965",
                    "1",
                    inr(freight),
                    inr(freight),
                ),
            ),
            fractions=(0.46, 0.12, 0.08, 0.16, 0.18),
            aligns=("L", "L", "R", "R", "R"),
        ),
        Totals(
            (
                ("Basic value", inr(taxable)),
                ("GST", f"{tax_rate_pct}% extra as applicable"),
                ("Estimated total", f"Rs {inr(total)}"),
            )
        ),
        P(
            f"Notes: The estimated total is inclusive of GST at {tax_rate_pct}%. "
            f"Please quote {po_no} on your invoice. Deliver in one lot. "
            f"Order quantity: {flip} units.",
            "small",
            8,
        ),
        Note(
            "SYNTHETIC SAMPLE - generated for the SamadhaanOS demo. Not a real "
            "purchase order. The Net-90 term is a demo of a contractual term that "
            "does not move the statutory clock; the engine decides that, not this page."
        ),
    ]
    return Sheet(title=f"Purchase order {po_no}", blocks=blocks)


def build_challan(
    *,
    supplier: Party,
    buyer: Party,
    challan_no: str,
    challan_date: str,
    invoice_no: str,
    po_no: str,
    lr_no: str,
    vehicle_no: str,
    items: Sequence[LineItem],
) -> Sheet:
    blocks: list[Block] = [
        _letterhead(supplier, "DELIVERY CHALLAN", "NOT A TAX INVOICE"),
        Gap(4),
        P(f"Consignor: {supplier.name}   GSTIN: {supplier.gstin}", "bold", 1),
        P(_address(supplier), "small", 1),
        P(f"Consignee: {buyer.name}   GSTIN: {buyer.gstin}", "bold", 1),
        P(_address(buyer), "small", 8),
        KVT(
            (
                ("Challan No", challan_no),
                ("Challan date", challan_date),
                ("Against Invoice No", invoice_no),
                ("Your PO", po_no),
                ("LR / Docket No", lr_no),
                ("Vehicle No", vehicle_no),
            )
        ),
        T(
            header=("Description", "HSN/SAC", "Qty", "Remarks"),
            rows=tuple(
                (item.description, item.hsn, item.qty, "Delivered in good condition")
                for item in items
            ),
            fractions=(0.50, 0.14, 0.10, 0.26),
            aligns=("L", "L", "R", "L"),
        ),
        P("Received the quantity shown above in good condition.", "body", 10),
        P(f"For {buyer.name}", "body", 1),
        P("Stores in-charge (fictional)", "note", 2),
        Note(
            "SYNTHETIC SAMPLE - generated for the SamadhaanOS demo. Not a real "
            "delivery challan and not evidence of any real supply."
        ),
    ]
    return Sheet(title=f"Delivery challan {challan_no}", blocks=blocks)


def build_grn(
    *,
    buyer: Party,
    supplier: Party,
    grn_no: str,
    delivery_date: str,
    invoice_no: str,
    po_no: str,
    items: Sequence[LineItem],
) -> Sheet:
    total_qty = sum((D(item.qty) for item in items), Decimal("0"))
    qty = str(int(total_qty))
    blocks: list[Block] = [
        _letterhead(buyer, "GOODS RECEIPT NOTE", "DELIVERY PROOF - SYNTHETIC"),
        Gap(4),
        P(f"Supplier: {supplier.name}   GSTIN: {supplier.gstin}", "bold", 1),
        P(f"Buyer: {buyer.name}   GSTIN: {buyer.gstin}", "bold", 1),
        KVT(
            (
                ("GRN No", grn_no),
                ("Delivery date", delivery_date),
                ("Against Invoice No", invoice_no),
                ("Your PO", po_no),
                ("Quantity received", qty),
                ("Quantity accepted", qty),
                ("Quantity rejected", "0"),
                ("Condition", "Received in good condition, no shortage, no damage"),
            )
        ),
        T(
            header=("Description", "HSN/SAC", "Qty received", "Qty accepted"),
            rows=tuple(
                (item.description, item.hsn, item.qty, item.qty) for item in items
            ),
            fractions=(0.52, 0.14, 0.17, 0.17),
            aligns=("L", "L", "R", "R"),
        ),
        P(
            "Remarks: GRN signed by stores. No rejection was raised on this delivery.",
            "body",
            10,
        ),
        P(f"For {buyer.name}", "body", 1),
        P("Stores in-charge (fictional)", "note", 2),
        Note(
            "SYNTHETIC SAMPLE - generated for the SamadhaanOS demo. A real GRN is "
            "signed by the buyer; this page proves nothing."
        ),
    ]
    return Sheet(title=f"Goods receipt note {grn_no}", blocks=blocks)


def build_udyam_extract(*, supplier: Party) -> Sheet:
    blocks: list[Block] = [
        _letterhead(
            supplier,
            "UDYAM REGISTRATION",
            "DATA EXTRACT - NOT A CERTIFICATE",
            gstin=False,
        ),
        Gap(4),
        Note(
            "NOT AN UDYAM REGISTRATION CERTIFICATE. This page is a synthetic "
            "transcription of the fields a supplier reads from their own "
            "certificate, for OCR testing. It is not issued by any authority, "
            "has no legal effect, and SamadhaanOS never generates government "
            "documents (AGENTS.md golden rules 9 and 17)."
        ),
        KVT(
            (
                ("Udyam Registration Number", supplier.udyam),
                ("Name of Enterprise", supplier.name),
                ("Enterprise Type", supplier.enterprise),
                ("Major Activity", "Manufacturing"),
                ("NIC Code", supplier.nic),
                ("Registered on", supplier.registered_on),
                ("Social Category", "General"),
                ("Unit Address", _address(supplier)),
                ("District / State", "Sample Nagar / Karnataka"),
                ("Investment in Plant and Machinery", supplier.investment),
                ("Annual Turnover", supplier.turnover),
                ("GSTIN", supplier.gstin),
            )
        ),
        Note(
            "The page states the enterprise's own declared particulars. Whether the "
            "supplier qualifies under the Act is decided by the engine from the "
            "case input, not from this page."
        ),
    ]
    return Sheet(title="Udyam registration data extract", blocks=blocks)


def build_gst_return(
    *,
    supplier: Party,
    form: str,
    period: str,
    filed_on: str,
    invoice_no: str,
    invoice_date: str,
    taxable: Decimal,
    cgst: Decimal,
    sgst: Decimal,
    total: Decimal,
) -> Sheet:
    if form == "GSTR-1":
        intro = (
            "Invoice-level detail for one invoice, as a supplier would export it "
            "to show that a supply was declared."
        )
    else:
        intro = (
            "Summary of outward taxable supplies for the period, as a supplier "
            "would export it."
        )
    blocks: list[Block] = [
        _letterhead(supplier, f"GST RETURN - {form}", "SYNTHETIC EXTRACT", gstin=False),
        Gap(4),
        Note(
            f"{intro} This is not a GST portal document and it is not a filing. "
            "Every figure is synthetic."
        ),
        KVT(
            (
                ("GSTIN", supplier.gstin),
                ("Legal name", supplier.name),
                ("Return form", form),
                ("Return period", period),
                ("Filed on", filed_on),
                ("Status", "Filed (synthetic)"),
            )
        ),
        P(f"Invoice No: {invoice_no}", "bold", 1),
        P(f"Invoice date: {invoice_date}", "body", 1),
        T(
            header=("Tax head", "Amount"),
            rows=(
                ("Taxable value", inr(taxable)),
                ("CGST", inr(cgst)),
                ("SGST", inr(sgst)),
                ("Invoice value", f"Rs {inr(total)}"),
            ),
            fractions=(0.70, 0.30),
            aligns=("L", "R"),
        ),
        Note(
            "A return extract shows what was declared. It does not prove payment, "
            "acceptance, or the buyer's position."
        ),
    ]
    return Sheet(title=f"{form} extract", blocks=blocks)


def build_objection(
    *,
    buyer: Party,
    supplier: Party,
    sent: str,
    subject: str,
    invoice_no: str,
    body: Sequence[str],
) -> Sheet:
    blocks: list[Block] = [
        _letterhead(
            buyer, "WRITTEN OBJECTION", "E-MAIL PRINT - SYNTHETIC", gstin=False
        ),
        Gap(4),
        KVT(
            (
                ("From (buyer)", "Purchase Desk <purchase@example.invalid>"),
                ("To (supplier)", "Accounts <accounts@example.invalid>"),
                ("Buyer GSTIN", buyer.gstin),
                ("Sent", sent),
                ("Subject", subject),
            )
        ),
        P("Dear Sir/Madam,", "body", 8),
    ]
    for para in body:
        blocks.append(P(para, "body", 8))
    blocks.append(P(f"Reference: Invoice No {invoice_no}", "small", 8))
    blocks.append(
        Note("SYNTHETIC SAMPLE - a fictional buyer's email, not a real dispute.")
    )
    return Sheet(title="Written objection", blocks=blocks)


def build_remittance(
    *,
    buyer: Party,
    supplier: Party,
    advice_no: str,
    paid_on: str,
    invoice_no: str,
    invoice_value: Decimal,
    amount_paid: Decimal,
    balance: Decimal,
) -> Sheet:
    blocks: list[Block] = [
        _letterhead(buyer, "REMITTANCE ADVICE", "SYNTHETIC SPECIMEN", gstin=False),
        Gap(4),
        KVT(
            (
                ("Advice No", advice_no),
                ("Payment date", paid_on),
                ("Supplier", supplier.name),
                ("Supplier GSTIN", supplier.gstin),
                ("Buyer GSTIN", buyer.gstin),
                ("Invoice No", invoice_no),
                ("Invoice value", f"Rs {inr(invoice_value)}"),
                ("Amount paid", f"Rs {inr(amount_paid)}"),
                ("Balance outstanding", f"Rs {inr(balance)}"),
                ("Mode", "NEFT (simulated)"),
                ("UTR", "SYNTHUTR0001"),
            )
        ),
        Note(
            "SYNTHETIC SAMPLE - a fictional buyer's accounts-payable advice. The "
            "bank, the UTR and the payment are simulated; no money moved."
        ),
    ]
    return Sheet(title="Remittance advice", blocks=blocks)


# ------------------------------------------------------------------ chats --

SIDE_RIGHT = "right"
SIDE_LEFT = "left"


@dataclass(frozen=True)
class ChatMsg:
    date: str
    time: str
    sender: str
    text: str
    side: str


@dataclass(frozen=True)
class Chat:
    title: str
    preamble: str
    messages: tuple[ChatMsg, ...]

    def export(self, *, ios: bool = False) -> str:
        lines = [BANNER_TEXT, self.preamble, ""]
        for msg in self.messages:
            if ios:
                lines.append(f"[{msg.date}, {msg.time}] {msg.sender}: {msg.text}")
            else:
                lines.append(f"{msg.date}, {msg.time} - {msg.sender}: {msg.text}")
        return "\n".join(lines) + "\n"


def render_chat_png(chat: Chat, path: Path, *, scale: float = 2.0) -> None:
    """A neutral chat-transcript render (no platform logo, no page styling)."""
    from reportlab.lib.utils import simpleSplit as split  # local alias

    width = 390
    pad = 14
    bubble_max = 250
    header = 34
    heights: list[tuple[ChatMsg, list[str], float]] = []
    for msg in chat.messages:
        lines = split(msg.text, "Helvetica", 8.4, bubble_max - 16)
        heights.append((msg, lines, 12 + 11.6 * len(lines) + 12))
    total = header + sum(h for _, _, h in heights) + 24
    path.parent.mkdir(parents=True, exist_ok=True)

    canvas = rl_canvas.Canvas(
        str(path.with_suffix(".chat.pdf")), pagesize=(width, total)
    )
    canvas.setFillColor(colors.HexColor("#f7f6f2"))
    canvas.rect(0, 0, width, total, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#e9e6de"))
    canvas.rect(0, total - header, width, header, stroke=0, fill=1)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(pad, total - 16, "Chat transcript")
    canvas.setFont("Helvetica", 6.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        pad, total - 26, "Rendered from the synthetic export - fictional parties"
    )

    y = total - header - 10
    for msg, lines, height in heights:
        y -= height
        right = msg.side == SIDE_RIGHT
        x = pad if not right else width - pad - bubble_max - 8
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.2)
        label = f"{msg.sender}  {msg.date} {msg.time}"
        if right:
            canvas.drawRightString(width - pad, y + height - 9, label)
        else:
            canvas.drawString(pad, y + height - 9, label)
        bubble = colors.HexColor("#dcebdc") if right else colors.HexColor("#ececec")
        canvas.setFillColor(bubble)
        canvas.roundRect(x, y + 2, bubble_max + 8, height - 14, 5, stroke=0, fill=1)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica", 8.4)
        ty = y + height - 24
        for line in lines:
            canvas.drawString(x + 8, ty, line)
            ty -= 11.6
        y -= 2

    canvas.showPage()
    canvas.save()

    import pymupdf  # noqa: PLC0415 - development-only import

    pdf = pymupdf.open(str(path.with_suffix(".chat.pdf")))
    pix = pdf[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale))
    path.write_bytes(pix.tobytes("png"))
    pdf.close()
    path.with_suffix(".chat.pdf").unlink()


# ------------------------------------------------------------- rendering ----


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter  # noqa: F401
    except ImportError as exc:  # pragma: no cover - developer message
        raise SystemExit(
            "Pillow is needed for the scanned/photo variants: pip install pillow"
        ) from exc
    return Image, ImageDraw, ImageEnhance, ImageFilter


def _pymupdf():
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - developer message
        raise SystemExit(
            "PyMuPDF is needed to rasterise and assemble the scans: pip install pymupdf"
        ) from exc
    return pymupdf


def rasterize(pdf_path: Path, *, dpi: int = 150):
    pymupdf = _pymupdf()
    Image, _, _, _ = _pil()
    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    return pages


def images_to_pdf(images, path: Path) -> None:
    """Image-only PDF (no text layer), fixed metadata, so it is a real OCR target."""
    pymupdf = _pymupdf()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for image in images:
        temp = path.with_suffix(".page.png")
        image.save(temp)
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_image(page.rect, filename=str(temp))
        temp.unlink()
    doc.set_metadata(
        {
            "title": "Synthetic scanned sample",
            "author": "SamadhaanOS sample corpus (synthetic)",
            "subject": "Image-only page for OCR testing",
            "creator": "sample_data/generate_samples.py",
            "producer": "PyMuPDF",
            "creationDate": "D:20260101000000Z",
            "modDate": "D:20260101000000Z",
        }
    )
    try:
        doc.save(str(path), garbage=4, deflate=True, no_new_id=True)
    except TypeError:  # older PyMuPDF
        doc.save(str(path), garbage=4, deflate=True)
    doc.close()


def _rotate(image, degrees: float):
    Image, _, _, _ = _pil()
    return image.rotate(
        degrees, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
    )


def _speckle(image, *, seed: int = 7, count: int = 900):
    Image, ImageDraw, _, _ = _pil()
    image = image.copy()
    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    width, height = image.size
    for _ in range(count):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        shade = rng.randint(140, 225)
        draw.point((x, y), fill=(shade, shade, shade))
    for _ in range(14):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        draw.line(
            (x, y, x + rng.randint(40, 220), y + rng.randint(-6, 6)),
            fill=(rng.randint(150, 210),) * 3,
            width=1,
        )
    return image


def _shadow(image):
    Image, ImageDraw, _, ImageFilter = _pil()
    width, height = image.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(
        [(0, 0), (int(width * 0.16), 0), (int(width * 0.05), height), (0, height)],
        fill=(20, 20, 20, 120),
    )
    draw.polygon(
        [
            (0, int(height * 0.90)),
            (width, int(height * 0.96)),
            (width, height),
            (0, height),
        ],
        fill=(20, 20, 20, 90),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(38))
    base = image.convert("RGBA")
    base.alpha_composite(overlay)
    return base.convert("RGB")


def _stamp(image):
    Image, ImageDraw, _, _ = _pil()
    from PIL import ImageFont

    image = image.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    box = (
        int(width * 0.55),
        int(height * 0.43),
        int(width * 0.93),
        int(height * 0.55),
    )
    draw.ellipse(box, outline=(150, 40, 40), width=max(3, width // 320))
    try:
        font = ImageFont.load_default(size=max(16, width // 42))
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    centre_x = (box[0] + box[2]) // 2
    for offset, text in ((0, "RECEIVED"), (1, "16 FEB 2026 - STORES")):
        text_box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (
                centre_x - (text_box[2] - text_box[0]) / 2,
                box[1]
                + (box[3] - box[1]) * (0.32 + 0.30 * offset)
                - (text_box[3] - text_box[1]) / 2,
            ),
            text,
            font=font,
            fill=(150, 40, 40),
        )
    return image


# ---------------------------------------------------------------- manifest --


MANIFEST: dict = {
    "corpus": "SamadhaanOS synthetic sample documents",
    "version": "1.0",
    "generated_by": "sample_data/generate_samples.py",
    "synthetic_only": True,
    "statement": (
        "Every party, GSTIN, amount and transaction in this corpus is fictional. "
        "No page is a real tax invoice, purchase order, government certificate, "
        "notice or filing. The Udyam page is a data extract, not a certificate. "
        "Nothing here is legal advice."
    ),
    "field_keys": [
        "invoice_number",
        "invoice_date",
        "amount",
        "supplier_gstin",
        "buyer_gstin",
        "buyer_name",
        "delivery_date",
        "po_reference",
        "written_credit_days",
        "supplier_name",
    ],
    "cases": [],
    "files": [],
}


class Corpus:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: list[dict] = []

    # -- ledger -------------------------------------------------------
    def _add(self, entry: dict) -> None:
        if any(item["file"] == entry["file"] for item in self.files):
            raise SystemExit(f"duplicate manifest entry: {entry['file']}")
        self.files.append(entry)

    def _write_text(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    # -- writers ------------------------------------------------------
    def pdf(
        self,
        rel: str,
        sheet: Sheet,
        *,
        doc_type: str,
        case: str,
        evidence: str | None = None,
        expect: dict | None = None,
        kind: str = "DOCUMENT_TEXT",
        warnings: Sequence[str] = ("MACHINE_SUGGESTED",),
        not_warnings: Sequence[str] = (),
        messages: Sequence[dict] = (),
        notes: str = "",
        twin: bool = True,
        text_layer_must_contain: Sequence[str] = (),
    ) -> Path:
        path = self.root / rel
        pages = render_pdf(sheet, path)
        self._add(
            {
                "file": rel,
                "role": "document",
                "doc_type": doc_type,
                "evidence_kind": evidence,
                "case": case,
                "render": "digital",
                "text_layer": True,
                "pages": pages,
                "expected": expect or {},
                "text_layer_must_contain": list(text_layer_must_contain),
                "notes": notes,
            }
        )
        if twin:
            txt = str(Path(rel).with_suffix(".txt")).replace("\\", "/")
            self._write_text(txt, sheet.text())
            self._add(
                {
                    "file": txt,
                    "role": "text_twin",
                    "doc_type": doc_type,
                    "evidence_kind": evidence,
                    "case": case,
                    "render": "text",
                    "text_layer": None,
                    "pages": None,
                    "expected": expect or {},
                    "expect_kind": kind,
                    "expected_warnings": list(warnings),
                    "not_expected_warnings": list(not_warnings),
                    "expected_messages": list(messages),
                    "notes": notes,
                }
            )
        return path

    def chat(
        self,
        rel: str,
        chat: Chat,
        *,
        case: str,
        expect: dict,
        warnings: Sequence[str],
        not_warnings: Sequence[str] = (),
        messages: Sequence[dict] = (),
        notes: str = "",
        ios: bool = False,
    ) -> None:
        self._write_text(rel, chat.export(ios=ios))
        self._add(
            {
                "file": rel,
                "role": "chat_export",
                "doc_type": "WHATSAPP_EXPORT",
                "evidence_kind": "WHATSAPP",
                "case": case,
                "render": "text",
                "text_layer": None,
                "pages": None,
                "expected": expect,
                "expect_kind": "WHATSAPP_EXPORT",
                "expected_warnings": list(warnings),
                "not_expected_warnings": list(not_warnings),
                "expected_messages": list(messages),
                "notes": notes,
            }
        )

    def chat_png(self, rel: str, chat: Chat, *, case: str, source: str) -> None:
        render_chat_png(chat, self.root / rel)
        self._add(
            {
                "file": rel,
                "role": "chat_render",
                "doc_type": "CHAT_SCREENSHOT",
                "evidence_kind": "WHATSAPP",
                "case": case,
                "render": "raster",
                "text_layer": False,
                "pages": 1,
                "expected": {},
                "notes": (
                    f"Neutral transcript image rendered from {source}. "
                    "No platform logo or page styling."
                ),
            }
        )

    def derived(
        self,
        rel: str,
        data: bytes,
        *,
        doc_type: str,
        case: str,
        evidence: str | None,
        expected: dict,
        render: str,
        text_layer: bool,
        notes: str,
        pages: int = 1,
    ) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self._add(
            {
                "file": rel,
                "role": "derived",
                "doc_type": doc_type,
                "evidence_kind": evidence,
                "case": case,
                "render": render,
                "text_layer": text_layer,
                "pages": pages,
                "expected": expected,
                "notes": notes,
            }
        )

    def edge_pdf(
        self,
        rel: str,
        sheet: Sheet,
        *,
        doc_type: str,
        case: str,
        expect: dict,
        notes: str,
        twin: bool = True,
        warnings: Sequence[str] = ("MACHINE_SUGGESTED",),
        not_warnings: Sequence[str] = (),
    ) -> None:
        self.pdf(
            rel,
            sheet,
            doc_type=doc_type,
            case=case,
            expect=expect,
            notes=notes,
            twin=twin,
            warnings=warnings,
            not_warnings=not_warnings,
        )


# ------------------------------------------------------------- the corpus --

C01 = "case-01-sample-supplies"
C02 = "case-02-micro-works"
C04 = "case-04-fabricators"
C06 = "case-06-maintenance"
RECORDS = "supplier-records"
STRESS = "ocr-stress"


def build_corpus(corpus: Corpus) -> None:
    # ---------------------------------------------------------- case 01 --
    po_items = (
        LineItem("Fabricated component, MS bracket, 12 mm", "7308", "100", "10593.22"),
    )
    po = build_po(
        buyer=BUYER_CORP,
        supplier=SUPPLIES,
        po_no="PO-2026-0114",
        order_date="15/01/2026",
        delivery_date="16/02/2026",
        credit_days=90,
        items=po_items,
        freight=Decimal("0.00"),
        tax_rate_pct=Decimal("18.00"),
    )
    corpus.pdf(
        f"{C01}/01-purchase-order/PO-2026-0114.pdf",
        po,
        doc_type="PURCHASE_ORDER",
        evidence="PO",
        case=C01,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": "1250000.00",
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": "90",
        },
        text_layer_must_contain=("PO-2026-0114", "Net 90 days"),
        notes=(
            "A PO is not an invoice: invoice_number and invoice_date are expected "
            "to be missing, and the user confirms the rest. The Net-90 term is the "
            "demo's 'a contract cannot move the statutory clock' case."
        ),
    )

    invoice_items = (
        LineItem("Fabricated component, MS bracket, 12 mm", "7308", "100", "10593.22"),
    )
    invoice = build_invoice(
        supplier=SUPPLIES,
        buyer=BUYER_CORP,
        invoice_no="INV-2026-0042",
        invoice_date="16/02/2026",
        delivery_date="16/02/2026",
        po_no="PO-2026-0114",
        credit_days=90,
        items=invoice_items,
        freight=Decimal("0.00"),
        tax_rate_pct=Decimal("18.00"),
        target_total=Decimal("1250000.00"),
    )
    invoice_expect = {
        "invoice_number": "INV-2026-0042",
        "invoice_date": "2026-02-16",
        "amount": "1250000.00",
        "supplier_gstin": SUPPLIES.gstin,
        "buyer_gstin": BUYER_CORP.gstin,
        "buyer_name": BUYER_CORP.name,
        "supplier_name": SUPPLIES.name,
        "delivery_date": "2026-02-16",
        "po_reference": "PO-2026-0114",
        "written_credit_days": "90",
    }
    corpus.pdf(
        f"{C01}/02-tax-invoice/INV-2026-0042.pdf",
        invoice,
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C01,
        expect=invoice_expect,
        text_layer_must_contain=(
            "INV-2026-0042",
            "12,50,000.00",
            "Sample Buyer Corp (synthetic)",
        ),
        notes=(
            "Golden-path invoice. Taxable 10,59,322.00 + 9% CGST + 9% SGST "
            "+ 0.04 round-off = 12,50,000.00, the preset case_01 principal."
        ),
    )

    challan = build_challan(
        supplier=SUPPLIES,
        buyer=BUYER_CORP,
        challan_no="DC-2026-0088",
        challan_date="16/02/2026",
        invoice_no="INV-2026-0042",
        po_no="PO-2026-0114",
        lr_no="LR-SYN-0091",
        vehicle_no="KA-00-SYN-0000",
        items=invoice_items,
    )
    corpus.pdf(
        f"{C01}/03-delivery/DC-2026-0088.pdf",
        challan,
        doc_type="DELIVERY_CHALLAN",
        evidence="DELIVERY_PROOF",
        case=C01,
        expect={
            "invoice_number": "INV-2026-0042",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": None,
        },
        text_layer_must_contain=("DC-2026-0088", "LR-SYN-0091"),
        notes=(
            "A challan proves delivery, not the invoice date or amount: both are "
            "expected to be missing. 'Challan date' is what the delivery-date rule "
            "anchors on."
        ),
    )

    grn = build_grn(
        buyer=BUYER_CORP,
        supplier=SUPPLIES,
        grn_no="GRN-2026-0088",
        delivery_date="16/02/2026",
        invoice_no="INV-2026-0042",
        po_no="PO-2026-0114",
        items=invoice_items,
    )
    corpus.pdf(
        f"{C01}/03-delivery/GRN-2026-0088.pdf",
        grn,
        doc_type="GOODS_RECEIPT_NOTE",
        evidence="DELIVERY_PROOF",
        case=C01,
        expect={
            "invoice_number": "INV-2026-0042",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": None,
        },
        text_layer_must_contain=("GRN-2026-0088", "16/02/2026"),
        notes=(
            "A GRN is the buyer's own receipt. This one is a clean receipt with no "
            "rejection, because case_01 has no objection."
        ),
    )

    chat_01 = Chat(
        title="Case 01 - delivery and payment promise",
        preamble=(
            "Synthetic WhatsApp export for the SamadhaanOS demo. Fictional parties, "
            "fictional numbers."
        ),
        messages=(
            ChatMsg(
                "16/02/2026",
                "9:40 AM",
                "Anu (fictional)",
                "Vehicle left our works this morning with 100 units against invoice INV-2026-0042.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "16/02/2026",
                "4:30 PM",
                "Buyer Stores (fictional)",
                "We received the 100 units today. GRN signed, no shortage.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "18/02/2026",
                "11:05 AM",
                "Anu (fictional)",
                "Thanks. The PO says Net 90 days from delivery, so we were expecting payment by mid-May.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "10/04/2026",
                "5:45 PM",
                "Buyer Accounts (fictional)",
                "Payment for the invoice will be released by 30 April.",
                SIDE_LEFT,
            ),
        ),
    )
    corpus.chat(
        f"{C01}/04-whatsapp/chat_delivery_and_promise.txt",
        chat_01,
        case=C01,
        expect={
            "invoice_number": "INV-2026-0042",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": "90",
        },
        warnings=("MACHINE_SUGGESTED", "OBJECTION_WINDOW_APPLIED"),
        not_warnings=("DELIVERY_ANCHOR_MISSING",),
        messages=(
            {
                "contains": "We received the 100 units",
                "tags": ["DELIVERY_CONFIRMATION"],
            },
            {
                "contains": "will be released by 30 April",
                "tags": ["PAYMENT_PROMISE"],
                "days_after_delivery": 53,
            },
        ),
        notes=(
            "The delivery line on 16/02/2026 is the anchor (day 0). The promise on "
            "10/04/2026 is 53 days later, which is the preset's acknowledgment date."
        ),
    )
    corpus.chat_png(
        f"{C01}/04-whatsapp/chat_delivery_and_promise.png",
        chat_01,
        case=C01,
        source="chat_delivery_and_promise.txt",
    )

    # ---------------------------------------------------------- case 02 --
    micro_items = (
        LineItem("Machined bush, zinc plated, 25 mm", "7318", "300", "845.00"),
    )
    corpus.pdf(
        f"{C02}/01-purchase-order/PO-2026-0209.pdf",
        build_po(
            buyer=BUYER_TWO,
            supplier=MICRO,
            po_no="PO-2026-0209",
            order_date="01/03/2026",
            delivery_date="15/03/2026",
            credit_days=30,
            items=micro_items,
            freight=Decimal("737.29"),
            tax_rate_pct=Decimal("18.00"),
        ),
        doc_type="PURCHASE_ORDER",
        evidence="PO",
        case=C02,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": "300000.00",
            "supplier_gstin": MICRO.gstin,
            "buyer_gstin": BUYER_TWO.gstin,
            "buyer_name": BUYER_TWO.name,
            "supplier_name": MICRO.name,
            "delivery_date": "2026-03-15",
            "po_reference": "PO-2026-0209",
            "written_credit_days": "30",
        },
        text_layer_must_contain=("PO-2026-0209", "Net 30 days"),
        notes="Micro enterprise, Net 30, with a freight line so the total is exact.",
    )
    corpus.pdf(
        f"{C02}/02-tax-invoice/INV-2026-0209.pdf",
        build_invoice(
            supplier=MICRO,
            buyer=BUYER_TWO,
            invoice_no="INV-2026-0209",
            invoice_date="15/03/2026",
            delivery_date="15/03/2026",
            po_no="PO-2026-0209",
            credit_days=30,
            items=micro_items,
            freight=Decimal("737.29"),
            tax_rate_pct=Decimal("18.00"),
            target_total=Decimal("300000.00"),
        ),
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C02,
        expect={
            "invoice_number": "INV-2026-0209",
            "invoice_date": "2026-03-15",
            "amount": "300000.00",
            "supplier_gstin": MICRO.gstin,
            "buyer_gstin": BUYER_TWO.gstin,
            "buyer_name": BUYER_TWO.name,
            "supplier_name": MICRO.name,
            "delivery_date": "2026-03-15",
            "po_reference": "PO-2026-0209",
            "written_credit_days": "30",
        },
        text_layer_must_contain=("INV-2026-0209", "3,00,000.00"),
        notes="Overdue case with a written objection nine days after delivery.",
    )
    corpus.pdf(
        f"{C02}/03-delivery/DC-2026-0209.pdf",
        build_challan(
            supplier=MICRO,
            buyer=BUYER_TWO,
            challan_no="DC-2026-0209",
            challan_date="15/03/2026",
            invoice_no="INV-2026-0209",
            po_no="PO-2026-0209",
            lr_no="LR-SYN-0212",
            vehicle_no="KA-00-SYN-0001",
            items=micro_items,
        ),
        doc_type="DELIVERY_CHALLAN",
        evidence="DELIVERY_PROOF",
        case=C02,
        expect={
            "invoice_number": "INV-2026-0209",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": MICRO.gstin,
            "buyer_gstin": BUYER_TWO.gstin,
            "buyer_name": BUYER_TWO.name,
            "supplier_name": MICRO.name,
            "delivery_date": "2026-03-15",
            "po_reference": "PO-2026-0209",
            "written_credit_days": None,
        },
        text_layer_must_contain=("DC-2026-0209", "LR-SYN-0212"),
        notes="Delivery proof for the case that ends in a written objection.",
    )

    objection = build_objection(
        buyer=BUYER_TWO,
        supplier=MICRO,
        sent="24/03/2026 11:20",
        subject="Defective batch against Invoice No INV-2026-0209",
        invoice_no="INV-2026-0209",
        body=(
            "We refer to your Invoice No INV-2026-0209 dated 15/03/2026 and the 300 "
            "units received on 15/03/2026.",
            "On opening the cartons we found 18 bushes with a machining defect and "
            "4 cracked bushes. 22 pieces in total are not usable. We are rejecting "
            "these 22 pieces only; the remaining 278 pieces are accepted.",
            "Please arrange a replacement for the 22 rejected pieces. Payment for "
            "the accepted quantity will be processed as per the agreed terms once "
            "the replacement is received.",
            "This note is sent nine days after delivery. Kindly acknowledge receipt.",
        ),
    )
    corpus.pdf(
        f"{C02}/04-objection/WRITTEN-OBJECTION-2026-03-24.pdf",
        objection,
        doc_type="WRITTEN_OBJECTION",
        evidence=None,
        case=C02,
        expect={
            "invoice_number": "INV-2026-0209",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": BUYER_TWO.gstin,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        text_layer_must_contain=("INV-2026-0209", "22 pieces"),
        notes=(
            "A domestic commercial email, not an official form. Dated day 9 after "
            "delivery, which is inside the configured 15-day window."
        ),
    )
    eml = (
        "From: Purchase Desk <purchase@example.invalid>\r\n"
        "To: Accounts <accounts@example.invalid>\r\n"
        "Subject: Defective batch against Invoice No INV-2026-0209\r\n"
        "Date: Tue, 24 Mar 2026 11:20:00 +0530\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "SPECIMEN - SYNTHETIC DATA - NOT A REAL DOCUMENT\r\n"
        "Fictional buyer, fictional supplier, fictional transaction.\r\n"
        "\r\n"
        "We refer to your Invoice No INV-2026-0209 dated 15/03/2026 and the 300\r\n"
        "units received on 15/03/2026.\r\n"
        "\r\n"
        "18 bushes are defective and 4 are cracked. We are rejecting 22 pieces\r\n"
        "and accepting the remaining 278. Please arrange a replacement.\r\n"
    )
    path = corpus.root / f"{C02}/04-objection/WRITTEN-OBJECTION-2026-03-24.eml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(eml.encode("utf-8"))
    corpus._add(
        {
            "file": f"{C02}/04-objection/WRITTEN-OBJECTION-2026-03-24.eml",
            "role": "source",
            "doc_type": "WRITTEN_OBJECTION",
            "evidence_kind": None,
            "case": C02,
            "render": "email",
            "text_layer": None,
            "pages": None,
            "expected": {},
            "notes": "The same objection as a raw email, for header/body parsers.",
        }
    )

    chat_02 = Chat(
        title="Case 02 - defect on day 9",
        preamble=(
            "Synthetic WhatsApp export for the SamadhaanOS demo. Knock-off names, "
            "no real people."
        ),
        messages=(
            ChatMsg(
                "15/03/2026",
                "10:05 AM",
                "Anu (fictional)",
                "Dispatched 300 units against invoice INV-2026-0209 this morning.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "15/03/2026",
                "4:30 PM",
                "Buyer Stores (fictional)",
                "We received the 300 units today. GRN signed, thanks.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "24/03/2026",
                "11:20 AM",
                "Buyer Stores (fictional)",
                "Day 9 after delivery: 18 bushes are defective and 4 are cracked. "
                "We are rejecting those 22 pieces.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "27/03/2026",
                "3:00 PM",
                "Anu (fictional)",
                "Noted. Replacement for the 22 rejected pieces is dispatched today.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "02/04/2026",
                "9:02 AM",
                "Buyer Stores (fictional)",
                "Replacement received, the issue is resolved. Thanks for the quick fix.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "09/04/2026",
                "5:45 PM",
                "Buyer Accounts (fictional)",
                "We are waiting for the credit note for the rejected pieces.",
                SIDE_LEFT,
            ),
        ),
    )
    corpus.chat(
        f"{C02}/05-whatsapp/chat_defect_day9.txt",
        chat_02,
        case=C02,
        expect={
            "invoice_number": "INV-2026-0209",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        warnings=("MACHINE_SUGGESTED", "OBJECTION_WINDOW_APPLIED"),
        messages=(
            {
                "contains": "We received the 300 units",
                "tags": ["DELIVERY_CONFIRMATION"],
            },
            {
                "contains": "18 bushes are defective",
                "tags": ["DEFECT_OBJECTION"],
                "days_after_delivery": 9,
                "within_objection_window": True,
            },
            {
                "contains": "Replacement for the 22 rejected",
                "tags": ["DEFECT_OBJECTION", "RESOLUTION_ACK"],
            },
        ),
        notes=(
            "The objection is on day 9, inside the 15-day window, and is resolved on "
            "day 18. The resolution is not a late complaint."
        ),
    )
    corpus.chat_png(
        f"{C02}/05-whatsapp/chat_defect_day9.png",
        chat_02,
        case=C02,
        source="chat_defect_day9.txt",
    )

    chat_late = Chat(
        title="Case 02 - late complaint variant",
        preamble=(
            "Synthetic WhatsApp export. The same delivery, with the first complaint "
            "on day 60 instead of day 9."
        ),
        messages=(
            ChatMsg(
                "15/03/2026",
                "4:30 PM",
                "Buyer Stores (fictional)",
                "We received the 300 units today. GRN signed, thanks.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "14/05/2026",
                "10:10 AM",
                "Buyer Stores (fictional)",
                "60 days after delivery we are still finding cracked bushes in the "
                "same lot. This is unacceptable.",
                SIDE_LEFT,
            ),
        ),
    )
    corpus.chat(
        f"{C02}/05-whatsapp/chat_late_objection.txt",
        chat_late,
        case=C02,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        warnings=("MACHINE_SUGGESTED", "OBJECTION_WINDOW_APPLIED"),
        messages=(
            {
                "contains": "still finding cracked bushes",
                "tags": ["DEFECT_OBJECTION", "LATE_COMPLAINT"],
                "days_after_delivery": 60,
                "within_objection_window": False,
            },
        ),
        notes=(
            "Negative control: the same complaint on day 60 is tagged LATE_COMPLAINT. "
            "The tag is a suggestion; the engine decides whether it qualifies."
        ),
    )

    # ---------------------------------------------------------- case 04 --
    fab_items = (
        LineItem("Fabricated frame assembly, painted", "7308", "300", "1410.00"),
    )
    corpus.pdf(
        f"{C04}/01-purchase-order/PO-2026-0310.pdf",
        build_po(
            buyer=BUYER_FOUR,
            supplier=FABRICATORS,
            po_no="PO-2026-0310",
            order_date="15/02/2026",
            delivery_date="10/03/2026",
            credit_days=30,
            items=fab_items,
            freight=Decimal("728.81"),
            tax_rate_pct=Decimal("18.00"),
        ),
        doc_type="PURCHASE_ORDER",
        evidence="PO",
        case=C04,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": "500000.00",
            "supplier_gstin": FABRICATORS.gstin,
            "buyer_gstin": BUYER_FOUR.gstin,
            "buyer_name": BUYER_FOUR.name,
            "supplier_name": FABRICATORS.name,
            "delivery_date": "2026-03-10",
            "po_reference": "PO-2026-0310",
            "written_credit_days": "30",
        },
        text_layer_must_contain=("PO-2026-0310", "Net 30 days"),
        notes="Part-payment case. 10/03/2026 is a deliberately ambiguous date.",
    )
    corpus.pdf(
        f"{C04}/02-tax-invoice/INV-2026-0310.pdf",
        build_invoice(
            supplier=FABRICATORS,
            buyer=BUYER_FOUR,
            invoice_no="INV-2026-0310",
            invoice_date="10/03/2026",
            delivery_date="10/03/2026",
            po_no="PO-2026-0310",
            credit_days=30,
            items=fab_items,
            freight=Decimal("728.81"),
            tax_rate_pct=Decimal("18.00"),
            target_total=Decimal("500000.00"),
        ),
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C04,
        expect={
            "invoice_number": "INV-2026-0310",
            "invoice_date": "2026-03-10",
            "amount": "500000.00",
            "supplier_gstin": FABRICATORS.gstin,
            "buyer_gstin": BUYER_FOUR.gstin,
            "buyer_name": BUYER_FOUR.name,
            "supplier_name": FABRICATORS.name,
            "delivery_date": "2026-03-10",
            "po_reference": "PO-2026-0310",
            "written_credit_days": "30",
        },
        warnings=("MACHINE_SUGGESTED", "DATE_ORDER_ASSUMED"),
        text_layer_must_contain=("INV-2026-0310", "5,00,000.00"),
        notes=(
            "10/03/2026 is genuinely ambiguous (day and month are both 12 or less), "
            "so the extractor must raise DATE_ORDER_ASSUMED and the human must check."
        ),
    )
    corpus.pdf(
        f"{C04}/03-payment/REMITTANCE-ADVICE-2026-05-15.pdf",
        build_remittance(
            buyer=BUYER_FOUR,
            supplier=FABRICATORS,
            advice_no="RA-2026-0515",
            paid_on="15/05/2026",
            invoice_no="INV-2026-0310",
            invoice_value=Decimal("500000.00"),
            amount_paid=Decimal("150000.00"),
            balance=Decimal("350000.00"),
        ),
        doc_type="REMITTANCE_ADVICE",
        evidence=None,
        case=C04,
        expect={
            "invoice_number": "INV-2026-0310",
            "invoice_date": None,
            "amount": "500000.00",
            "supplier_gstin": FABRICATORS.gstin,
            "buyer_gstin": BUYER_FOUR.gstin,
            "buyer_name": None,
            "supplier_name": FABRICATORS.name,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        text_layer_must_contain=("1,50,000.00", "3,50,000.00"),
        notes=(
            "The part payment the preset records on 2026-05-15. 'Invoice value' is "
            "the invoice amount; 'Amount paid' is not the invoice amount."
        ),
    )

    # ---------------------------------------------------------- case 06 --
    maint_items = (
        LineItem(
            "Annual maintenance visit - HVAC, April to September 2026",
            "998719",
            "1",
            "211000.00",
        ),
    )
    corpus.pdf(
        f"{C06}/01-purchase-order/PO-2026-0401.pdf",
        build_po(
            buyer=BUYER_SEVEN,
            supplier=MAINTENANCE,
            po_no="PO-2026-0401",
            order_date="20/03/2026",
            delivery_date="01/04/2026",
            credit_days=30,
            items=maint_items,
            freight=Decimal("864.41"),
            tax_rate_pct=Decimal("18.00"),
        ),
        doc_type="PURCHASE_ORDER",
        evidence="PO",
        case=C06,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": "250000.00",
            "supplier_gstin": MAINTENANCE.gstin,
            "buyer_gstin": BUYER_SEVEN.gstin,
            "buyer_name": BUYER_SEVEN.name,
            "supplier_name": MAINTENANCE.name,
            "delivery_date": "2026-04-01",
            "po_reference": "PO-2026-0401",
            "written_credit_days": "30",
        },
        text_layer_must_contain=("PO-2026-0401", "Net 30 days"),
        notes="Service case: the PO exists, but no delivery proof is ever produced.",
    )
    corpus.pdf(
        f"{C06}/02-tax-invoice/INV-2026-0401.pdf",
        build_invoice(
            supplier=MAINTENANCE,
            buyer=BUYER_SEVEN,
            invoice_no="INV-2026-0401",
            invoice_date="01/04/2026",
            delivery_date=None,
            po_no="PO-2026-0401",
            credit_days=30,
            items=maint_items,
            freight=Decimal("864.41"),
            tax_rate_pct=Decimal("18.00"),
            target_total=Decimal("250000.00"),
            include_delivery=False,
        ),
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C06,
        expect={
            "invoice_number": "INV-2026-0401",
            "invoice_date": "2026-04-01",
            "amount": "250000.00",
            "supplier_gstin": MAINTENANCE.gstin,
            "buyer_gstin": BUYER_SEVEN.gstin,
            "buyer_name": BUYER_SEVEN.name,
            "supplier_name": MAINTENANCE.name,
            "delivery_date": None,
            "po_reference": "PO-2026-0401",
            "written_credit_days": "30",
        },
        warnings=("MACHINE_SUGGESTED", "DATE_ORDER_ASSUMED"),
        text_layer_must_contain=("INV-2026-0401", "2,50,000.00"),
        notes=(
            "A service invoice with NO delivery date line. Delivery is the anchor the "
            "engine needs, so this case is the 'no delivery proof' demo. 01/04/2026 "
            "is ambiguous."
        ),
    )
    chat_06 = Chat(
        title="Case 06 - no delivery confirmation",
        preamble=(
            "Synthetic WhatsApp export with no delivery confirmation anywhere, so "
            "the extractor cannot compute days after delivery."
        ),
        messages=(
            ChatMsg(
                "01/04/2026",
                "9:15 AM",
                "Anu (fictional)",
                "Invoice INV-2026-0401 raised for the April to September maintenance contract.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "07/04/2026",
                "12:40 PM",
                "Anu (fictional)",
                "The technician attended site on 03/04 and completed the service check. Please confirm acceptance.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "20/04/2026",
                "6:05 PM",
                "Buyer Accounts (fictional)",
                "Payment for the invoice will be released by 10 May.",
                SIDE_LEFT,
            ),
        ),
    )
    corpus.chat(
        f"{C06}/03-whatsapp/chat_no_delivery_confirmation.txt",
        chat_06,
        case=C06,
        expect={
            "invoice_number": "INV-2026-0401",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        warnings=("MACHINE_SUGGESTED", "DELIVERY_ANCHOR_MISSING"),
        not_warnings=("OBJECTION_WINDOW_APPLIED",),
        messages=(
            {"contains": "completed the service check", "tags": []},
            {"contains": "will be released by 10 May", "tags": ["PAYMENT_PROMISE"]},
        ),
        notes=(
            "'Completed the service' is not a delivery confirmation: the extractor "
            "must say the anchor is missing rather than assume day 0."
        ),
    )

    # --------------------------------------------------- supplier records --
    corpus.pdf(
        f"{RECORDS}/01-udyam/UDYAM-DATA-EXTRACT-SAMPLE-SUPPLIES.pdf",
        build_udyam_extract(supplier=SUPPLIES),
        doc_type="UDYAM_DATA_EXTRACT",
        evidence="UDYAM",
        case=C01,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        text_layer_must_contain=(
            "UDYAM-SYN-000000000",
            "NOT AN UDYAM REGISTRATION CERTIFICATE",
        ),
        notes=(
            "Not a certificate: a labelled field transcription. This is the one "
            "document type we deliberately do not imitate (golden rules 9, 17)."
        ),
    )
    for party, suffix, case in (
        (MICRO, "SAMPLE-MICRO-WORKS", C02),
        (FABRICATORS, "SAMPLE-FABRICATORS", C04),
        (MAINTENANCE, "SAMPLE-MAINTENANCE", C06),
    ):
        corpus.pdf(
            f"{RECORDS}/01-udyam/UDYAM-DATA-EXTRACT-{suffix}.pdf",
            build_udyam_extract(supplier=party),
            doc_type="UDYAM_DATA_EXTRACT",
            evidence="UDYAM",
            case=case,
            expect={
                "invoice_number": None,
                "invoice_date": None,
                "amount": None,
                "supplier_gstin": party.gstin,
                "buyer_gstin": None,
                "buyer_name": None,
                "supplier_name": None,
                "delivery_date": None,
                "po_reference": None,
                "written_credit_days": None,
            },
            notes="Same template, different fictional enterprise.",
        )

    taxable = Decimal("1059322.00")
    cgst = Decimal("95338.98")
    total = Decimal("1250000.00")
    corpus.pdf(
        f"{RECORDS}/02-gst-return/GSTR-1-2026-02-EXTRACT.pdf",
        build_gst_return(
            supplier=SUPPLIES,
            form="GSTR-1",
            period="February 2026",
            filed_on="11/03/2026",
            invoice_no="INV-2026-0042",
            invoice_date="16/02/2026",
            taxable=taxable,
            cgst=cgst,
            sgst=cgst,
            total=total,
        ),
        doc_type="GST_RETURN_EXTRACT",
        evidence="GST_RETURN",
        case=C01,
        expect={
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-02-16",
            "amount": "1250000.00",
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        text_layer_must_contain=("GSTR-1", "INV-2026-0042"),
        notes=(
            "Invoice-level return detail. It shows the invoice was declared; it "
            "proves nothing about payment or acceptance."
        ),
    )
    corpus.pdf(
        f"{RECORDS}/02-gst-return/GSTR-3B-2026-02-EXTRACT.pdf",
        build_gst_return(
            supplier=SUPPLIES,
            form="GSTR-3B",
            period="February 2026",
            filed_on="20/03/2026",
            invoice_no="INV-2026-0042",
            invoice_date="16/02/2026",
            taxable=taxable,
            cgst=cgst,
            sgst=cgst,
            total=total,
        ),
        doc_type="GST_RETURN_EXTRACT",
        evidence="GST_RETURN",
        case=C01,
        expect={
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-02-16",
            "amount": "1250000.00",
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        text_layer_must_contain=("GSTR-3B", "Filed (synthetic)"),
        notes="Summary return. Same figures as the GSTR-1 extract for the invoice.",
    )

    # -------------------------------------------------------- OCR stress --
    base_pdf = corpus.root / f"{C01}/02-tax-invoice/INV-2026-0042.pdf"
    base_pages = rasterize(base_pdf, dpi=150)

    rotated = [_rotate(page, 1.8) for page in base_pages]
    images_to_pdf(
        rotated, corpus.root / f"{STRESS}/01-degraded/INV-2026-0042-rotated.pdf"
    )
    corpus._add(
        {
            "file": f"{STRESS}/01-degraded/INV-2026-0042-rotated.pdf",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "scanned",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "Same invoice rotated 1.8 degrees. No text layer: OCR only.",
        }
    )

    low = []
    for page in base_pages:
        _, _, ImageEnhance, _ = _pil()
        low.append(
            _speckle(ImageEnhance.Contrast(page).enhance(0.42), seed=11, count=400)
        )
    images_to_pdf(
        low, corpus.root / f"{STRESS}/01-degraded/INV-2026-0042-low-contrast.pdf"
    )
    corpus._add(
        {
            "file": f"{STRESS}/01-degraded/INV-2026-0042-low-contrast.pdf",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "scanned",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "Washed-out photocopy: contrast 0.42 plus speckle. Tests binarisation.",
        }
    )

    copy = []
    for page in base_pages:
        _, _, ImageEnhance, _ = _pil()
        copy.append(
            _speckle(ImageEnhance.Contrast(page).enhance(0.85), seed=3, count=1600)
        )
    images_to_pdf(
        copy, corpus.root / f"{STRESS}/01-degraded/INV-2026-0042-photocopy.pdf"
    )
    corpus._add(
        {
            "file": f"{STRESS}/01-degraded/INV-2026-0042-photocopy.pdf",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "scanned",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "Generational-copy look: speckle, streak lines, slightly grey whites.",
        }
    )

    # The totals block sits in the right third of the page. Cropping it away is
    # a deliberate honesty test: OCR must report the total as missing.
    cropped = []
    for page in base_pages:
        Image, _, _, _ = _pil()
        sheet = Image.new("RGB", page.size, (255, 255, 255))
        sheet.paste(page.crop((0, 0, int(page.width * 0.78), page.height)), (0, 0))
        cropped.append(sheet)
    images_to_pdf(
        cropped, corpus.root / f"{STRESS}/01-degraded/INV-2026-0042-cropped-total.pdf"
    )
    corpus._add(
        {
            "file": f"{STRESS}/01-degraded/INV-2026-0042-cropped-total.pdf",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "scanned",
            "text_layer": False,
            "pages": 1,
            "expected": {**invoice_expect, "amount": None},
            "notes": (
                "The right 22% (the amounts column and the Grand Total) is cut off. "
                "A good OCR reports amount as missing. A bad one guesses."
            ),
        }
    )

    stamped = [_stamp(page) for page in base_pages]
    images_to_pdf(
        stamped,
        corpus.root / f"{STRESS}/01-degraded/INV-2026-0042-stamp-over-total.pdf",
    )
    corpus._add(
        {
            "file": f"{STRESS}/01-degraded/INV-2026-0042-stamp-over-total.pdf",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "scanned",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "A rubber stamp overlaps the totals. Tests ink-over-text recovery.",
        }
    )

    photo = _shadow(_rotate(base_pages[0], -1.2))
    photo_path = corpus.root / f"{STRESS}/02-photos/INV-2026-0042-phone-photo.jpg"
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(
        photo_path,
        "JPEG",
        quality=48,
        optimize=True,
    )
    corpus._add(
        {
            "file": f"{STRESS}/02-photos/INV-2026-0042-phone-photo.jpg",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "photo",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "Handheld-photo look: tilt, edge shadow, JPEG q48. OCR input is an image.",
        }
    )

    _, _, ImageEnhance, _ = _pil()
    dark = _shadow(_rotate(base_pages[0], 1.5))
    dark = ImageEnhance.Brightness(ImageEnhance.Contrast(dark).enhance(0.75)).enhance(
        0.72
    )
    dark_path = (
        corpus.root / f"{STRESS}/02-photos/INV-2026-0042-phone-photo-low-light.jpg"
    )
    dark_path.parent.mkdir(parents=True, exist_ok=True)
    dark.save(
        dark_path,
        "JPEG",
        quality=40,
        optimize=True,
    )
    corpus._add(
        {
            "file": f"{STRESS}/02-photos/INV-2026-0042-phone-photo-low-light.jpg",
            "role": "derived",
            "doc_type": "TAX_INVOICE",
            "evidence_kind": "INVOICE",
            "case": C01,
            "render": "photo",
            "text_layer": False,
            "pages": 1,
            "expected": invoice_expect,
            "notes": "Low-light photo: brightness 0.72, contrast 0.75, JPEG q40.",
        }
    )

    # Multi-page: 30 line items, so the totals land on a later page. Every number
    # is computed here, not typed.
    mp_items = tuple(
        LineItem(
            f"Fabricated assembly, batch {index:02d}, drawing SYN-{1000 + index}",
            "7308",
            "10",
            f"{410 + index * 7}.00",
        )
        for index in range(1, 31)
    )
    mp_taxable = sum((item.amount for item in mp_items), Decimal("0.00"))
    mp_cgst, mp_sgst, _, mp_total = _invoice_totals(mp_taxable, Decimal("18.00"), None)
    corpus.pdf(
        f"{STRESS}/03-multipage/INV-2026-MP01.pdf",
        build_invoice(
            supplier=SUPPLIES,
            buyer=BUYER_CORP,
            invoice_no="INV-2026-MP01",
            invoice_date="16/02/2026",
            delivery_date="16/02/2026",
            po_no="PO-2026-0114",
            credit_days=90,
            items=mp_items,
            freight=Decimal("0.00"),
            tax_rate_pct=Decimal("18.00"),
            target_total=None,
            subtitle="ORIGINAL FOR RECIPIENT - MULTI-PAGE",
        ),
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C01,
        expect={
            "invoice_number": "INV-2026-MP01",
            "invoice_date": "2026-02-16",
            "amount": str(mp_total),
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": "90",
        },
        text_layer_must_contain=("INV-2026-MP01", inr(mp_total)),
        notes=(
            f"Three-page invoice with 30 line items. Taxable {inr(mp_taxable)}, "
            f"CGST {inr(mp_cgst)}, SGST {inr(mp_sgst)}, total {inr(mp_total)}. "
            "The total is on the last page."
        ),
    )

    # Edge cases: each one must produce a warning or a missing value, never an
    # invented one.
    ambiguous = build_invoice(
        supplier=SUPPLIES,
        buyer=BUYER_CORP,
        invoice_no="INV-2026-EDGE01",
        invoice_date="10/03/2026",
        delivery_date="04/05/2026",
        po_no="PO-2026-0114",
        credit_days=90,
        items=(
            LineItem(
                "Fabricated component, MS bracket, 12 mm", "7308", "10", "10593.22"
            ),
        ),
        freight=Decimal("0.00"),
        tax_rate_pct=Decimal("18.00"),
        target_total=None,
        subtitle="DATE AMBIGUITY TEST",
    )
    corpus.pdf(
        f"{STRESS}/04-edge-cases/INV-2026-EDGE01-ambiguous-dates.pdf",
        ambiguous,
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C01,
        expect={
            "invoice_number": "INV-2026-EDGE01",
            "invoice_date": "2026-03-10",
            "amount": "125000.00",
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-05-04",
            "po_reference": "PO-2026-0114",
            "written_credit_days": "90",
        },
        warnings=("MACHINE_SUGGESTED", "DATE_ORDER_ASSUMED"),
        text_layer_must_contain=("10/03/2026", "04/05/2026"),
        notes=(
            "Both dates are ambiguous under DD/MM/YYYY. The extractor assumes Indian "
            "order and must say so. The amount is whatever the arithmetic gives."
        ),
    )

    no_total = build_invoice(
        supplier=SUPPLIES,
        buyer=BUYER_CORP,
        invoice_no="INV-2026-EDGE02",
        invoice_date="16/02/2026",
        delivery_date="16/02/2026",
        po_no="PO-2026-0114",
        credit_days=90,
        items=(
            LineItem(
                "Fabricated component, MS bracket, 12 mm", "7308", "10", "10593.22"
            ),
        ),
        freight=Decimal("0.00"),
        tax_rate_pct=Decimal("18.00"),
        target_total=None,
        include_total=False,
        subtitle="TOTAL UNREADABLE TEST",
    )
    corpus.pdf(
        f"{STRESS}/04-edge-cases/INV-2026-EDGE02-no-total.pdf",
        no_total,
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C01,
        expect={
            "invoice_number": "INV-2026-EDGE02",
            "invoice_date": "2026-02-16",
            "amount": None,
            "supplier_gstin": SUPPLIES.gstin,
            "buyer_gstin": BUYER_CORP.gstin,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": "90",
        },
        text_layer_must_contain=("INV-2026-EDGE02",),
        notes=(
            "The Grand Total line is absent (a torn or blurred page). amount must be "
            "missing, not the taxable value and not the amount in words."
        ),
    )

    no_gstin = build_invoice(
        supplier=SUPPLIES,
        buyer=BUYER_CORP,
        invoice_no="INV-2026-EDGE03",
        invoice_date="16/02/2026",
        delivery_date="16/02/2026",
        po_no="PO-2026-0114",
        credit_days=90,
        items=(
            LineItem(
                "Fabricated component, MS bracket, 12 mm", "7308", "10", "10593.22"
            ),
        ),
        freight=Decimal("0.00"),
        tax_rate_pct=Decimal("18.00"),
        target_total=None,
        include_gstin=False,
        subtitle="GSTIN MISSING TEST",
    )
    corpus.pdf(
        f"{STRESS}/04-edge-cases/INV-2026-EDGE03-no-gstin.pdf",
        no_gstin,
        doc_type="TAX_INVOICE",
        evidence="INVOICE",
        case=C01,
        expect={
            "invoice_number": "INV-2026-EDGE03",
            "invoice_date": "2026-02-16",
            "amount": "125000.00",
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": BUYER_CORP.name,
            "supplier_name": SUPPLIES.name,
            "delivery_date": "2026-02-16",
            "po_reference": "PO-2026-0114",
            "written_credit_days": "90",
        },
        text_layer_must_contain=("INV-2026-EDGE03",),
        notes=(
            "No GSTIN anywhere. Both GSTIN fields must be missing; the user fills "
            "them in or the case is marked unregistered."
        ),
    )

    # Chat edge cases.
    ios_chat = Chat(
        title="iOS export shape",
        preamble="Synthetic iOS-format export ([date, time] Sender: text).",
        messages=(
            ChatMsg(
                "12/02/2026",
                "9:15:12 PM",
                "Buyer Stores (fictional)",
                "We received the goods today. Challan signed.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "20/02/2026",
                "10:02:44 AM",
                "Anu (fictional)",
                "Thanks. Payment is due next week.",
                SIDE_RIGHT,
            ),
        ),
    )
    corpus.chat(
        f"{STRESS}/05-chats/chat_ios_format.txt",
        ios_chat,
        case=C01,
        expect={
            "invoice_number": None,
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        warnings=("MACHINE_SUGGESTED", "OBJECTION_WINDOW_APPLIED"),
        messages=(
            {
                "contains": "We received the goods today",
                "tags": ["DELIVERY_CONFIRMATION"],
            },
        ),
        notes="Parser coverage for the iOS bracket header and a seconds-bearing time.",
        ios=True,
    )

    hinglish = Chat(
        title="Hinglish export",
        preamble=(
            "Synthetic Hinglish export. The keyword tagger is English-only today, so "
            "this file is a known-limitation test, not a failure to fix by guessing."
        ),
        messages=(
            ChatMsg(
                "03/02/2026",
                "10:05 AM",
                "Anu (fictional)",
                "40 boxes dispatch ho gaye hain, invoice SYN-INV-9001 ke against.",
                SIDE_RIGHT,
            ),
            ChatMsg(
                "03/02/2026",
                "4:30 PM",
                "Buyer Stores (fictional)",
                "Maal mil gaya, GRN sign kar diya.",
                SIDE_LEFT,
            ),
            ChatMsg(
                "12/02/2026",
                "11:20 AM",
                "Buyer Stores (fictional)",
                "6 units kharab hain, replace kar dijiye.",
                SIDE_LEFT,
            ),
        ),
    )
    corpus.chat(
        f"{STRESS}/05-chats/chat_hinglish.txt",
        hinglish,
        case=C01,
        expect={
            "invoice_number": "SYN-INV-9001",
            "invoice_date": None,
            "amount": None,
            "supplier_gstin": None,
            "buyer_gstin": None,
            "buyer_name": None,
            "supplier_name": None,
            "delivery_date": None,
            "po_reference": None,
            "written_credit_days": None,
        },
        warnings=("MACHINE_SUGGESTED", "DELIVERY_ANCHOR_MISSING", "NO_CANDIDATES"),
        messages=(),
        notes=(
            "Expected: no tags. The English keyword tagger cannot read Hinglish, and "
            "the honest output is NO_CANDIDATES plus a missing anchor. A future "
            "language layer may suggest tags; a human still confirms."
        ),
    )

    corpus._write_text(
        f"{STRESS}/05-chats/chat_group_continuation.txt",
        BANNER_TEXT
        + "\nSynthetic group export with a system line and a wrapped message.\n\n"
        + "Messages in this chat are end-to-end encrypted.\n"
        + "16/02/2026, 9:40 AM - Anu (fictional): Dispatched 100 units against invoice "
        "INV-2026-0042.\n"
        + "LR number is on the challan and the driver has the signed copy.\n"
        + "16/02/2026, 4:30 PM - Buyer Stores (fictional): Received all 100 units. "
        "GRN signed.\n",
    )
    corpus._add(
        {
            "file": f"{STRESS}/05-chats/chat_group_continuation.txt",
            "role": "chat_export",
            "doc_type": "WHATSAPP_EXPORT",
            "evidence_kind": "WHATSAPP",
            "case": C01,
            "render": "text",
            "text_layer": None,
            "pages": None,
            "expected": {
                "invoice_number": "INV-2026-0042",
                "invoice_date": None,
                "amount": None,
                "supplier_gstin": None,
                "buyer_gstin": None,
                "buyer_name": None,
                "supplier_name": None,
                "delivery_date": None,
                "po_reference": None,
                "written_credit_days": None,
            },
            "expect_kind": "WHATSAPP_EXPORT",
            "expected_warnings": ["MACHINE_SUGGESTED", "OBJECTION_WINDOW_APPLIED"],
            "not_expected_warnings": [],
            "expected_messages": [
                {"contains": "LR number is on the challan", "tags": []},
                {
                    "contains": "Received all 100 units",
                    "tags": ["DELIVERY_CONFIRMATION"],
                },
            ],
            "notes": (
                "The wrapped line must be joined onto the first message, and the "
                "system line must not become a message."
            ),
        }
    )


def write_readmes(corpus: Corpus) -> None:
    corpus._write_text(
        f"{C01}/README.md",
        """# Case 01 - Sample Supplies Pvt Ltd

The golden-path demo. An overdue invoice, a 90-day term that cannot move the
statutory clock, delivery proof, and a WhatsApp promise to pay.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0114.pdf` | the order and the written Net-90 term | `PO` |
| `02-tax-invoice/INV-2026-0042.pdf` | the payable, 12,50,000.00 | `INVOICE` |
| `03-delivery/DC-2026-0088.pdf` | dispatched and received on 16/02/2026 | `DELIVERY_PROOF` |
| `03-delivery/GRN-2026-0088.pdf` | the buyer's own receipt, no rejection | `DELIVERY_PROOF` |
| `04-whatsapp/chat_delivery_and_promise.txt` | delivery plus a promise on 10/04/2026 | `WHATSAPP` |
| `../supplier-records/01-udyam/` | the enterprise's declared particulars | `UDYAM` |

Every `.pdf` has a `.txt` twin generated from the same content. The Udyam page
is a data extract, not a certificate, by design.

This case matches `contracts/fixtures/case_01.request.json` on dates and amount.
The supplier GSTIN is a distinct placeholder because the preset's buyers reuse
neighbouring numbers.
""",
    )
    corpus._write_text(
        f"{C02}/README.md",
        """# Case 02 - Sample Micro Works

A micro enterprise, a 30-day term, and a written objection nine days after
delivery. The objection is inside the configured 15-day window; the replacement
arrives on day 18.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0209.pdf` | the order and the Net-30 term | `PO` |
| `02-tax-invoice/INV-2026-0209.pdf` | the payable, 3,00,000.00 | `INVOICE` |
| `03-delivery/DC-2026-0209.pdf` | delivered 15/03/2026 | `DELIVERY_PROOF` |
| `04-objection/WRITTEN-OBJECTION-2026-03-24.pdf` | the buyer's written objection | (objection record) |
| `05-whatsapp/chat_defect_day9.txt` | the same objection in chat, day 9 | `WHATSAPP` |
| `05-whatsapp/chat_late_objection.txt` | a negative control: day 60 | `WHATSAPP` |

`chat_late_objection.txt` is deliberately the same story told late. Its
`LATE_COMPLAINT` tag is a suggestion; the engine decides whether the objection
qualifies.

This case matches `contracts/fixtures/case_02.request.json` on dates, amount and
the objection's raised and resolved dates.
""",
    )
    corpus._write_text(
        f"{C04}/README.md",
        """# Case 04 - Sample Fabricators Pvt Ltd

An invoice with an ambiguous date (10/03/2026) and a part payment recorded on
15/05/2026.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0310.pdf` | the order | `PO` |
| `02-tax-invoice/INV-2026-0310.pdf` | the payable, 5,00,000.00 | `INVOICE` |
| `03-payment/REMITTANCE-ADVICE-2026-05-15.pdf` | 1,50,000.00 paid, 3,50,000.00 left | (part payment) |

There is no delivery challan here on purpose: case 04's delivery proof in the
preset is an LR, which is not in this corpus yet. Upload only what you hold.

This case matches `contracts/fixtures/case_04.request.json` on dates, amount and
the part-payment date and amount.
""",
    )
    corpus._write_text(
        f"{C06}/README.md",
        """# Case 06 - Sample Maintenance Services

A service invoice with **no delivery date and no delivery proof**. This is the
case that shows the system refusing to invent an anchor.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0401.pdf` | the order | `PO` |
| `02-tax-invoice/INV-2026-0401.pdf` | the payable, 2,50,000.00 | `INVOICE` |
| `03-whatsapp/chat_no_delivery_confirmation.txt` | a promise, but no delivery line | `WHATSAPP` |

The chat's technician line ("completed the service check") is deliberately not
a delivery confirmation. The extractor must raise `DELIVERY_ANCHOR_MISSING`.

This case matches `contracts/fixtures/case_06.request.json` on dates and amount.
""",
    )
    corpus._write_text(
        f"{RECORDS}/README.md",
        """# Supplier records

Documents that belong to the enterprise, not to one invoice.

| Folder | Document | Notes |
|---|---|---|
| `01-udyam/` | `UDYAM-DATA-EXTRACT-*.pdf` | **Not a certificate.** A labelled transcription of the fields a supplier reads off their own Udyam certificate. SamadhaanOS does not generate government documents. |
| `02-gst-return/` | `GSTR-1-*.pdf`, `GSTR-3B-*.pdf` | Synthetic return extracts showing that an invoice was declared. Not GST portal documents, not filings. |

One Udyam extract per fictional enterprise, so each case packet is complete.
""",
    )
    corpus._write_text(
        f"{STRESS}/README.md",
        """# OCR stress set

These files are for the OCR layer, not for the case flow. Each one is derived
from a clean document by a degradation that a real supplier's paperwork suffers.

| File | What it tests |
|---|---|
| `01-degraded/...-rotated.pdf` | 1.8-degree skew; deskew before line segmentation |
| `01-degraded/...-low-contrast.pdf` | washed-out photocopy; binarisation and thresholding |
| `01-degraded/...-photocopy.pdf` | generational copy with speckle and streak lines |
| `01-degraded/...-cropped-total.pdf` | the amounts column is cut off. **Amount must come back missing.** |
| `01-degraded/...-stamp-over-total.pdf` | a rubber stamp over the totals |
| `02-photos/...-phone-photo.jpg` | tilt, edge shadow, JPEG q48 |
| `02-photos/...-phone-photo-low-light.jpg` | brightness 0.72, contrast 0.75, JPEG q40 |
| `03-multipage/INV-2026-MP01.pdf` | 30 line items; the total is on the last page |
| `04-edge-cases/INV-2026-EDGE01-ambiguous-dates.pdf` | 10/03/2026 and 04/05/2026: both readings are valid |
| `04-edge-cases/INV-2026-EDGE02-no-total.pdf` | no Grand Total line at all |
| `04-edge-cases/INV-2026-EDGE03-no-gstin.pdf` | no GSTIN on the page |
| `05-chats/chat_ios_format.txt` | iOS `[date, time] Sender:` header |
| `05-chats/chat_hinglish.txt` | English-only tagger meets Hinglish; expect `NO_CANDIDATES` |
| `05-chats/chat_group_continuation.txt` | system line plus a wrapped message |

`MANIFEST.json` holds the ground truth. For every file it gives `expected`, the
values a correct reader should produce, and `notes` saying what the specific
degradation is meant to defeat. Compare your OCR output against it; do not
tune the manifest to make a reading pass.
""",
    )


# ------------------------------------------------------------------- main --


def clean(root: Path) -> None:
    for name in (C01, C02, C04, C06, RECORDS, STRESS):
        target = root / name
        if target.exists():
            shutil.rmtree(target)


def main() -> int:
    root = HERE
    clean(root)
    corpus = Corpus(root)
    build_corpus(corpus)
    write_readmes(corpus)

    MANIFEST["files"] = sorted(corpus.files, key=lambda entry: entry["file"])
    MANIFEST["cases"] = [
        {
            "id": C01,
            "preset": "case_01",
            "story": "Overdue invoice, Net-90 term, delivery proof, WhatsApp promise.",
        },
        {
            "id": C02,
            "preset": "case_02",
            "story": "Micro enterprise, written objection on day 9, resolved on day 18.",
        },
        {
            "id": C04,
            "preset": "case_04",
            "story": "Ambiguous date, part payment of 1,50,000 on 15/05/2026.",
        },
        {
            "id": C06,
            "preset": "case_06",
            "story": "Service invoice with no delivery date and no delivery proof.",
        },
    ]
    (root / "MANIFEST.json").write_text(
        json.dumps(MANIFEST, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(corpus.files)} manifest entries under {root}")
    print(f"manifest: {root / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
