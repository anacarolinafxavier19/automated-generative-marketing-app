from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.generate import router as generate_router
from app.api.upload import router as upload_router
from app.core.config import get_settings

app = FastAPI(
    title="Automated Generative Marketing Collateral",
    description="Prototype backend: upload sender/receiver context PDFs, generate a tailored article JSON.",
    version="0.1.0",
)

app.include_router(upload_router)
app.include_router(generate_router)


@app.get("/health")
def health():
    return {"status": "ok"}


_settings = get_settings()
# Serves generated/extracted assets (logos, etc). `asset_ref` values returned by
# /generate already start with "storage/documents/...", so the UI can fetch
# `"/" + asset_ref` directly against this mount.
app.mount(
    "/storage/documents", StaticFiles(directory=str(_settings.storage_root / "documents")), name="documents"
)
# Demo UI: a static single-page app driving the two API endpoints above.
app.mount("/ui", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True), name="ui")
