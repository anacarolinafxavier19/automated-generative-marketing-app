"""Layout/article JSON schema.

This is a representative pre-defined template standing in for the client's
real publishing template. The LLM only ever chooses *which* image slot it
wants (from a fixed vocabulary, via `ArticleDraft`) -- it never invents an
asset path. The real `asset_ref` is resolved server-side (see
`_resolve_image_assets` in generate.py) against assets actually extracted
from the uploaded PDFs, producing the final `Article`, so the response can
never point at a hallucinated image.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ImageSlotName = Literal["hero", "sender_logo", "receiver_logo"]


class BodySection(BaseModel):
    heading: str
    text: str


class Theme(BaseModel):
    primary_color: str
    secondary_color: str


class ImageSlotRequest(BaseModel):
    slot_name: ImageSlotName


class TableData(BaseModel):
    """An optional comparison/spec table (e.g. before-vs-after, plan tiers).

    Every cell is free text chosen by the model, but -- same grounding rule as
    everything else -- only ever from facts present in the retrieved/researched
    context, never invented. Row/column counts are capped in validator.py to
    keep the table from blowing out the rendered layout.
    """

    title: str
    headers: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)


class ArticleDraft(BaseModel):
    """The schema handed to Gemini as `response_schema` for structured output."""

    headline: str = Field(description="<=8 words")
    subheadline: str = Field(description="<=15 words")
    body_sections: list[BodySection] = Field(min_length=1)
    tables: list[TableData] = Field(default_factory=list, description="0-2 optional tables; omit if nothing table-worthy")
    image_slots: list[ImageSlotRequest] = Field(min_length=1)
    theme: Theme
    cta: str = Field(description="<=10 words")


class ImageSlot(BaseModel):
    slot_name: ImageSlotName
    asset_ref: Optional[str] = None


class Article(BaseModel):
    """The final response: `ArticleDraft` plus server-resolved image assets."""

    headline: str
    subheadline: str
    body_sections: list[BodySection] = Field(min_length=1)
    tables: list[TableData] = Field(default_factory=list)
    image_slots: list[ImageSlot] = Field(min_length=1)
    theme: Theme
    cta: str

    @classmethod
    def from_draft(cls, draft: ArticleDraft) -> "Article":
        return cls(
            headline=draft.headline,
            subheadline=draft.subheadline,
            body_sections=draft.body_sections,
            tables=draft.tables,
            image_slots=[ImageSlot(slot_name=s.slot_name) for s in draft.image_slots],
            theme=draft.theme,
            cta=draft.cta,
        )
