import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.genai import errors as genai_errors
from langchain_community.vectorstores.chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.config import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import Client as LangSmithClient
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.dependencies import get_langsmith_client, get_llm_client, get_metadata_store, get_research_client, get_vector_store
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.generation.research import CompanyResearchClient
from app.generation.schema import Article, ArticleDraft
from app.generation.validator import validate_constraints
from app.storage.metadata_db import GenerationMetricsRecord, MetadataStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])


class GenerateRequest(BaseModel):
    sender_company: str
    receiver_company: str
    prompt: str


@router.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to the Marketing App API"}


@router.post("/generate")
def generate_article(
    request: GenerateRequest,
    settings: Settings = Depends(get_settings),
    vector_store: Chroma = Depends(get_vector_store),
    metadata_store: MetadataStore = Depends(get_metadata_store),
    llm_client: ChatGoogleGenerativeAI = Depends(get_llm_client),
    langsmith_client: LangSmithClient | None = Depends(get_langsmith_client),
    research_client: CompanyResearchClient = Depends(get_research_client),
):
    start_time = time.monotonic()
    input_tokens = 0
    output_tokens = 0

    # 0. Verify sender document exists before proceeding. This is a hard requirement.
    if not metadata_store.list_documents(request.sender_company, role="sender"):
        raise HTTPException(
            status_code=404,
            detail=f"Sender company '{request.sender_company}' not found or has no uploaded documents. "
            "Please upload a sender context PDF via POST /companies/{name}/documents?role=sender.",
        )

    # 1. Sender context always comes from an uploaded document (required by /companies
    #    upload flow before /generate can succeed).
    sender_filter = {"$and": [{"company_name": request.sender_company}, {"role": "sender"}]}
    sender_retriever = vector_store.as_retriever(search_kwargs={"filter": sender_filter, "k": settings.retrieval_top_k})
    sender_context = [doc.page_content for doc in sender_retriever.invoke(request.prompt)]

    # 2. Receiver context: retrieve from an uploaded document if one exists, otherwise
    #    fall back to live web research (Gemini's Google Search grounding tool) so a
    #    receiver can be specified by name alone. Same grounding rule either way — see
    #    SYSTEM_PROMPT: only what's actually in this context, nothing invented.
    receiver_has_docs = bool(metadata_store.list_documents(request.receiver_company, role="receiver"))
    if receiver_has_docs:
        receiver_source = "document"
        receiver_filter = {"$and": [{"company_name": request.receiver_company}, {"role": "receiver"}]}
        receiver_retriever = vector_store.as_retriever(search_kwargs={"filter": receiver_filter, "k": settings.retrieval_top_k})
        receiver_context = [doc.page_content for doc in receiver_retriever.invoke(request.prompt)]
    else:
        receiver_source = "web_research"
        try:
            receiver_context, research_usage = research_client.research(request.receiver_company)
        except genai_errors.APIError as exc:
            # Grounded search sits on a separate, much stricter quota than plain
            # generation on Gemini's free tier — a 429 here is a real, expected
            # operating condition, not a bug. Surface it plainly with the workaround.
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Couldn't research receiver company '{request.receiver_company}' via web search: {exc}. "
                    "If this is a quota/rate-limit error, either wait and retry, upload a receiver context PDF "
                    "instead via POST /companies/{name}/documents?role=receiver, or set TAVILY_API_KEY in .env "
                    "for a free automatic fallback (sign up at https://app.tavily.com)."
                ),
            ) from exc
        input_tokens += research_usage["input_tokens"]
        output_tokens += research_usage["output_tokens"]
        if not receiver_context:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Web research for '{request.receiver_company}' returned nothing usable. "
                    "Try uploading a receiver context PDF instead."
                ),
            )

    # 3. Build the generation chain with LCEL. Context resolution happened above (in
    #    plain Python, not as a lazy LCEL step) because it now branches on a real
    #    decision — retrieve vs. research — that isn't naturally expressible as a
    #    declarative Runnable without more complexity than it buys.
    prompt_template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{user_prompt}")])
    user_prompt = build_user_prompt(
        request.sender_company, request.receiver_company, sender_context, receiver_context, request.prompt
    )

    # include_raw=True surfaces the underlying AIMessage (and its usage_metadata token
    # counts) alongside the parsed model — needed for /metrics token/cost tracking.
    llm_with_parser = llm_client.with_structured_output(ArticleDraft, include_raw=True)

    # Main generation chain
    chain = prompt_template | llm_with_parser

    # 4. Invoke the chain and handle potential errors
    try:
        run_name = f"Generate: {request.sender_company} -> {request.receiver_company}"
        config: RunnableConfig = {
            "run_name": run_name,
            "metadata": {"sender": request.sender_company, "receiver": request.receiver_company},
        }
        result = chain.invoke({"user_prompt": user_prompt}, config=config)
        if result["parsing_error"]:
            raise HTTPException(status_code=502, detail=f"Gemini returned a response that didn't match the article schema: {result['parsing_error']}")
        initial_draft = result["parsed"]
        usage = result["raw"].usage_metadata or {}
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        run_id = None
    except genai_errors.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc

    article = Article.from_draft(initial_draft)
    violations = validate_constraints(article)
    initial_violations = violations[:]
    repair_pass_needed = False

    if violations:
        repair_pass_needed = True
        # Your existing repair logic can be wrapped in a chain as well
        repair_prompt_str = (
            "{original_prompt}"
            "\n\n== Your previous draft violated these layout constraints ==\n{violations}"
            "\n\nPrevious draft:\n{previous_draft}"
            "\n\nRe-emit a corrected version that fixes every violation."
        )
        repair_prompt_template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", repair_prompt_str)])
        repair_chain = repair_prompt_template | llm_with_parser

        try:
            # Reuses the same sender/receiver context resolved in steps 1-2 above
            # (no second retrieval or research call — same grounding, lower cost).
            # The repair pass will show up as a nested run in the same trace
            repair_result = repair_chain.invoke(
                {
                    "original_prompt": build_user_prompt(
                        request.sender_company,
                        request.receiver_company,
                        sender_context,
                        receiver_context,
                        request.prompt,
                    ),
                    "violations": "\n".join(f"- {v}" for v in violations),
                    "previous_draft": initial_draft.model_dump_json(),
                },
                # You can add config to any `invoke` call
                config={"run_name": "Repair Pass", "metadata": config.get("metadata", {})},
            )
            if repair_result["parsing_error"]:
                raise HTTPException(status_code=502, detail=f"Gemini returned a response that didn't match the article schema during repair: {repair_result['parsing_error']}")
            repaired_draft = repair_result["parsed"]
            repair_usage = repair_result["raw"].usage_metadata or {}
            input_tokens += repair_usage.get("input_tokens", 0)
            output_tokens += repair_usage.get("output_tokens", 0)
            article = Article.from_draft(repaired_draft)
            violations = validate_constraints(article) # re-validate
        except genai_errors.APIError as exc:
            raise HTTPException(status_code=502, detail=f"Gemini API error during repair pass: {exc}") from exc

    _resolve_image_assets(article, request.sender_company, request.receiver_company, metadata_store)

    total_tokens = input_tokens + output_tokens
    cost_usd = (
        input_tokens / 1_000_000 * settings.gemini_input_price_usd_per_million
        + output_tokens / 1_000_000 * settings.gemini_output_price_usd_per_million
    )
    cost_eur = cost_usd * settings.usd_to_eur_rate

    metrics = {
        "latency_seconds": time.monotonic() - start_time,
        "repair_pass_needed": repair_pass_needed,
        "initial_violations": initial_violations,
        "final_violations": violations,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_eur, 6),
    }

    metadata_store.add_generation_metrics(
        GenerationMetricsRecord(
            id=str(uuid.uuid4()),
            sender_company=request.sender_company,
            receiver_company=request.receiver_company,
            receiver_source=receiver_source,
            model_name=settings.gemini_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_seconds=metrics["latency_seconds"],
            repair_pass_needed=repair_pass_needed,
            initial_violations_count=len(initial_violations),
            final_violations_count=len(violations),
            sender_chunks_used=len(sender_context),
            receiver_chunks_used=len(receiver_context),
            cost_usd=cost_usd,
            cost_eur=cost_eur,
        )
    )

    logger.info(json.dumps({"event": "article_generated", "metrics": metrics}))

    # 5. Add evaluation feedback to the LangSmith trace
    if langsmith_client and run_id:
        score = 1.0 if not violations else 0.0
        langsmith_client.create_feedback(
            run_id=run_id,
            key="Constraint Adherence",
            score=score,
            comment=f"Final constraint violations: {len(violations)}",
        )
    return {
        "article": article.model_dump(),
        "retrieval": {
            "sender_chunks_used": len(sender_context),
            "receiver_chunks_used": len(receiver_context),
            "receiver_source": receiver_source,
        },
        "metrics": metrics,
    }


def _resolve_image_assets(
    article: Article, sender_company: str, receiver_company: str, metadata_store: MetadataStore
) -> None:
    """Replace LLM-chosen slot names with real asset paths extracted from the uploaded PDFs.

    The model never sees or invents file paths -- this keeps every image
    reference factually grounded in what was actually uploaded.
    """
    sender_logo = metadata_store.get_logo(sender_company, "sender")
    receiver_logo = metadata_store.get_logo(receiver_company, "receiver")

    for slot in article.image_slots:
        if slot.slot_name == "sender_logo":
            slot.asset_ref = sender_logo.file_path if sender_logo else None
        elif slot.slot_name == "receiver_logo":
            slot.asset_ref = receiver_logo.file_path if receiver_logo else None
        elif slot.slot_name == "hero":
            slot.asset_ref = None  # prototype limitation: no contextual hero-image selection yet
