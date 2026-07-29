"""Live web research for a receiver company that has no uploaded context PDF.

Primary path: Gemini's native Google Search grounding tool via the raw `google-genai`
SDK (not LangChain -- `langchain_google_genai` doesn't currently expose grounding-tool
config any more simply than calling the SDK directly for this one-shot use). Grounded
search sits on a separate, much stricter quota than plain text generation on Gemini's
free tier -- a `RESOURCE_EXHAUSTED` 429 here is a real, expected operating condition,
not a bug.

Fallback path: if that quota is exhausted (429) and a free-tier Tavily API key is
configured (`TAVILY_API_KEY`), research via Tavily's search API instead -- no Gemini
tokens are spent on this step, so its usage is reported as zero. If Tavily isn't
configured, the original quota error propagates as `google.genai.errors.APIError`,
same as before.

Both paths return text shaped like retrieved vector-store chunks (`list[str]`), so
`build_user_prompt` doesn't need to know whether receiver context came from an
uploaded PDF, Google Search, or Tavily -- see the grounding rule in `SYSTEM_PROMPT`,
which treats every source identically.
"""
import logging

logger = logging.getLogger(__name__)


class CompanyResearchClient:
    def __init__(self, api_key: str, model: str, tavily_api_key: str | None = None):
        self._api_key = api_key
        self._model = model
        self._tavily_api_key = tavily_api_key

    def research(self, company_name: str) -> tuple[list[str], dict]:
        """Returns (context_chunks, usage) where usage has input_tokens/output_tokens."""
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        tool = types.Tool(google_search=types.GoogleSearch())
        prompt = (
            f'Research the company "{company_name}" using web search. Write a factual, '
            "neutral summary (200-400 words) covering: what it does/sells, its industry, "
            "its likely customers, and any publicly known operational challenges or "
            "priorities relevant to a B2B vendor pitching to them. Do not invent anything "
            "you can't find; if search results are thin, say so briefly rather than padding."
        )
        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[tool]),
            )
        except genai_errors.APIError as exc:
            if self._tavily_api_key and exc.code == 429:
                try:
                    return self._tavily_research(company_name), {"input_tokens": 0, "output_tokens": 0}
                except Exception:
                    # Tavily itself failed (bad key, network error, etc.) -- fall back to
                    # the original quota error rather than surfacing an unrelated 500;
                    # its message already points the caller at the PDF-upload workaround.
                    logger.warning("Tavily fallback research failed for %r", company_name, exc_info=True)
                    raise exc from None
            raise
        text = (response.text or "").strip()
        usage = response.usage_metadata
        return (
            [text] if text else [],
            {
                "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
                "output_tokens": (usage.candidates_token_count or 0) if usage else 0,
            },
        )

    def _tavily_research(self, company_name: str) -> list[str]:
        """Free-tier web search fallback (no Gemini tokens spent) via api.tavily.com."""
        import httpx

        query = f'"{company_name}" company overview industry products customers'
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": 5,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()

        chunks: list[str] = []
        answer = (data.get("answer") or "").strip()
        if answer:
            chunks.append(answer)
        for result in data.get("results", []):
            content = (result.get("content") or "").strip()
            if content:
                title = (result.get("title") or "").strip()
                chunks.append(f"{title}: {content}" if title else content)
        return chunks
