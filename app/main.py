from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from app.api import chat as chat_api
from app.api import eval as eval_api
from app.api import ingest as ingest_api
from app.config import settings
from app.llm.ollama_client import ollama
from app.rag.retriever import get_retriever
from app.schemas import HealthResponse, SmokeRequest, SmokeResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the hybrid retriever (loads chunks from Chroma -> builds BM25).
    n = get_retriever().reload()
    print(f"[startup] Hybrid retriever ready: {n} chunks indexed (dense + BM25)")
    yield
    await ollama.aclose()


app = FastAPI(title="MyChatbot — KYC/AML RAG", version="0.1.0", lifespan=lifespan)
app.include_router(ingest_api.router)
app.include_router(chat_api.router)
app.include_router(eval_api.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        models = ollama.list_models()
        reachable = True
    except (httpx.HTTPError, OSError):
        models = []
        reachable = False

    def _has(name: str) -> bool:
        return any(m == name or m.startswith(f"{name}:") for m in models)

    return HealthResponse(
        status="ok" if reachable else "degraded",
        ollama_reachable=reachable,
        chat_model_present=_has(settings.chat_model),
        embed_model_present=_has(settings.embed_model),
        available_models=models,
    )


@app.post("/smoke", response_model=SmokeResponse)
async def smoke(req: SmokeRequest) -> SmokeResponse:
    try:
        reply = ollama.chat([{"role": "user", "content": req.prompt}])
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama call failed: {e}") from e
    return SmokeResponse(model=settings.chat_model, reply=reply)
