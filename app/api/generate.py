import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from google.genai import errors as genai_errors
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.runnables.config import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.dependencies import get_langsmith_client, get_llm_client, get_metadata_store, get_vector_store
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.generation.schema import Article, ArticleDraft
from app.generation.validator import validate_constraints
from langchain_community.vectorstores.chroma import Chroma
from app.storage.metadata_db import MetadataStore

logger = logging.getLogger(__name__)
from langsmith import Client as LangSmithClient

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
):
    start_time = time.monotonic()

    # 1. Create retrievers for sender and receiver context
    sender_filter = {"$and": [{"company_name": request.sender_company}, {"role": "sender"}]}
    receiver_filter = {"$and": [{"company_name": request.receiver_company}, {"role": "receiver"}]}
    sender_retriever = vector_store.as_retriever(search_kwargs={"filter": sender_filter, "k": settings.retrieval_top_k})
    receiver_retriever = vector_store.as_retriever(search_kwargs={"filter": receiver_filter, "k": settings.retrieval_top_k})

    # 2. Build the generation chain with LCEL
    setup_and_retrieval = RunnablePassthrough.assign(
        sender_context=RunnableLambda(lambda x: [doc.page_content for doc in sender_retriever.invoke(x["creative_brief"])]),
        receiver_context=RunnableLambda(lambda x: [doc.page_content for doc in receiver_retriever.invoke(x["creative_brief"])]),
    )

    def format_prompt(x):
        return build_user_prompt(
            x["sender_company"], x["receiver_company"], x["sender_context"], x["receiver_context"], x["creative_brief"]
        )

    llm_with_parser = llm_client.with_structured_output(ArticleDraft)

    # Main generation chain
    chain = setup_and_retrieval | RunnableLambda(format_prompt) | llm_with_parser

    # 4. Invoke the chain and handle potential errors
    try:
        run_name = f"Generate: {request.sender_company} -> {request.receiver_company}"
        config: RunnableConfig = {
            "run_name": run_name,
            "metadata": {"sender": request.sender_company, "receiver": request.receiver_company},
        }
        # The 'invoke' method returns a dict with 'output' and 'run_id' when tracing is on
        result = chain.invoke(
            {
                "sender_company": request.sender_company,
                "receiver_company": request.receiver_company,
                "creative_brief": request.prompt,
            },
            config=config,
        )
        initial_draft = result
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
        repair_prompt_template = PromptTemplate.from_template(repair_prompt_str)
        repair_chain = repair_prompt_template | llm_with_parser

        try:
            # The repair pass will show up as a nested run in the same trace
            repair_result = repair_chain.invoke(
                {
                    "original_prompt": build_user_prompt(
                        request.sender_company,
                        request.receiver_company,
                        [doc.page_content for doc in sender_retriever.invoke(request.prompt)],
                        [doc.page_content for doc in receiver_retriever.invoke(request.prompt)],
                        request.prompt,
                    ),
                    "violations": "\n".join(f"- {v}" for v in violations),
                    "previous_draft": initial_draft.model_dump_json(),
                },
                # You can add config to any `invoke` call
                config={"run_name": "Repair Pass", "metadata": config.get("metadata", {})},
            )
            repaired_draft = repair_result
            article = Article.from_draft(repaired_draft)
            violations = validate_constraints(article) # re-validate
        except genai_errors.APIError as exc:
            raise HTTPException(status_code=502, detail=f"Gemini API error during repair pass: {exc}") from exc

    _resolve_image_assets(article, request.sender_company, request.receiver_company, metadata_store)

    metrics = {
        "latency_seconds": time.monotonic() - start_time,
        "repair_pass_needed": repair_pass_needed,
        "initial_violations": initial_violations,
        "final_violations": violations,
    }

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
            "sender_chunks_used": settings.retrieval_top_k,
            "receiver_chunks_used": settings.retrieval_top_k,
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
