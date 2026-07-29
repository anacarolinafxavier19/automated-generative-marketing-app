# marketing-app evaluation dashboard

React (Vite) dashboard for the `marketing-app` backend's evaluation data: agentic-AI
metrics (repair-pass rate, retrieval usage, latency), token usage + cost in EUR, and
dependency/dead-code alerts + improvement suggestions from the `app-evaluator` agent.

## Run

The backend must already be running on `http://localhost:8000` (see
[`../.claude/skills/run-marketing-app/SKILL.md`](../.claude/skills/run-marketing-app/SKILL.md))
— this dashboard is a pure client reading its `/metrics` and `/evaluation-report`
endpoints, it has no backend of its own.

```bash
npm install   # first run only
npm run dev
```

Open `http://localhost:5173`. It polls the backend every 30s; use the Refresh button
for an immediate re-fetch.

To point it at a different backend URL, set `VITE_API_URL` (e.g. in a `.env` file in
this directory): `VITE_API_URL=http://localhost:8001`.

## Data sources

- `GET /metrics` — always available once the backend has served at least one
  `/generate` call; aggregates every row in the `generationmetricsrecord` SQLite table
  (see `../app/storage/metadata_db.py`) into the summary stats and charts.
- `GET /evaluation-report` — 404 until the `app-evaluator` agent
  (`../.claude/agents/app-evaluator.md`) has been run at least once; it writes
  `storage/evaluation-report.json`, which this endpoint serves. The dashboard shows a
  plain empty state (not an error) until that file exists.

Both are wiped whenever `storage/` is reset (e.g. by
`.claude/skills/run-marketing-app/smoke.sh`, which resets it on every run) — re-run the
agent after that to repopulate the alerts/suggestions panels.

## Build

```bash
npm run build      # outputs dashboard/dist/
npm run preview    # serve the production build locally
```

## Stack notes

Vite + React 19, `recharts` for the two charts (latency line, token bar). No other UI
dependencies. Color palette follows the project's dataviz skill conventions — see the
CSS custom properties at the top of `src/index.css` for the light/dark tokens.
