"""LLM client abstraction.

Google Gemini (structured JSON output via `response_schema`) for the
prototype; swap for an Azure OpenAI chat deployment (structured outputs /
JSON mode) in the Azure target architecture -- callers only depend on
`generate_structured()`.
"""

import json
from typing import Protocol, Type, TypeVar

from pydantic import BaseModel

from app.core.config import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMClient(Protocol):
    def generate_structured(self, system: str, user_message: str, response_schema: Type[ModelT]) -> ModelT: ...


class GeminiLLMClient:
    def __init__(self, settings: Settings):
        from google import genai

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    def generate_structured(self, system: str, user_message: str, response_schema: Type[ModelT]) -> ModelT:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        return response_schema.model_validate(json.loads(response.text))
