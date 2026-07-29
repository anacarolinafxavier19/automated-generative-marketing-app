# marketing-app studio

The content-creation web app: upload a sender PDF, type the target (receiver) company
name, describe what you want, and get a rendered marketing brochure — text, images
(logos extracted from the sender PDF), and tables, all grounded in real content.

## Run

The backend must already be running on `http://localhost:8000` (see
[`../.claude/skills/run-marketing-app/SKILL.md`](../.claude/skills/run-marketing-app/SKILL.md)) —
this is a pure client over its API.

```bash
npm install   # first run only
npm run dev
```

Open `http://localhost:5173` (or whatever port Vite picks if 5173 is taken by
`dashboard/` — run studio on a different port explicitly if running both at once:
`npm run dev -- --port 5174`).

To point it at a different backend URL, set `VITE_API_URL` (e.g. in a `.env` file in
this directory): `VITE_API_URL=http://localhost:8001`.

## How the receiver side works

1. Type the target company's name and hit generate — the backend researches it live
   via Gemini's Google Search grounding tool (no upload needed). This keeps the same
   "never invent facts" guarantee as the uploaded-PDF path; the grounding source is
   just a live search instead of a document.
2. Grounded search sits on a **much stricter quota** than plain generation, even on
   paid Gemini tiers, and free-tier keys often have none available. Two free fallbacks
   for when that quota is exhausted:
   - Set `TAVILY_API_KEY` in the backend's `.env` (sign up free at
     https://app.tavily.com, no card needed) — the backend automatically falls back to
     Tavily's search API on a `429` and generation just succeeds, no UI change needed.
   - Or open "Optional: upload a PDF for this company instead" and upload one — the
     backend automatically uses it instead of researching live once it exists (see
     `receiver_has_docs` check in `../app/api/generate.py`).
   If generation still fails with a quota error (no Tavily key configured), the app
   shows a hint pointing at the PDF-upload fallback.

## Output

The rendered brochure uses the model-chosen theme colors, any extracted sender/receiver
logo images, and up to 2 model-generated tables (comparison/spec tables — omitted if
nothing in the grounding context was actually tabular; the model is instructed not to
invent one just to fill space). "Print / Save as PDF" uses the browser's native print
dialog with print-only CSS (`@media print` in `src/App.css`) that hides everything but
the brochure itself — no server-side PDF rendering.

## Build

```bash
npm run build      # outputs studio/dist/
npm run preview    # serve the production build locally
```
