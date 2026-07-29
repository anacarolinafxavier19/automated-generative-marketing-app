from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.generate import router as generate_router
from app.api.metrics import router as metrics_router
from app.api.upload import router as upload_router
from app.core.config import get_settings

app = FastAPI(
    title="Automated Generative Marketing Collateral",
    description="Prototype backend: upload sender/receiver context PDFs, generate a tailored article JSON.",
    version="0.1.0",
)

# Local-only frontends (dashboard/ and studio/, Vite dev servers on other ports) need
# to fetch/POST against this API. This is a local prototype with no auth, so a
# wide-open dev CORS policy is fine; tighten this to the real origins before any real
# deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(generate_router)
app.include_router(metrics_router)


@app.get("/health")
def health():
    return {"status": "ok"}


_settings = get_settings()
# Serves extracted logo images so studio/ can render them. `asset_ref` values returned
# by /generate already start with "storage/documents/...", so the frontend can fetch
# `"/" + asset_ref` directly against this mount. StaticFiles requires the directory to
# exist at mount time; Settings.ensure_dirs() doesn't create this subdirectory.
Path(_settings.storage_root / "documents").mkdir(parents=True, exist_ok=True)
app.mount(
    "/storage/documents", StaticFiles(directory=str(_settings.storage_root / "documents")), name="documents"
)
