# Agentic AI Stack: What Each Piece of Tech Is Doing

This document maps every technology in `pyproject.toml` onto the standard building
blocks ("cores") of an agentic AI system — perception, memory, retrieval, reasoning,
grounding, structured output, reflection, and orchestration — and says plainly which
ones this app implements and which it deliberately doesn't.

## How to read this

This app is a **grounded generation pipeline with one bounded self-correction loop**,
not an autonomous multi-step agent. It runs a fixed sequence once per `/generate` call
and stops — the model itself never decides what to do next and never plans a
multi-step task; the *one* external tool call it makes (Google Search grounding, to
research a receiver company with no uploaded document — see core 3.5) is triggered by
a fixed if/else in application code, not chosen by the model mid-reasoning. That's a
deliberate scope choice (see [`README.md`](../README.md#scope-how-this-was-built)), not
a limitation of the underlying tech; several of the pieces below (LangChain's LCEL
runnables, Gemini's function-calling support) are the same primitives a full autonomous
agent would be built from. Rather than "this app uses framework X, therefore it's
agentic," treat each core below as a checkbox: implemented, partially implemented, or
intentionally skipped.

## The cores, and what implements each one

### 1. Perception — turning raw, multi-modal input into structured content

The system's only input is a PDF; perception here means extracting text, tables, and
images from it before anything else can happen.

- **PyMuPDF** (`pymupdf`, used directly in `app/ingestion/pdf_parser.py`) — extracts
  raw text, flattens tables to pipe-delimited text, and pulls embedded images out of
  the PDF binary.
- **`PyMuPDFLoader`** (`langchain-community`, used in `app/api/upload.py`) — a second,
  LangChain-native entry point into the same PyMuPDF text extraction, used specifically
  to hand text `Document` objects to the LangChain chunking/embedding pipeline below.

### 2. Memory — persisting what's been perceived so it can be used later

Split, as it usually is in agentic systems, into an unstructured/semantic half and a
structured/episodic half:

- **ChromaDB** (`chromadb`, wrapped by `langchain_community.vectorstores.chroma.Chroma`
  in `app/dependencies.py`) — long-term **semantic** memory. Every chunk of every
  uploaded PDF is embedded and persisted here, tagged with `company_name` and `role`
  metadata, and survives across requests (it's `./storage/vector_store/`, not
  in-memory).
- **SQLModel over SQLite** (`sqlmodel`, `app/storage/metadata_db.py`) — long-term
  **structured/episodic** memory: which documents were uploaded, when, and where their
  extracted images live on disk. This is what `_resolve_image_assets` in
  `app/api/generate.py` queries to turn a model-chosen slot name into a real file path.
- **What's absent:** there's no **working memory across turns** — no conversation
  history, no session state. Every `/generate` call is stateless from the caller's
  perspective except for what it retrieves from the two stores above. There's also no
  memory *consolidation* (summarizing/forgetting old chunks) — everything persists
  forever once uploaded.

### 3. Retrieval — pulling the relevant slice of memory into context

- **`GoogleGenerativeAIEmbeddings`** (`langchain-google-genai`, `app/dependencies.py`)
  — encodes both stored chunks (at upload time) and the live query (the creative brief,
  at generate time) into the same vector space, so semantic similarity search is
  possible at all.
- **`Chroma.as_retriever(...)`** (`app/api/generate.py`) — does the actual top-k
  similarity search, scoped with a compound `$and` filter so a sender's retrieval can
  never leak into the receiver's context or vice versa (see
  [`architecture.md`](architecture.md) design choice #3). Always used for the sender
  side (a sender PDF upload is required); used for the receiver side only when a
  receiver document was actually uploaded.
- **`tiktoken`** (via `langchain-text-splitters`'s `TokenTextSplitter`,
  `app/api/upload.py`) — not retrieval itself, but what makes retrieval *granular*:
  splits long documents into ~500-token overlapping chunks before embedding, so a
  query can retrieve the specific relevant paragraph instead of an entire 10-page PDF.
- **`CompanyResearchClient`** (`app/generation/research.py`) — the receiver-side
  fallback when no document was uploaded: instead of retrieving from memory, it
  *populates* memory-shaped context live, via Gemini's Google Search grounding tool
  (see core 3.5 below). `app/api/generate.py` checks
  `metadata_store.list_documents(receiver_company, role="receiver")` once per request
  to decide which path to take — this is the one real conditional branch in an
  otherwise fixed pipeline, and it's why context resolution was pulled out of the LCEL
  chain into plain Python (a declarative `Runnable` doesn't buy much for a single
  if/else that only runs once).

### 3.5. Tool use — the one place this app actually calls an external tool

Named as its own core because it's new and it's the one place the "cores this app
deliberately does not implement" list (below) had to be corrected, not just extended:

- **Gemini's Google Search grounding tool** (`google.genai.types.Tool(google_search=...)`,
  called directly via the raw `google-genai` SDK in `CompanyResearchClient.research()`
  — not through LangChain, which doesn't currently expose this tool config as simply)
  — a real, live web search the model runs and reads results from before answering,
  used *only* for the receiver-research fallback in core 3. This is genuine tool use,
  scoped narrowly: the main article-generation call never calls a tool, plans, or
  decides *whether* to search — that decision is made in application code (core 3's
  conditional), not by the model.
- **Known operating constraint:** grounded search sits on a separate, much stricter
  quota than plain generation on Gemini's free tier — expect `429 RESOURCE_EXHAUSTED`
  regularly on a free-tier key even when plain `/generate` calls work fine.
  `app/api/generate.py` catches this and returns a 502 with the specific workaround
  (upload a receiver PDF instead) rather than failing opaquely or silently falling back
  to ungrounded generation.

### 4. Reasoning — the actual generation step

- **`ChatGoogleGenerativeAI`** (`langchain-google-genai`, wired in
  `app/dependencies.py`, invoked in `app/api/generate.py`) — the reasoning engine.
  Takes the retrieved context plus the creative brief and produces the article.
  Reasoning here is a single forward pass per attempt (initial draft, and — if
  needed — one repair pass), not a multi-step chain-of-thought or planning loop.

### 5. Grounding / guardrails — constraining what reasoning is allowed to claim

- **`SYSTEM_PROMPT`** (`app/generation/prompts.py`) — the actual guardrail text:
  instructs the model to base every claim only on retrieved context and to generalize
  rather than fabricate when the context doesn't support a specific claim. This is
  injected as a real system message via `ChatPromptTemplate` in `app/api/generate.py`
  — a prior bug in this repo (found and fixed during an audit pass) imported this
  constant but never actually attached it to the LLM call, so grounding was silently
  not happening. Fixed now; see git history on `app/api/generate.py` if curious.
- **Retrieval scoping itself** (see core 3) is also a grounding mechanism — the model
  physically cannot retrieve the wrong company's material to hallucinate from.

### 6. Structured output — constraining the *shape*, not just the content

- **Pydantic** (`pydantic`, `app/generation/schema.py`) — defines `ArticleDraft` /
  `Article`, the exact JSON shape the response must match, including the optional
  `tables: list[TableData]` field (0-2 tables; the model is instructed in
  `SYSTEM_PROMPT` not to invent one just to fill space, and `validator.py` caps rows
  (6) and columns (5) and rejects any row whose cell count doesn't match its headers).
- **`llm_client.with_structured_output(ArticleDraft, include_raw=True)`**
  (LangChain's structured-output wrapper over Gemini's native `response_schema`
  support) — forces the model to emit JSON conforming to that schema, rather than free
  text that then needs a fragile regex/parser to extract fields from. `include_raw=True`
  surfaces the underlying message's `usage_metadata` (token counts) alongside the
  parsed object — see core 9, Observability.

### 7. Reflection / self-correction — checking and fixing the reasoning step's output

- **`validate_constraints`** (`app/generation/validator.py`) — the trigger, not the
  reflection itself: a deterministic function checking hard, countable rules (word
  limits, hex color format) that an LLM can't reliably self-police.
- **The repair chain** (`app/api/generate.py`) — the actual reflection step: if
  validation fails, the model's own previous draft plus the specific violations are
  fed back to it in a second call, asking for a corrected version. This is a *bounded*
  reflection loop — exactly one retry, never open-ended — which is a deliberate design
  choice (see [`architecture.md`](architecture.md) design choice #4), not a limitation
  of the LLM or the framework.

### 8. Orchestration — wiring the cores above into one execution path

- **LangChain Expression Language** (`langchain-core`'s `RunnablePassthrough`,
  `RunnableLambda`, `ChatPromptTemplate`, all in `app/api/generate.py`) — declaratively
  chains retrieval → prompt construction → generation (`chain = setup_and_retrieval |
  RunnableLambda(format_prompt) | prompt_template | llm_with_parser`) into a single
  `.invoke()` call. This is orchestration in the narrow sense (sequencing fixed steps),
  not planning (deciding *which* steps to run).
- **FastAPI** (`fastapi`, `uvicorn`) — the outermost orchestration layer: turns an HTTP
  request into the dependency-injected objects (`get_vector_store`, `get_llm_client`,
  etc., from `app/dependencies.py`) that the chain above needs. Infrastructure, not an
  agentic core itself, but worth naming since it's what makes the pipeline callable.

### 9. Observability — watching what the reasoning step actually did

- **`GenerationMetricsRecord`** (`app/storage/metadata_db.py`, written from
  `app/api/generate.py`) — the functioning half of this story: every `/generate` call
  persists token counts (via `with_structured_output(..., include_raw=True)`'s
  `usage_metadata`), latency, retrieval/repair outcome, and cost (USD+EUR, priced from
  `app/core/config.py`) to SQLite. `GET /metrics` aggregates it into the agentic-AI
  metrics this document's other sections describe (first-pass success rate,
  repair-pass rate, token/cost totals); the `dashboard/` React app visualizes it.
- **`app-evaluator` agent** (`.claude/agents/app-evaluator.md`) — reads `/metrics`,
  re-runs the dependency/dead-code audit (`.claude/skills/audit-marketing-app/`), and
  writes `storage/evaluation-report.json` (alerts + improvement suggestions + narrative),
  served at `GET /evaluation-report` for the same dashboard.
- **LangSmith** (`langsmith`, `get_langsmith_client` in `app/dependencies.py`) — attaches
  evaluation feedback (constraint-adherence score) to each generation's trace for
  end-to-end observability. This is enabled when `LANGCHAIN_TRACING_V2` is set in the
  environment, providing detailed run analysis in the LangSmith UI.
- **`google.genai.errors.APIError`** (`google-genai`, caught in `app/api/generate.py`)
  — not observability in the tracing sense, but the error-handling boundary that turns
  a raw Gemini API failure into a proper `HTTPException` instead of a raw 500.

## Cores this app deliberately does not implement

Naming these explicitly so the gap between "RAG pipeline" and "autonomous agent" is a
choice you can see, not an accident:

- **Tool use *during generation*, and function calling specifically.** Correcting an
  earlier version of this doc: the app does now use one real tool (Google Search
  grounding — see core 3.5), so "no tool use at all" is no longer accurate. What's
  still true and still a deliberate scope boundary: the *main article-generation
  call* never calls a tool, and Gemini's function-calling support specifically
  (`langchain-google-genai` does expose it) is unused everywhere — tool use here is a
  single fixed pre-step (research the receiver, or don't), decided by application
  code before generation starts, not something the model chooses to invoke mid-reasoning.
- **Planning / task decomposition.** There's no step where the model decides what
  subtasks to run or in what order — the pipeline shape is fixed in code, not chosen
  by the model.
- **Cross-request / session memory.** Each `/generate` call is independent; nothing
  is remembered about prior generations for the same company pair beyond what's in the
  vector store and metadata DB (which are facts about *uploaded documents*, not about
  *past conversations*).
- **Multi-agent coordination.** One model, one role (B2B marketing editor), for both
  the initial draft and the repair pass — no specialist sub-agents or hand-offs.

If this were extended toward a fuller agentic system, the natural next additions —
in roughly the order they'd add the most capability — are: (1) a tool-calling loop so
the model could request more retrieval on its own instead of getting a fixed top-k
dump, (2) session memory so an account team could iterate on an article across
multiple turns instead of one-shot, and (3) a real planning step if the task ever grew
beyond "one article from one sender/receiver pair" into something with genuine
branching (e.g., "generate a full campaign across N receiver segments").
