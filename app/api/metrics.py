"""Agentic AI metrics + dependency/dead-code alerts for the dashboard and the
app-evaluator agent.

`GET /metrics` aggregates every persisted `GenerationMetricsRecord` (see
`app/storage/metadata_db.py`) into the "agentic AI common metrics" this app can
actually compute from real request data -- see docs/agentic-ai-stack.md for why some
common agentic metrics (e.g. grounding/hallucination rate) are *not* here: they'd need
an LLM-judge pass this prototype doesn't run.
"""

import json
import statistics

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.dependencies import get_metadata_store
from app.storage.metadata_db import GenerationMetricsRecord, MetadataStore

router = APIRouter(tags=["metrics"])


def _avg(values: list[float]) -> float:
    return round(statistics.fmean(values), 4) if values else 0.0


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 4) if values else 0.0


@router.get("/metrics")
def get_metrics(
    limit: int = 500,
    metadata_store: MetadataStore = Depends(get_metadata_store),
):
    records = metadata_store.list_generation_metrics(limit=limit)

    if not records:
        return {
            "summary": {
                "total_generations": 0,
                "first_pass_success_rate": None,
                "repair_pass_rate": None,
                "repair_success_rate": None,
                "avg_latency_seconds": None,
                "p50_latency_seconds": None,
                "avg_sender_chunks_used": None,
                "avg_receiver_chunks_used": None,
                "avg_input_tokens": None,
                "avg_output_tokens": None,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost_usd": 0.0,
                "total_cost_eur": 0.0,
                "avg_cost_eur_per_generation": None,
                "web_research_rate": None,
            },
            "records": [],
        }

    n = len(records)
    needed_repair = [r for r in records if r.repair_pass_needed]
    repair_succeeded = [r for r in needed_repair if r.final_violations_count == 0]
    first_pass_ok = [r for r in records if r.initial_violations_count == 0]
    web_researched = [r for r in records if r.receiver_source == "web_research"]

    total_input_tokens = sum(r.input_tokens for r in records)
    total_output_tokens = sum(r.output_tokens for r in records)
    total_cost_usd = sum(r.cost_usd for r in records)
    total_cost_eur = sum(r.cost_eur for r in records)

    summary = {
        "total_generations": n,
        "first_pass_success_rate": round(len(first_pass_ok) / n, 4),
        "repair_pass_rate": round(len(needed_repair) / n, 4),
        "repair_success_rate": round(len(repair_succeeded) / len(needed_repair), 4) if needed_repair else None,
        "avg_latency_seconds": _avg([r.latency_seconds for r in records]),
        "p50_latency_seconds": _median([r.latency_seconds for r in records]),
        "avg_sender_chunks_used": _avg([r.sender_chunks_used for r in records]),
        "avg_receiver_chunks_used": _avg([r.receiver_chunks_used for r in records]),
        "avg_input_tokens": _avg([r.input_tokens for r in records]),
        "avg_output_tokens": _avg([r.output_tokens for r in records]),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost_usd, 6),
        "total_cost_eur": round(total_cost_eur, 6),
        "avg_cost_eur_per_generation": round(total_cost_eur / n, 6),
        "web_research_rate": round(len(web_researched) / n, 4),
    }

    return {
        "summary": summary,
        "records": [_serialize(r) for r in records],
    }


@router.get("/evaluation-report")
def get_evaluation_report(settings: Settings = Depends(get_settings)):
    """Serves the JSON report the `app-evaluator` agent writes to
    `storage/evaluation-report.json` (dependency/dead-code alerts + improvement
    suggestions + a narrative read of /metrics). Not generated automatically — run the
    agent (`.claude/agents/app-evaluator.md`) to produce or refresh it.
    """
    report_path = settings.storage_root / "evaluation-report.json"
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No evaluation report yet — run the app-evaluator agent to generate storage/evaluation-report.json.",
        )
    return json.loads(report_path.read_text())


def _serialize(r: GenerationMetricsRecord) -> dict:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "sender_company": r.sender_company,
        "receiver_company": r.receiver_company,
        "receiver_source": r.receiver_source,
        "model_name": r.model_name,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "total_tokens": r.total_tokens,
        "latency_seconds": r.latency_seconds,
        "repair_pass_needed": r.repair_pass_needed,
        "initial_violations_count": r.initial_violations_count,
        "final_violations_count": r.final_violations_count,
        "sender_chunks_used": r.sender_chunks_used,
        "receiver_chunks_used": r.receiver_chunks_used,
        "cost_usd": r.cost_usd,
        "cost_eur": r.cost_eur,
    }
