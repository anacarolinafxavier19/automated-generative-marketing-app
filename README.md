# Automated Generative Marketing Collateral

Prototype for automated, personalized B2B marketing collateral. Upload a sender
context PDF, name the receiver company (upload a PDF for them too, or let the app
research them live via web search), describe what you want, and get a grounded
article — text, images, and tables — rendered as a brochure in
[`studio/`](studio/README.md), the content-creation web app, or consumed as
structured JSON directly from the API.

Full design writeup (pipeline + Azure production architecture) is in
[`docs/architecture.md`](docs/architecture.md). For how each piece of the stack maps
onto standard agentic-AI building blocks (memory, retrieval, grounding, reflection,
orchestration), see [`docs/agentic-ai-stack.md`](docs/agentic-ai-stack.md).

## Goal

A human editor doing this by hand would: (1) read a Sender company's materials to learn
what it sells, (2) read a Receiver company's materials to learn its industry and pain
points, (3) write a short article bridging the two ("here's why Sender's product matters
to someone in Receiver's position"), and (4) drop that copy into a fixed layout template
(headline, subheadline, body columns, logo slots, brand colors).

This app automates steps 1–4. Given a sender PDF, a receiver (a company name — from
an uploaded PDF if you have one, or researched live via web search if you don't), and
a one-line creative brief, `/generate` returns a single structured article — grounded
only in real content, never invented — that [`studio/`](studio/README.md) renders as an
actual brochure (theme-colored, with real logos and optional comparison tables), or
that you can consume as JSON directly and drop into your own template.

## Scope: how this was built

Built as a small, mostly linear pipeline rather than a general-purpose agent, with one
real conditional branch (does the receiver have an uploaded document or not) and one
bounded self-correction loop:

1. **Ingest** (`POST /companies/{name}/documents`) — parse each PDF (text, tables, images),
   split the text into overlapping chunks, embed the chunks, and store them in a per-company,
   per-role vector index. Logos/images are extracted and kept alongside, addressed by file
   path, not re-generated.
2. **Get context** (`/generate`, step 1-2) — sender context always comes from retrieving
   the top-k most relevant uploaded chunks. Receiver context does too, *if* a receiver
   document was uploaded; otherwise the receiver company is researched live via Gemini's
   Google Search grounding tool (`app/generation/research.py`) — same grounding guarantee,
   different source. See [`docs/agentic-ai-stack.md`](docs/agentic-ai-stack.md#35-tool-use--the-one-place-this-app-actually-calls-an-external-tool).
3. **Generate** (`/generate`, step 3) — feed that context plus the brief to the LLM
   through a system prompt that forbids inventing facts, requesting output constrained to
   the article JSON schema (including up to 2 optional tables, when the context actually
   supports something tabular).
4. **Validate + repair** (`/generate`, step 4) — check the draft against hard layout
   constraints (word/row/column limits); if it fails, send the model its own draft plus
   the specific violations and ask for one corrected pass.
5. **Resolve assets** (`/generate`, step 5) — swap the model's chosen image *slot names*
   (`sender_logo`, `receiver_logo`, `hero`) for the real file paths extracted in step 1, so
   the response can never point at an asset the model made up.

[`studio/`](studio/README.md) is the rendering step that used to be explicitly out of
scope — a React app that turns the JSON above into an actual styled brochure (theme
colors, real logo images, tables) with a print-to-PDF button.

Every external dependency (LLM, embeddings, vector store, metadata DB, file storage) sits
behind a small interface for exactly this reason — see [Why this stack](#why-this-stack)
for the local-vs-production mapping.

## Core GenAI concepts this applies

This is a fairly canonical **RAG (Retrieval-Augmented Generation)** pipeline with one small
self-correction loop bolted on. Mapping the basic concepts to where they live in the code:

| Concept | What it means here | Where |
|---|---|---|
| **Chunking** | PDFs are split into ~500-token overlapping pieces before embedding, since embedding models and LLM context windows both have limits, and overlap keeps a sentence that straddles a chunk boundary from losing meaning on either side. | `app/api/upload.py` (`TokenTextSplitter`) |
| **Embeddings** | Each chunk is converted into a vector that captures its *meaning*, not just its keywords, so retrieval can match "reduce warehouse overstock" against a chunk about "inventory forecasting" even with no shared words. | `app/dependencies.py` (`GoogleGenerativeAIEmbeddings`) |
| **Vector store + retrieval (the "R" in RAG)** | Chunks are indexed by embedding similarity and filtered by `company_name`/`role`, so `/generate` only ever retrieves *this* sender's and *this* receiver's own material — not the whole corpus. | `app/api/generate.py` (Chroma `as_retriever` with a metadata filter) |
| **Grounding, to reduce hallucination** | The system prompt explicitly instructs the model to base every factual claim only on the retrieved-or-researched context, and to generalize rather than invent specifics it isn't given. The model only "knows" what was just handed to it in the prompt — whether that came from retrieval or live search. | `app/generation/prompts.py` (`SYSTEM_PROMPT`) |
| **Tool-augmented grounding (web search)** | When the receiver has no uploaded document, the app calls Gemini's Google Search grounding tool once, live, to research the company by name — same grounding rule applies to what comes back. This is the one point where an external tool gets called at all; the main generation call never does. | `app/generation/research.py` (`CompanyResearchClient`) |
| **Structured / schema-constrained output** | Instead of free-text the model returns JSON matching a fixed Pydantic schema (including optional tables), so the response is directly usable by a renderer with no parsing guesswork. | `app/generation/schema.py`, `llm_client.with_structured_output(ArticleDraft, include_raw=True)` |
| **Self-correction (reflect-and-retry) loop** | A lightweight, non-agentic version of "let the model see its own mistake": deterministic code checks hard constraints (section word limits) that the LLM can't be trusted to count reliably, and if they fail, makes one more call with the previous draft and the specific violations attached, asking for a fix. | `app/generation/validator.py`, repair pass in `app/api/generate.py` |
| **Multi-modal grounding for assets** | The model chooses *which* image slot to use from a fixed vocabulary (e.g. `sender_logo`) but never sees or invents a file path — the actual asset is resolved server-side against images that were physically extracted from the uploaded PDFs. | `_resolve_image_assets` in `app/api/generate.py` |

## Why this stack

This runs entirely on a local machine (no Azure account needed to try it). `FileStore`
and `MetadataStore` (`app/storage/`) sit behind small `Protocol` interfaces, so swapping
those for Azure equivalents is an adapter change, not a rewrite. The LLM, embeddings,
and vector store are wired directly via LangChain in `app/dependencies.py` instead —
there's no custom interface layer over them, so swapping providers means changing that
one file's client construction:

| Concern       | Local prototype                      | Azure production target        |
|---------------|---------------------------------------|---------------------------------|
| LLM           | Google Gemini (`app/dependencies.py`, `ChatGoogleGenerativeAI`) | Azure OpenAI (structured outputs) |
| Embeddings    | Google `gemini-embedding-001` (`app/dependencies.py`) | Azure OpenAI embeddings deployment |
| Vector store  | ChromaDB, persisted to disk (`app/dependencies.py`) | Azure AI Search (hybrid vector index) |
| Metadata DB   | SQLite via SQLModel (`app/storage/metadata_db.py`) | Cosmos DB / Azure Database for PostgreSQL |
| File storage  | local `./storage/` (`app/storage/file_store.py`) | Azure Blob Storage             |

The LLM provider is Gemini rather than Azure OpenAI purely because the target Azure
OpenAI resource wasn't available yet; `app/dependencies.py` is the only file that would
need to change to point this at Azure OpenAI instead.

See [`docs/agentic-ai-stack.md`](docs/agentic-ai-stack.md) for how each of these pieces
maps onto the standard building blocks of an agentic AI system (memory, retrieval,
grounding, reflection, orchestration).

## Setup

Requires Python 3.11+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# then edit .env and set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API is at `http://localhost:8000` (interactive docs at `/docs`).

## Try it

**Easiest:** `cd studio && npm install && npm run dev`, open the URL it prints, upload
a sender PDF, type a receiver company name, describe what you want — see
[`studio/README.md`](studio/README.md).

Or drive the API directly. Upload a sender context PDF:

```bash
curl -X POST "localhost:8000/companies/AcmeAI/documents?role=sender" \
  -F "files=@sender.pdf"
```

Generate against a receiver by name only (no PDF — researched live via web search):

```bash
curl -X POST localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
        "sender_company": "AcmeAI",
        "receiver_company": "LogiCorp",
        "prompt": "Pitch our forecasting platform for reducing warehouse overstock."
      }'
```

Or upload a receiver PDF first (`role=receiver`, same shape as the sender upload above)
to ground on a real document instead — `/generate` automatically prefers it over live
research whenever one exists for that company name.

Returns JSON matching the layout schema in `app/generation/schema.py`: `headline`,
`subheadline`, `body_sections` (each with a word limit), `tables` (0-2 optional
comparison/spec tables), `image_slots` (resolved to real asset paths extracted from the
uploaded PDFs, never invented by the model), `theme` colors, and a `cta`. Constraints
are enforced in `app/generation/validator.py`; if the model's first draft violates one,
the endpoint automatically does one repair pass before returning. `retrieval.receiver_source`
in the response tells you which grounding path was used (`"document"` or
`"web_research"`).

## Tests

```bash
pytest
```

## Evaluation: metrics, cost, and the `app-evaluator` agent

Every `/generate` call persists a row (tokens, latency, retrieval/repair outcome, cost
in USD+EUR) to a `generationmetricsrecord` SQLite table — see `app/storage/metadata_db.py`
and the instrumentation in `app/api/generate.py`. Two read endpoints expose this:

- `GET /metrics` — aggregated agentic-AI metrics (first-pass success rate, repair-pass
  rate, avg latency, token/cost totals) plus the raw recent records.
- `GET /evaluation-report` — dependency/dead-code alerts, improvement suggestions, and
  narrative commentary written by the `app-evaluator` agent to
  `storage/evaluation-report.json`. This endpoint will return a 404 until the agent has run at least once.

`dashboard/` is a small React (Vite) app that visualizes both — see
[`dashboard/README.md`](dashboard/README.md) to run it (`npm install && npm run dev`,
backend must already be running). This is a separate app from [`studio/`](studio/README.md)
(content creation, above) — both are plain Vite dev servers with no fixed port
assignment between them, so if running both at once, start one on a non-default port,
e.g. `npm run dev -- --port 5174`.

Cost figures use per-token USD pricing + a USD→EUR rate hardcoded in
`app/core/config.py` as a dated snapshot (see that file's comment for the exact date
and the known pricing-tier retirement to watch for) — not a live pricing/FX feed;
update those constants periodically or cost figures will silently drift from reality.

## Known limitations (prototype scope)

- **Table extraction from uploaded PDFs** is flattened to pipe-delimited text, not
  structured cell data — this is separate from the *output* `tables` field (which the
  model constructs fresh, structured, for the generated article).
- **Logo detection** is a heuristic (largest image on page 1), not a trained detector.
- **Hero image selection** isn't implemented — only the sender/receiver logo slots
  resolve to a real asset; production would add contextual image retrieval/generation.
- **Retrieval** does per-company top-k similarity search; there's no cross-document
  re-ranking or citation tracking back to source pages.
- **Receiver web research has one free fallback if grounded search quota is
  exhausted** (expect this regularly on free-tier Gemini keys): set `TAVILY_API_KEY`
  in `.env` (free signup, no card, at https://app.tavily.com) and
  `CompanyResearchClient` automatically retries via Tavily's search API instead —
  still fully grounded, same "never invent" rule. Without a Tavily key, or if Tavily
  itself fails, it returns a 502 with a clear message (upload a receiver PDF instead)
  rather than silently degrading to ungrounded generation. There's still no automatic
  retry/backoff on Gemini's own grounding quota, and no other alternate provider — see
  [`docs/agentic-ai-stack.md`](docs/agentic-ai-stack.md#35-tool-use--the-one-place-this-app-actually-calls-an-external-tool).
- Ingestion is synchronous in the request path; the Azure design decouples this via a
  queue (see `docs/architecture.md`) since PDF parsing/embedding is the slow step.
- The layout template in `schema.py` is representative — the client's real template
  (column limits, font sizes, brand palette rules) would replace it directly.
  [`studio/`](studio/README.md)'s brochure rendering is a reasonable prototype
  stand-in, not that real template.
