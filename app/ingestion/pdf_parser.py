"""PDF parsing: text, tables and images via PyMuPDF.

Prototype-scope heuristics (documented as known limitations in the README):
- Tables are flattened to a simple pipe-delimited text block, not preserved
  as structured cell data.
- The logo is guessed as the largest image found on the document's first
  page. A production system would use layout-aware extraction (e.g. Azure
  Document Intelligence) and/or a logo-detection model instead.
"""

from dataclasses import dataclass, field

import fitz  # PyMuPDF


@dataclass
class ExtractedImage:
    index: int
    page_number: int
    ext: str
    content: bytes
    width: int
    height: int
    is_logo: bool = False


@dataclass
class ParsedDocument:
    page_texts: list[str] = field(default_factory=list)
    table_texts: list[str] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(t for t in self.page_texts + self.table_texts if t.strip())


def parse_pdf(content: bytes) -> ParsedDocument:
    doc = fitz.open(stream=content, filetype="pdf")
    parsed = ParsedDocument()

    try:
        for page_index, page in enumerate(doc):
            parsed.page_texts.append(page.get_text().strip())
            parsed.table_texts.extend(_extract_tables(page))
            parsed.images.extend(_extract_images(doc, page, page_index))
    finally:
        doc.close()

    _tag_logo(parsed.images)
    return parsed


def _extract_tables(page: "fitz.Page") -> list[str]:
    tables_text: list[str] = []
    try:
        finder = page.find_tables()
    except Exception:
        return tables_text
    for table in finder.tables:
        rows = table.extract()
        lines = [" | ".join(str(cell) if cell is not None else "" for cell in row) for row in rows]
        if lines:
            tables_text.append("\n".join(lines))
    return tables_text


def _extract_images(doc: "fitz.Document", page: "fitz.Page", page_index: int) -> list[ExtractedImage]:
    images: list[ExtractedImage] = []
    for image_index, image_info in enumerate(page.get_images(full=True)):
        xref = image_info[0]
        try:
            base_image = doc.extract_image(xref)
        except Exception:
            continue
        images.append(
            ExtractedImage(
                index=image_index,
                page_number=page_index,
                ext=base_image["ext"],
                content=base_image["image"],
                width=base_image.get("width", 0),
                height=base_image.get("height", 0),
            )
        )
    return images


def _tag_logo(images: list[ExtractedImage]) -> None:
    first_page_images = [img for img in images if img.page_number == 0]
    if not first_page_images:
        return
    largest = max(first_page_images, key=lambda img: img.width * img.height)
    largest.is_logo = True
