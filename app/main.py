from fastapi import FastAPI

from app.api.generate import router as generate_router
from app.api.upload import router as upload_router

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
