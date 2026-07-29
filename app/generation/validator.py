"""Layout constraint checks beyond what Pydantic/JSON-schema already enforce."""

import re

from app.generation.schema import Article

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

HEADLINE_MAX_WORDS = 8
SUBHEADLINE_MAX_WORDS = 15
BODY_SECTION_MAX_WORDS = 60
CTA_MAX_WORDS = 10
TABLE_MAX_COUNT = 2
TABLE_MAX_ROWS = 6
TABLE_MAX_COLUMNS = 5


def _word_count(text: str) -> int:
    return len(text.split())


def validate_constraints(article: Article) -> list[str]:
    violations: list[str] = []

    if _word_count(article.headline) > HEADLINE_MAX_WORDS:
        violations.append(f"headline exceeds {HEADLINE_MAX_WORDS} words")
    if _word_count(article.subheadline) > SUBHEADLINE_MAX_WORDS:
        violations.append(f"subheadline exceeds {SUBHEADLINE_MAX_WORDS} words")
    if _word_count(article.cta) > CTA_MAX_WORDS:
        violations.append(f"cta exceeds {CTA_MAX_WORDS} words")

    for i, section in enumerate(article.body_sections):
        if _word_count(section.text) > BODY_SECTION_MAX_WORDS:
            violations.append(f"body_sections[{i}] ('{section.heading}') exceeds {BODY_SECTION_MAX_WORDS} words")

    if not HEX_COLOR_RE.match(article.theme.primary_color):
        violations.append("theme.primary_color is not a valid hex color")
    if not HEX_COLOR_RE.match(article.theme.secondary_color):
        violations.append("theme.secondary_color is not a valid hex color")

    if len(article.tables) > TABLE_MAX_COUNT:
        violations.append(f"tables has {len(article.tables)} entries, exceeds max {TABLE_MAX_COUNT}")

    for i, table in enumerate(article.tables):
        if len(table.rows) > TABLE_MAX_ROWS:
            violations.append(f"tables[{i}] ('{table.title}') has {len(table.rows)} rows, exceeds max {TABLE_MAX_ROWS}")
        if len(table.headers) > TABLE_MAX_COLUMNS:
            violations.append(f"tables[{i}] ('{table.title}') has {len(table.headers)} columns, exceeds max {TABLE_MAX_COLUMNS}")
        for r, row in enumerate(table.rows):
            if len(row) != len(table.headers):
                violations.append(f"tables[{i}] ('{table.title}') row {r} has {len(row)} cells, expected {len(table.headers)} to match headers")

    return violations
