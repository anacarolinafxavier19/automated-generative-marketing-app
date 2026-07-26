# Generative Marketing App

Prototype backend for automated, personalized B2B marketing collateral. It takes
sender/receiver context PDFs, retrieves relevant grounding, and generates a tailored
article as structured JSON mapped to a pre-defined layout template.

Full design writeup (pipeline + Azure production architecture) is in
[`docs/architecture.md`](docs/architecture.md).

## Goal

A human editor doing this by hand would: (1) read a Sender company's materials to learn
what it sells, (2) read a Receiver company's materials to learn its industry and pain
points, (3) write a short article bridging the two ("here's why Sender's product matters
to someone in Receiver's position"), and (4) drop that copy into a fixed layout template
(headline, subheadline, body columns, logo slots, brand colors).

This app automates steps 1–3 end to end and hands back JSON shaped for step 4. Given a
sender PDF, a receiver PDF, and a one-line creative brief, `/generate` returns a single
structured article — grounded only in what was actually uploaded, never invented — ready
to be dropped into a rendering step (out of scope here, see
[Known limitations](#known-limitations-prototype-scope)).

## Scope: how this was built

Built as a small, linear pipeline rather than a general-purpose agent, since the task has
a fixed shape (two documents in, one constrained JSON object out):

1. **Ingest** (`POST /companies/{name}/documents`) — parse each PDF (text, tables, images),
   split the text into overlapping chunks, embed the chunks, and store them in a per-company,
   per-role vector index. Logos/images are extracted and kept alongside, addressed by file
   path, not re-generated.
2. **Retrieve** (`/generate`, step 1) — for the given sender/receiver pair, pull back the
   top-k most relevant chunks for each side using the creative brief as the query.
3. **Generate** (`/generate`, step 2) — feed the retrieved chunks plus the brief to the LLM
   through a system prompt that forbids inventing facts, requesting output constrained to
   the article JSON schema.
4. **Validate + repair** (`/generate`, step 3) — check the draft against hard layout
   constraints (word limits per section); if it fails, send the model its own draft plus
   the specific violations and ask for one corrected pass.
5. **Resolve assets** (`/generate`, step 4) — swap the model's chosen image *slot names*
   (`sender_logo`, `receiver_logo`, `hero`) for the real file paths extracted in step 1, so
   the response can never point at an asset the model made up.

A static demo UI (`http://localhost:8000/ui/`, `app/static/index.html`) sits in front of
steps 1–5 for manual demoing — it's a thin browser client over the same two endpoints,
with no separate frontend build/framework, so it doesn't change anything about the
pipeline above.

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
| **Grounding, to reduce hallucination** | The system prompt explicitly instructs the model to base every factual claim only on the retrieved context, and to generalize rather than invent specifics it isn't given. Retrieval is what makes this possible: the model only "knows" what was just handed to it in the prompt. | `app/generation/prompts.py` (`SYSTEM_PROMPT`) |
| **Structured / schema-constrained output** | Instead of free-text the model returns JSON matching a fixed Pydantic schema, so the response is directly usable by a downstream renderer with no parsing guesswork. | `app/generation/schema.py`, `llm_client.with_structured_output(ArticleDraft)` |
| **Self-correction (reflect-and-retry) loop** | A lightweight, non-agentic version of "let the model see its own mistake": deterministic code checks hard constraints (section word limits) that the LLM can't be trusted to count reliably, and if they fail, makes one more call with the previous draft and the specific violations attached, asking for a fix. | `app/generation/validator.py`, repair pass in `app/api/generate.py` |
| **Multi-modal grounding for assets** | The model chooses *which* image slot to use from a fixed vocabulary (e.g. `sender_logo`) but never sees or invents a file path — the actual asset is resolved server-side against images that were physically extracted from the uploaded PDFs. | `_resolve_image_assets` in `app/api/generate.py` |

## Why this stack

This runs entirely on a local machine (no Azure account needed to try it), but every
external dependency sits behind a small interface, so swapping it for the Azure target
architecture is an adapter change, not a rewrite:

| Concern       | Local prototype                      | Azure production target        |
|---------------|---------------------------------------|---------------------------------|
| LLM           | Google Gemini (`app/generation/llm_client.py`) | Azure OpenAI (structured outputs) |
| Embeddings    | Google `gemini-embedding-001` (`app/dependencies.py`) | Azure OpenAI embeddings deployment |
| Vector store  | ChromaDB, persisted to disk           | Azure AI Search (hybrid vector index) |
| Metadata DB   | SQLite via SQLModel                   | Cosmos DB / Azure Database for PostgreSQL |
| File storage  | local `./storage/`                    | Azure Blob Storage             |

The LLM provider is Gemini rather than Azure OpenAI purely because the target Azure
OpenAI resource wasn't available yet; `app/generation/llm_client.py` is the only file
that would need a new adapter to point this at Azure OpenAI instead.

## Setup

Requires Python 3.11+. Run these from the repo root (the directory containing
`pyproject.toml`) — running `pip install -e ".[dev]"` from any other directory
(e.g. `.claude/skills`) fails with "does not appear to be a Python project" since
pip installs relative to your current directory, not the repo.

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

**Fastest way:** open `http://localhost:8000/ui/` in a browser — a small demo page for
uploading both PDFs and generating an article without curl. It talks to the exact same
two endpoints below and defaults to the same fixture company names the smoke test uses,
so you can point its file pickers at `tests/fixtures/sender_company_context.pdf` and
`tests/fixtures/receiver_company_context.pdf`.

Or drive the API directly. Upload context PDFs for a sender and a receiver company:

```bash
curl -X POST "localhost:8000/companies/AcmeAI/documents?role=sender" \
  -F "files=@sender.pdf"

curl -X POST "localhost:8000/companies/LogiCorp/documents?role=receiver" \
  -F "files=@receiver.pdf"
```

Generate a tailored article:

```bash
curl -X POST localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
        "sender_company": "AcmeAI",
        "receiver_company": "LogiCorp",
        "prompt": "Pitch our forecasting platform for reducing warehouse overstock."
      }'
```

Returns JSON matching the layout schema in `app/generation/schema.py`: `headline`,
`subheadline`, `body_sections` (each with a word limit), `image_slots` (resolved to real
asset paths extracted from the uploaded PDFs, never invented by the model), `theme`
colors, and a `cta`. Section word limits are enforced in `app/generation/validator.py`;
if the model's first draft violates a limit, the endpoint automatically does one repair
pass before returning.

## Tests

```bash
pytest
```

## Known limitations (prototype scope)

- **Table extraction** is flattened to pipe-delimited text, not structured cell data.
- **Logo detection** is a heuristic (largest image on page 1), not a trained detector.
- **Hero image selection** isn't implemented — only the sender/receiver logo slots
  resolve to a real asset; production would add contextual image retrieval/generation.
- **Retrieval** does per-company top-k similarity search; there's no cross-document
  re-ranking or citation tracking back to source pages.
- Ingestion is synchronous in the request path; the Azure design decouples this via a
  queue (see `docs/architecture.md`) since PDF parsing/embedding is the slow step.
- The layout template in `schema.py` is representative — the client's real template
  (column limits, font sizes, brand palette rules) would replace it directly.
