"""Generate a synthetic Receiver context PDF: "Apex Global Logistics".

Produces a multi-page, multi-modal PDF (text, a multi-row/column metrics
table, and an embedded logo image) to use as test/demo input for the
marketing-app ingestion pipeline (`POST /companies/{name}/documents`).

Usage:
    python scripts/generate_receiver_pdf.py
"""

import math
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
PDF_PATH = OUTPUT_DIR / "receiver_company_context.pdf"
LOGO_PATH = OUTPUT_DIR / "apex_logo.png"

AMBER_HEX = "#F97316"
LIGHT_AMBER_HEX = "#FFEDD5"
AMBER = colors.HexColor(AMBER_HEX)
LIGHT_AMBER = colors.HexColor(LIGHT_AMBER_HEX)
DARK_TEXT = colors.HexColor("#111827")


# --------------------------------------------------------------------------
# Synthetic image asset (company logo)
# --------------------------------------------------------------------------

def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def generate_logo(path: Path) -> None:
    """Synthesize a simple hexagon wordmark logo as a PNG asset."""
    width, height = 500, 500
    img = PILImage.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    cx, cy, r = width / 2, height / 2 - 30, 190
    hexagon = [
        (cx + r * 0.95 * math.cos(angle), cy + r * 0.95 * math.sin(angle)) for angle in _hex_angles()
    ]
    draw.polygon(hexagon, fill=AMBER_HEX, outline="#C2410C", width=6)

    # abstract "box/crate" glyph in the center
    box_w, box_h = 150, 110
    bx, by = cx - box_w / 2, cy - box_h / 2
    draw.rectangle([bx, by, bx + box_w, by + box_h], outline="white", width=8)
    draw.line([bx, by + box_h * 0.35, bx + box_w, by + box_h * 0.35], fill="white", width=6)
    draw.line([cx, by, cx, by + box_h * 0.35], fill="white", width=6)

    wordmark_font = _load_font(56)
    tagline_font = _load_font(24)
    text = "APEX"
    bbox = draw.textbbox((0, 0), text, font=wordmark_font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2, cy + r + 20), text, fill="#111827", font=wordmark_font)

    tagline = "GLOBAL LOGISTICS"
    bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2, cy + r + 90), tagline, fill=AMBER_HEX, font=tagline_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _hex_angles():
    return [math.radians(60 * i - 90) for i in range(6)]


# --------------------------------------------------------------------------
# Document content
# --------------------------------------------------------------------------

def build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "ApexTitle", parent=base["Title"], textColor=AMBER, fontSize=24, spaceAfter=6
        ),
        "Subtitle": ParagraphStyle(
            "ApexSubtitle", parent=base["Normal"], textColor=DARK_TEXT, fontSize=12, spaceAfter=18
        ),
        "Heading": ParagraphStyle(
            "ApexHeading",
            parent=base["Heading2"],
            textColor=AMBER,
            fontSize=15,
            spaceBefore=18,
            spaceAfter=8,
        ),
        "Body": ParagraphStyle(
            "ApexBody", parent=base["Normal"], textColor=DARK_TEXT, fontSize=10.5, leading=15
        ),
    }
    return styles


def build_metrics_table(styles: dict) -> Table:
    header = ["Facility", "Region", "Daily Volume (parcels)", "Manual Rescan Rate", "Est. Annual Rescan Cost"]
    rows = [
        ["Chicago Hub", "Midwest US", "210,000", "7.8%", "$2.94M"],
        ["Rotterdam DC", "EU-West", "165,000", "9.1%", "$2.63M"],
        ["Dallas Fulfillment", "South US", "190,000", "6.4%", "$2.20M"],
        ["Leipzig Cross-Dock", "EU-Central", "140,000", "8.5%", "$1.83M"],
    ]
    data = [header] + rows

    table = Table(data, colWidths=[1.5 * inch, 1.1 * inch, 1.5 * inch, 1.3 * inch, 1.5 * inch])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), AMBER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#9CA3AF")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_AMBER))
    table.setStyle(TableStyle(style))
    return table


PAIN_POINTS = [
    "Facility bottlenecks during peak season cause dock-to-stock delays averaging 6.4 hours.",
    "Manual barcode rescans due to damaged or misaligned labels cost approximately $4.80 per "
    "parcel in added labor.",
    "Inbound quality inspection is fully manual across 60% of facilities, creating inconsistent "
    "defect capture between sites.",
    "Limited real-time visibility into shelf and dock congestion keeps staffing reactive rather "
    "than predictive.",
]


def build_story(styles: dict) -> list:
    story = []

    story.append(Paragraph("Apex Global Logistics", styles["Title"]))
    story.append(
        Paragraph(
            "Global fulfillment and cross-dock logistics network for enterprise e-commerce clients.",
            styles["Subtitle"],
        )
    )
    story.append(Image(str(LOGO_PATH), width=1.6 * inch, height=1.6 * inch))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Operational Summary", styles["Heading"]))
    story.append(
        Paragraph(
            "Apex Global Logistics operates a network of 42 fulfillment and cross-dock facilities "
            "across North America and Europe, processing over 3.2 million parcels daily on behalf "
            "of enterprise e-commerce clients. The network combines high-volume regional hubs with "
            "smaller cross-dock sites optimized for last-mile handoff, and is undergoing a "
            "multi-year modernization of its inbound receiving and quality-inspection workflows.",
            styles["Body"],
        )
    )

    story.append(Paragraph("Business Pain Points", styles["Heading"]))
    story.append(
        ListFlowable(
            [ListItem(Paragraph(point, styles["Body"]), leftIndent=6) for point in PAIN_POINTS],
            bulletType="bullet",
            leftIndent=18,
        )
    )

    story.append(Paragraph("Facility Metrics", styles["Heading"]))
    story.append(
        Paragraph(
            "Rescan-cost figures below are estimated from Q2 2026 labor and throughput data across "
            "our four highest-volume facilities.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(build_metrics_table(styles))

    story.append(PageBreak())

    story.append(Paragraph("2026 Digital Transformation Priorities", styles["Heading"]))
    story.append(
        Paragraph(
            "Apex Global Logistics has allocated budget in fiscal year 2026 to modernize inbound "
            "receiving, with a stated priority on reducing manual rescan labor and improving "
            "predictive visibility into facility congestion. Leadership has expressed openness to "
            "automated visual inspection and analytics tooling that can integrate with existing "
            "warehouse management systems without a full infrastructure overhaul.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph("Procurement Contact", styles["Heading"]))
    story.append(
        Paragraph(
            "Vendor evaluations for this initiative are being coordinated through the Apex Global "
            "Logistics Operations Technology team, with a target vendor shortlist by the end of Q3 2026.",
            styles["Body"],
        )
    )

    return story


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_logo(LOGO_PATH)

    styles = build_styles()
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title="Apex Global Logistics - Company Context",
    )
    doc.build(build_story(styles))
    print(f"Wrote {PDF_PATH}")
    print(f"Wrote {LOGO_PATH}")


if __name__ == "__main__":
    main()
