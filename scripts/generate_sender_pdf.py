"""Generate a synthetic Sender context PDF: "Nexus Vision AI".

Produces a multi-page, multi-modal PDF (text, a multi-row/column data table,
and an embedded diagram image) to use as test/demo input for the
marketing-app ingestion pipeline (`POST /companies/{name}/documents`).

Usage:
    python scripts/generate_sender_pdf.py
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
PDF_PATH = OUTPUT_DIR / "sender_company_context.pdf"
DIAGRAM_PATH = OUTPUT_DIR / "nexus_architecture_diagram.png"

NAVY_HEX = "#1E3A8A"
LIGHT_NAVY_HEX = "#DBEAFE"
NAVY = colors.HexColor(NAVY_HEX)
LIGHT_NAVY = colors.HexColor(LIGHT_NAVY_HEX)
DARK_TEXT = colors.HexColor("#111827")


# --------------------------------------------------------------------------
# Synthetic image asset (architecture diagram)
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


def _draw_box(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, text: str, font: ImageFont.ImageFont) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=NAVY_HEX, outline="#0F1F45", width=3)
    lines = text.split("\n")
    line_height = 24
    total_height = line_height * len(lines)
    ty = y + (h - total_height) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        tx = x + (w - tw) / 2
        draw.text((tx, ty), line, fill="white", font=font)
        ty += line_height


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple, end: tuple, width: int = 4) -> None:
    draw.line([start, end], fill="#374151", width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    arrow_len = 16
    for delta in (0.5, -0.5):
        ax = end[0] - arrow_len * math.cos(angle - delta)
        ay = end[1] - arrow_len * math.sin(angle - delta)
        draw.line([end, (ax, ay)], fill="#374151", width=width)


def generate_architecture_diagram(path: Path) -> None:
    """Synthesize a 4-stage inference pipeline diagram as a PNG asset."""
    width, height = 1200, 420
    img = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    title_font = _load_font(26)
    label_font = _load_font(17)

    draw.text((30, 20), "NexusVision AI \u2014 Inference Pipeline Architecture", fill=NAVY_HEX, font=title_font)

    box_w, box_h = 230, 130
    gap = 60
    y = 160
    stages = [
        "Camera / Sensor\nInput",
        "Edge Inference\n(NexusScan Edge)",
        "NexusVision\nCloud API",
        "Analytics\nDashboard",
    ]
    x = 40
    centers = []
    for stage in stages:
        _draw_box(draw, x, y, box_w, box_h, stage, label_font)
        centers.append((x + box_w, y + box_h // 2))
        x += box_w + gap

    for (end_x, end_y), start_x in zip(centers[:-1], [c[0] for c in centers[:-1]]):
        arrow_start = (start_x, end_y)
        arrow_end = (start_x + gap, end_y)
        _draw_arrow(draw, arrow_start, arrow_end)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


# --------------------------------------------------------------------------
# Document content
# --------------------------------------------------------------------------

def build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "NexusTitle", parent=base["Title"], textColor=NAVY, fontSize=24, spaceAfter=6
        ),
        "Subtitle": ParagraphStyle(
            "NexusSubtitle", parent=base["Normal"], textColor=DARK_TEXT, fontSize=12, spaceAfter=18
        ),
        "Heading": ParagraphStyle(
            "NexusHeading",
            parent=base["Heading2"],
            textColor=NAVY,
            fontSize=15,
            spaceBefore=18,
            spaceAfter=8,
        ),
        "Body": ParagraphStyle(
            "NexusBody", parent=base["Normal"], textColor=DARK_TEXT, fontSize=10.5, leading=15
        ),
        "ProductName": ParagraphStyle(
            "NexusProductName",
            parent=base["Normal"],
            textColor=NAVY,
            fontSize=11.5,
            leading=15,
            spaceBefore=6,
        ),
    }
    return styles


def build_spec_table(styles: dict) -> Table:
    header = ["Product Line", "Deployment Model", "Model Accuracy", "Inference Latency", "Max Throughput"]
    rows = [
        ["NexusScan Edge", "On-Prem Edge Device", "98.7%", "12 ms", "240 fps"],
        ["NexusVision Cloud Platform", "Cloud API", "99.2%", "45 ms", "1,200 req/s"],
        ["NexusGuard Retail", "Hybrid (Edge + Cloud)", "97.5%", "18 ms", "180 fps"],
        ["NexusFlow Industrial", "On-Prem", "99.4%", "9 ms", "300 fps"],
    ]
    data = [header] + rows

    table = Table(data, colWidths=[1.7 * inch, 1.5 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
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
            style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_NAVY))
    table.setStyle(TableStyle(style))
    return table


PRODUCTS = [
    (
        "NexusScan Edge",
        "On-device computer vision appliance for real-time quality inspection on "
        "manufacturing lines.",
        [
            "Sub-15ms inference latency on-device",
            "Runs on ARM / NVIDIA Jetson edge hardware",
            "Fully offline-capable, no cloud dependency",
            "Auto-retrains from flagged defect samples",
        ],
    ),
    (
        "NexusVision Cloud Platform",
        "Scalable cloud API for large-scale image and video analytics across "
        "multi-site operations.",
        [
            "REST/gRPC API with SDKs for Python, Java, and Go",
            "Auto-scaling inference clusters",
            "Built-in data labeling and active-learning loop",
            "SOC 2 Type II compliant",
        ],
    ),
    (
        "NexusGuard Retail",
        "Loss-prevention and shelf-monitoring vision suite built for retail "
        "environments.",
        [
            "Real-time shelf out-of-stock detection",
            "Integrates with existing IP camera infrastructure",
            "Configurable alerting via webhook, Slack, or Teams",
        ],
    ),
    (
        "NexusFlow Industrial",
        "High-throughput defect detection for industrial production lines.",
        [
            "300 fps inline inspection",
            "Sub-pixel defect localization",
            "Integrates with PLC/SCADA systems for automatic line-stop",
        ],
    ),
]


def build_story(styles: dict) -> list:
    story = []

    story.append(Paragraph("Nexus Vision AI", styles["Title"]))
    story.append(
        Paragraph(
            "Enterprise computer vision software for manufacturing, retail, and logistics operations.",
            styles["Subtitle"],
        )
    )

    story.append(Paragraph("Company Overview", styles["Heading"]))
    story.append(
        Paragraph(
            "Nexus Vision AI builds production-grade computer vision software that turns camera "
            "and sensor feeds into real-time operational intelligence. Founded in 2019, the company "
            "serves enterprise manufacturing, retail, and logistics customers across North America "
            "and Europe, with over 400 production deployments processing more than 50 million frames "
            "per day. Our platform spans edge inference appliances to a fully managed cloud API, so "
            "customers can deploy computer vision wherever their operations require it.",
            styles["Body"],
        )
    )

    story.append(Paragraph("Product Portfolio", styles["Heading"]))
    for name, description, features in PRODUCTS:
        story.append(Paragraph(name, styles["ProductName"]))
        story.append(Paragraph(description, styles["Body"]))
        story.append(
            ListFlowable(
                [ListItem(Paragraph(feature, styles["Body"]), leftIndent=6) for feature in features],
                bulletType="bullet",
                leftIndent=18,
            )
        )
        story.append(Spacer(1, 6))

    story.append(Paragraph("Technical Specifications", styles["Heading"]))
    story.append(
        Paragraph(
            "Benchmark figures below are measured on representative production workloads across our "
            "current product lines.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(build_spec_table(styles))

    story.append(PageBreak())

    story.append(Paragraph("System Architecture", styles["Heading"]))
    story.append(
        Paragraph(
            "The diagram below illustrates the standard NexusVision inference pipeline, from camera "
            "input through edge inference to cloud aggregation and analytics.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 10))
    story.append(Image(str(DIAGRAM_PATH), width=6.4 * inch, height=2.24 * inch))
    story.append(Spacer(1, 14))
    story.append(Paragraph("Why Nexus Vision AI", styles["Heading"]))
    story.append(
        Paragraph(
            "Customers choose Nexus Vision AI to replace manual visual inspection and monitoring "
            "workflows with consistent, auditable, real-time computer vision -- deployable at the "
            "edge, in the cloud, or both, without vendor lock-in to a single hardware platform.",
            styles["Body"],
        )
    )

    return story


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_architecture_diagram(DIAGRAM_PATH)

    styles = build_styles()
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title="Nexus Vision AI - Company Context",
    )
    doc.build(build_story(styles))
    print(f"Wrote {PDF_PATH}")
    print(f"Wrote {DIAGRAM_PATH}")


if __name__ == "__main__":
    main()
