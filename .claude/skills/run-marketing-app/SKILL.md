---
name: run-marketing-app
description: Build, run, and drive the marketing-app FastAPI backend. Use when asked to start marketing-app, run it, upload PDFs, generate an article, smoke test it, or check that the API works end-to-end.
---

FastAPI backend (Python) exposing endpoints to upload sender/receiver context PDFs and
generate a tailored marketing article (text, images, optional tables) as structured
JSON. Drive it via `.claude/skills/run-marketing-app/smoke.sh` — it launches the
server, uploads the committed fixture PDFs, calls `/generate`, and shuts down cleanly.
All paths below are relative to the repo root.

Two companion React apps live at `dashboard/` (evaluation metrics/alerts) and
`studio/` (the actual content-creation UI — upload, name a receiver, generate a
rendered brochure); both are separate `npm install && npm run dev` Vite projects that
talk to this backend over HTTP, see their own `README.md`s.

## Prerequisites


The system `python3` on macOS/most minimal Linux images is too old (this repo needs
3.11+; a fresh macOS box only has 3.9.6 preinstalled). Get 3.11+ first:

```bash
# macOS
brew install python@3.12

# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv lsof
```

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

`pyproject.toml` already pins `[tool.setuptools.packages.find] include = ["app*"]` —
without that, `pip install -e .` fails with "Multiple top-level packages discovered
in a flat-layout: ['app', 'storage']" because setuptools trips over the `storage/`
data directory sitting next to `app/`. If you ever see that error again, that's why.

Environment (`.env`, copy from `.env.example`):

```bash
cp .env.example .env
```

```bash
GEMINI_API_KEY=   # REQUIRED, including for upload — get one at https://aistudio.google.com/apikey
                   # embeddings go through langchain_google_genai (Gemini's embedding API),
                   # not local sentence-transformers, despite EMBEDDING_MODEL below suggesting
                   # otherwise (that setting and app/retrieval/embeddings.py are dead/unwired
                   # — see Gotchas). Without a key, upload itself 503s; you never reach /generate.
GEMINI_MODEL=gemini-flash-lite-latest   # do not hardcode a dated model like
                                         # gemini-2.5-flash-lite, see Gotchas
TAVILY_API_KEY=   # OPTIONAL — free fallback for receiver web research when Gemini's
                   # grounding quota (separate from GEMINI_API_KEY's own quota, see
                   # Gotchas) is exhausted. Sign up free at https://app.tavily.com.
```

## Build

No separate build step (pure Python, no bundling).

## Run (agent path)

```bash
./.claude/skills/run-marketing-app/smoke.sh
```

This is the verified, self-contained path: it creates `.venv` on first run if
missing, frees port 8000, wipes and recreates `storage/` *before* starting the
server, launches `uvicorn` in the background, polls `/health` until ready, uploads
`tests/fixtures/sender_company_context.pdf` and `tests/fixtures/receiver_company_context.pdf`,
calls `/generate`, and kills the server on exit (success or failure) via a trap.
Exit code 0 = healthy. Override the port with `PORT=8001 ./.claude/skills/run-marketing-app/smoke.sh`.

Server log while it runs: `/tmp/marketing-app-smoke.log`. Last `/generate` response
body: `/tmp/marketing-app-generate.json`.

`GEMINI_API_KEY` is required — without it, the upload step itself 503s (embeddings
call Gemini's embedding API), so the script fails before ever reaching `/generate`.
With a valid key set in `.env`, the script prints the real generated article JSON.

## Run (human / interactive path)

To leave the server running (e.g. to poke it from a browser at `/docs`, or run
more requests manually) rather than have the smoke script tear it down:

```bash
source .venv/bin/activate
lsof -ti:8000 -sTCP:LISTEN | xargs -r kill 2>/dev/null   # free the port first
rm -rf storage && mkdir -p storage                        # only when the server is NOT running — see Gotchas
nohup uvicorn app.main:app --port 8000 &> /tmp/marketing-app-server.log &
for i in $(seq 1 30); do curl -sf http://localhost:8000/health > /dev/null && break; sleep 1; done
curl http://localhost:8000/health   # → {"status":"ok"}
```

API docs (Swagger): `http://localhost:8000/docs`. The server itself has no browser UI —
drive `/companies/.../documents` and `/generate` directly via curl or `/docs`, same as
`smoke.sh` does. Requires `GEMINI_API_KEY` to be set for the upload step (embeddings),
the generate step, and (if the receiver has no uploaded doc) live receiver research —
see Gotchas.

`GET /metrics` (agentic-AI metrics: tokens, cost in EUR, repair-pass rate, latency) and
`GET /evaluation-report` (dependency/dead-code alerts + suggestions, written by the
`app-evaluator` agent — 404 until it's been run) are also live once the server is up.
`app/main.py` also mounts `/storage/documents` as static files, so extracted logo
images (`asset_ref` values from `/generate`, already shaped
`storage/documents/<company>/<role>/<doc_id>/images/<file>`) are fetchable at
`"/" + asset_ref` — this is what lets `studio/` render real logos in the brochure
preview. `dashboard/` (evaluation) and `studio/` (content creation) are separate React
apps that consume this API — see their own `README.md`s — `npm install && npm run dev`
in each, backend must already be running.

Stop the server with:

```bash
lsof -ti:8000 -sTCP:LISTEN | xargs -r kill
```

## Test

```bash
source .venv/bin/activate
pytest
```

7 tests, all unit-level (chunking, schema/constraint validation) — no server needed.

---

## Gotchas

- **Never delete/reset `storage/` while the server is running.** It holds an open
  SQLite connection (`storage/metadata.db`) and an open Chroma persistent client.
  Ripping the directory out from under them leaves the DB in a state where the next
  write fails with `sqlite3.OperationalError: attempt to write a readonly database`.
  Stop the server (or don't start it yet) before touching `storage/`.
- **Receiver PDF upload is now optional — `/generate` works with just a receiver
  company name.** If `metadata_store.list_documents(receiver_company, role="receiver")`
  is empty, `app/api/generate.py` calls `CompanyResearchClient.research()`
  (`app/generation/research.py`), which uses Gemini's Google Search grounding tool to
  research the company live instead of retrieving from the vector store. Same
  grounding rule (never invent), different source.
- **Grounded search sits on a separate, much stricter quota than plain generation —
  expect `429 RESOURCE_EXHAUSTED` regularly on a free-tier key.** Confirmed live: the
  exact same API key that generates articles fine hits quota immediately on any call
  using `types.Tool(google_search=types.GoogleSearch())`. This is not a bug in this
  repo. `CompanyResearchClient.research()` (`app/generation/research.py`) now
  auto-falls-back to Tavily's free-tier search API on a 429 if `TAVILY_API_KEY` is set
  in `.env` (sign up free at https://app.tavily.com — no card needed); with no Tavily
  key, `/generate` catches the 429 and returns a 502 telling the caller to upload a
  receiver PDF instead (which sidesteps research entirely). If Tavily itself errors
  (bad key, network issue), the code falls back further to that same original 429
  message rather than crashing — see the `try/except Exception` around
  `self._tavily_research(...)` in `research.py`. If you need to test the web-research
  success path without live grounding quota (or without a Tavily key), override the
  `get_research_client` FastAPI dependency with a fake `CompanyResearchClient` (see
  git history / PR that added this feature for a `TestClient` example — the point is
  `app.dependency_overrides[get_research_client] = lambda: FakeClient()` before
  constructing a `TestClient`).
- **Don't hardcode a dated Gemini model name.** `gemini-2.5-flash` (an earlier default
  in this repo) 404s for at least some API keys with `"This model models/gemini-2.5-flash
  is no longer available to new users."` even though it still shows up in
  `client.models.list()`. The same thing happens with `gemini-2.5-flash-lite` — listed,
  but 404s on an actual `generate_content` call. Use the `-latest` alias for whichever
  tier you want instead: `gemini-flash-latest` or `gemini-flash-lite-latest` (the
  current default in `app/core/config.py` and `.env.example`) — these get silently
  repointed at a live model as Google deprecates dated ones, instead of breaking.
- **The system `python3` is too old.** `python3 --version` on a stock macOS box is
  3.9.6; this project needs 3.11+ for the `X | Y` union-type syntax used throughout
  `app/`. `pip install -e .` will fail obscurely (or `import` errors at runtime) on
  3.9 — always create the venv with `python3.12`/`python3.11` explicitly, not bare
  `python3`.
- **Port 8000 can briefly still show as bound immediately after `smoke.sh` exits.**
  The `trap ... EXIT` sends SIGTERM to uvicorn on the way out, but the script doesn't
  block waiting for the socket to actually release — a `lsof -ti:8000` run in the very
  next command can still show the (dying) PID. It's gone within ~1s; not a leak.
- **Embeddings actually call Gemini's API, not local `sentence-transformers`.**
  `app/dependencies.py:get_embedding_client()` wires `GoogleGenerativeAIEmbeddings`
  into the vector store. `EMBEDDING_MODEL=all-MiniLM-L6-v2` in `.env` is now a
  vestigial setting nothing reads — the local `sentence-transformers` embedding client
  it once configured (`app/retrieval/embeddings.py`) was found unwired/dead and deleted
  in a later audit pass. Practical effect: uploads need `GEMINI_API_KEY` too, not just
  `/generate`, and there's no offline/no-key embedding path today despite what the
  config suggests.
- **Don't hardcode a dated Gemini *embedding* model either.** The original
  `models/embedding-001` 404s the same way `gemini-2.5-flash` does (see above) —
  `client.models.list()` shows it but calling `embedContent` on it fails. Current
  working models for a fresh key: `models/gemini-embedding-001` (already the default
  in `app/dependencies.py`) or `models/gemini-embedding-2`.
- **Chroma's `where` filter needs an explicit `$and` for multi-field queries.**
  `vector_store.as_retriever(search_kwargs={"filter": {...two keys...}})` raises
  `ValueError: Expected where to have exactly one operator` on the installed
  `chromadb` version. `app/api/generate.py` builds
  `{"$and": [{"company_name": ...}, {"role": ...}]}` for this reason — don't flatten
  it back to a bare two-key dict.
- **`with_structured_output(...)` returns the parsed model directly, not a
  `{"output": ..., "run_id": ...}` dict.** That shape only appears if you pass
  `include_raw=True`. `app/api/generate.py` reads `result` (and `repair_result`)
  directly as the `ArticleDraft`; `run_id` is `None` today (no LangSmith run-id
  plumbing wired up), which is fine since `get_langsmith_client()` only returns a
  client when `LANGCHAIN_TRACING_V2` is set truthy anyway.
- **`build_user_prompt(...)` renders text immediately — it's not a lazy template.**
  It's a `list[str] -> str` function that does the `"\n---\n".join(...)` itself.
  Don't wrap its output in `PromptTemplate.from_template(...)` and call it again
  with placeholder strings like `"{sender_context}"` — passing a string where a list
  is expected silently iterates it character-by-character and corrupts the prompt.
  Call `build_user_prompt(...)` directly with the real resolved lists instead.

## Troubleshooting

- **`error: Multiple top-level packages discovered in a flat-layout: ['app', 'storage']`**
  during `pip install -e .`: `[tool.setuptools.packages.find]` is missing/wrong in
  `pyproject.toml`. It must read `include = ["app*"]`.
- **`sqlite3.OperationalError: attempt to write a readonly database`** on an upload
  call: `storage/` was deleted or modified while the server was already running.
  Kill the server, `rm -rf storage && mkdir -p storage`, then restart.
- **`Gemini API error: 404 NOT_FOUND ... no longer available to new users`** from
  `/generate`: `GEMINI_MODEL` in `.env` is pinned to a deprecated model. Set it to
  `gemini-flash-latest` or `gemini-flash-lite-latest` (whichever tier you want) instead
  of a dated name like `gemini-2.5-flash` / `gemini-2.5-flash-lite`.
- **`GEMINI_API_KEY is not configured` (HTTP 503) from upload or `/generate`**: this
  is the *expected* response when `.env` has no key — not a bug. It now surfaces at
  upload time too, since embeddings call Gemini's API (see Gotchas); it no longer
  means the rest of the pipeline already succeeded.
- **`ModuleNotFoundError: No module named 'langchain_core'` (or `langchain_community`
  / `langchain_google_genai` / `langchain_text_splitters`) on server start**:
  `pyproject.toml`'s `dependencies` list is missing one of these — `app/` imports
  them directly (`app/api/generate.py`, `app/api/upload.py`, `app/dependencies.py`).
  Add the missing package(s) and re-run `pip install -e ".[dev]"`.
- **`AttributeError: 'Settings' object has no attribute 'langchain_tracing_v2'`**:
  `app/dependencies.py:get_langsmith_client()` reads that field but it's missing
  from `app/core/config.py`'s `Settings` class. Add
  `langchain_tracing_v2: bool = False` to `Settings`.
- **`langchain_google_genai._common.GoogleGenerativeAIError: ... 404 NOT_FOUND ...
  models/embedding-001 is not found`** from an upload call: same dated-model issue
  as the chat model, but for embeddings — see Gotchas for the fix
  (`models/gemini-embedding-001`).
- **`ValueError: Expected where to have exactly one operator, got {...}`** from
  `/generate`: a Chroma `where` filter was flattened to a bare multi-key dict
  instead of using `$and` — see Gotchas.
- **`KeyError` on a mangled string like `'\n---\ns\n---\ne\n---\n...'`** from
  `/generate`: `build_user_prompt(...)` was called with placeholder strings instead
  of real context lists and then wrapped in `PromptTemplate.from_template(...)` —
  see the `build_user_prompt` gotcha above.
- **`TypeError: 'ArticleDraft' object is not subscriptable`** (or similar on
  `repair_result`) from `/generate`: code assumed `chain.invoke(...)` returns
  `{"output": ..., "run_id": ...}`; with plain `with_structured_output(...)` it
  returns the parsed object directly — see Gotchas.
- **`smoke.sh` hangs for 30s then fails with "server did not become healthy"**, and
  the log shows `[Errno 48] Address already in use` (or similar): `lsof` wasn't found
  (minimal `PATH`, or not installed on a bare Linux image — see Prerequisites) so the
  script's "free port 8000" step silently no-op'd and a previous server was still
  bound to it. Install `lsof`, or manually `kill` whatever's on port 8000, then re-run.
