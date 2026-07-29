---
name: audit-marketing-app
description: Audit marketing-app for dead code, unused imports/dependencies, and repo-structure problems (especially .gitignore overreach), then safely delete/fix what's confirmed dead. Use when asked to audit the code, find/remove unused code or dead code, clean up the repo, check for unused dependencies, or review repo structure for this project.
---

Static-analysis-plus-verification audit for this repo. The core rule: **nothing gets
deleted or removed from `pyproject.toml` on the strength of a grep alone** — every
finding is confirmed by actually running the app (via
`.claude/skills/run-marketing-app/smoke.sh`) and the test suite, both before and after
the change. A past run of this audit initially deleted `tiktoken` because grep couldn't
find a direct `import tiktoken` in app code — the smoke test then failed, because
`langchain_text_splitters.TokenTextSplitter` (the code path `app/api/upload.py` actually
uses) needs it as an unstated runtime dependency. Static analysis finds *candidates*;
only running the app confirms them.

All paths below are relative to the repo root.

## Run (agent path)

Do these checks in order. Activate the venv first (`source .venv/bin/activate`,
creating it per `.claude/skills/run-marketing-app/SKILL.md` if needed).

### 1. Unused imports/names — pyflakes

```bash
pip install -q pyflakes   # not a project dependency, just an audit tool
python3 -m pyflakes app/ tests/ scripts/
```

Ignore any hits under `*/.venv/*` or `*/site-packages/*` if a stray venv exists inside
those dirs (see step 4) — pyflakes will happily lint vendored packages if a venv is
sitting where it's scanning.

A real hit found this way previously: `app/api/generate.py` imported `SYSTEM_PROMPT`
but never used it — the generation chain passed a bare string straight to the LLM with
no system message, so the app's own grounding/anti-hallucination rules were silently
never sent to Gemini. **This is the class of bug this step exists to catch: an unused
import is sometimes a missing wire-up, not dead weight.** Read the surrounding code
before deleting the import — check whether the thing it names was clearly *meant* to be
used (docstring, README claims, a construction like `convert_system_message_to_human=True`
that only makes sense if a system message was intended) before concluding it's safe to
delete outright.

### 2. Orphaned modules — reverse-reference check

For each source file, check whether its main class/function is imported *anywhere else*:

```bash
# Example shape — swap in the class/function name and file path
grep -rn "ClassOrFunctionName" --include="*.py" app tests scripts
```

If the only hit is the file's own definition line, the module is a dead alternate
implementation — usually a hand-written abstraction (`Protocol` + concrete class) that
got superseded by a direct third-party call elsewhere and never wired up or deleted.
This repo's `app/dependencies.py` wires concrete clients (Chroma, Gemini) directly; any
custom `*Client`/`*Store` abstraction under `app/` that `dependencies.py` doesn't
construct is a strong dead-code candidate. Previously found this way and deleted:
`app/retrieval/vector_store.py`, `app/retrieval/embeddings.py`,
`app/generation/llm_client.py` — plus `app/ingestion/chunking.py`, whose only caller
turned out to be its own unit test (`tests/test_chunking.py`), not the actual upload
path (which uses `langchain_text_splitters.TokenTextSplitter` instead).

### 3. Dependency audit — cross-check `pyproject.toml` against real usage

For each dependency in `pyproject.toml`, grep for its import name across `app/`. If a
dependency's only consumer is a module step 2 already marked dead, it's a deletion
candidate — but **don't remove it from `pyproject.toml` without doing steps 5 and 6
(reinstall + full run) afterward.** A dependency can be a real *transitive* runtime
requirement of another package (e.g. an extras-style optional import) without ever
appearing as a top-level `import` in this repo's own code.

### 4. `.gitignore` overreach — the highest-value check in this whole audit

Unanchored gitignore patterns (no leading `/`) match a directory name *anywhere* in the
tree, not just at the root. This repo shipped with two: `storage/` (meant to ignore the
root-level runtime data dir) was also silently swallowing `app/storage/` — the actual
source package implementing `FileStore`/`MetadataStore` — meaning **the app's own
storage-layer source code had never been committed to git, in any commit.** Anyone
cloning the repo fresh would get a codebase that fails to import. Similarly `*.claude/`
(meant to ignore Claude Code's local settings) matched `.claude/` itself, silently
excluding the entire `.claude/skills/` directory — including this skill and
`run-marketing-app`'s `SKILL.md`/`smoke.sh` — from version control.

Run this check every time:

```bash
# 1. Find directories that share a name with something gitignore might target
find . -type d -name "storage" -not -path "*/.venv/*" -not -path "*/node_modules/*"
find . -maxdepth 1 -name ".*"   # dotdirs at root — check each against .gitignore intent

# 2. For any source file you'd expect to be tracked, confirm it actually is
git ls-files app/ | wc -l                      # sanity count
git ls-files app/storage app/api app/core      # spot-check every app/ subpackage

# 3. Ask git directly why something is (or would be) ignored
git check-ignore -v <path>

# 4. The full-repo tell: list everything gitignore is currently hiding and eyeball it
git status --ignored --short | grep '^!!'
```

If `git status --ignored` shows something that is obviously real source code (not a
venv, cache, or build artifact), that's the bug. Fix by anchoring the pattern to the
repo root with a leading `/` (`/storage/` instead of `storage/`), then re-run the
`git ls-files` spot-check to confirm the real source now shows as trackable
(`git status --short` should show it `??` if genuinely never committed before).

### 5. Repo clutter — stray venvs and build artifacts in the wrong place

```bash
find . -maxdepth 3 -type d -name ".venv" -not -path "./.venv"
```

A `.venv` anywhere other than the repo root usually means `python3.12 -m venv .venv` (or
`pip install -e .`) was run from the wrong working directory — e.g. from inside
`.claude/skills/` or `scripts/` instead of the repo root (see
`run-marketing-app/SKILL.md`'s Troubleshooting section for the exact error this
produces). These are always safe to `rm -rf` — they're not referenced by anything.

Also check for empty leftover data directories from a prior smoke-test run with the
wrong cwd, e.g. `find . -type d -name storage -empty`.

### 6. Verify — before AND after every change

```bash
pytest -q
./.claude/skills/run-marketing-app/smoke.sh
```

Run both **before** touching anything (establish the baseline passes), and **after**
every deletion/dependency change (confirm nothing broke). Never batch every candidate
deletion and verify once at the end — if something breaks, you want to know which
change caused it. The smoke test in particular caught the `tiktoken` false-positive
above; `pytest` alone would not have (there was no test exercising the real upload
chunking path).

## Gotchas

- **An "unused import" can mean the feature was never wired up, not that it's dead.**
  Always read what the imported name was clearly meant to do before deleting it. If in
  doubt, wiring it in correctly is the right fix, not deletion (see the `SYSTEM_PROMPT`
  case in step 1).
- **Grep-confirmed "no direct import" does not mean a dependency is unused.** Some
  packages (tiktoken via `langchain_text_splitters`) are required transitively by
  another dependency without a top-level `import` anywhere in this repo's own code.
  Only `pip uninstall` + reinstall + full smoke test proves a dependency is truly
  removable.
- **`git status` (without `--ignored`) will never show you this class of bug** — a
  gitignore pattern that's silently eating real source code produces a *clean* status,
  which looks like nothing is wrong. You have to explicitly ask `git status --ignored`
  and read through it.
- **Deleting dead code changes test counts — that's expected, not a regression.** This
  repo went from 7 tests to 4 when `tests/test_chunking.py` (testing only the dead
  `chunk_text` function) was removed alongside it.

## Troubleshooting

- **pyflakes reports dozens of hits under `scripts/.venv/...` or similar** — a stray
  venv exists inside a subdirectory (see step 5); pyflakes is linting vendored
  third-party code, not this repo. Delete the stray venv, don't fix the "errors."
  Legitimate hits are always under `app/`, `tests/`, or `scripts/*.py` directly.
- **Removed a dependency, `pip install -e ".[dev]"` succeeds, but the smoke test fails
  with `ImportError: Could not import <package>`** — the dependency was a real
  transitive requirement (see Gotchas). Re-add it to `pyproject.toml`.
