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


class ArticleDraft(BaseModel):
    """The schema handed to Gemini as `response_schema` for structured output."""

    headline: str = Field(description="<=8 words")
    subheadline: str = Field(description="<=15 words")
    body_sections: list[BodySection] = Field(min_length=1)
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
    image_slots: list[ImageSlot] = Field(min_length=1)
    theme: Theme
    cta: str

    @classmethod
    def from_draft(cls, draft: ArticleDraft) -> "Article":
        return cls(
            headline=draft.headline,
            subheadline=draft.subheadline,
            body_sections=draft.body_sections,
            image_slots=[ImageSlot(slot_name=s.slot_name) for s in draft.image_slots],
            theme=draft.theme,
            cta=draft.cta,
        )
