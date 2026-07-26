from app.generation.schema import Article, BodySection, ImageSlot, Theme
from app.generation.validator import validate_constraints


def _make_article(**overrides) -> Article:
    defaults = dict(
        headline="Short punchy headline",
        subheadline="A concise subheadline under the limit",
        body_sections=[BodySection(heading="Why it matters", text="A short body paragraph.")],
        image_slots=[ImageSlot(slot_name="sender_logo")],
        theme=Theme(primary_color="#1A2B3C", secondary_color="#FFFFFF"),
        cta="Get in touch today",
    )
    defaults.update(overrides)
    return Article(**defaults)


def test_valid_article_has_no_violations():
    article = _make_article()
    assert validate_constraints(article) == []


def test_headline_word_limit_is_enforced():
    article = _make_article(headline="This headline definitely has way more than eight words in it")
    violations = validate_constraints(article)
    assert any("headline" in v for v in violations)


def test_body_section_word_limit_is_enforced():
    long_text = " ".join(["word"] * 61)
    article = _make_article(body_sections=[BodySection(heading="Section", text=long_text)])
    violations = validate_constraints(article)
    assert any("body_sections[0]" in v for v in violations)


def test_invalid_hex_color_is_flagged():
    article = _make_article(theme=Theme(primary_color="blue", secondary_color="#FFFFFF"))
    violations = validate_constraints(article)
    assert any("primary_color" in v for v in violations)
