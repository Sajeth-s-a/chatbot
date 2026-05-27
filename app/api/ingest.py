from fastapi import APIRouter
from pydantic import BaseModel

from app.rag.pipeline import ingest_dir
from app.rag.vectorstore import vectorstore

router = APIRouter(prefix="", tags=["ingest"])


class IngestResult(BaseModel):
    doc_name: str
    chunks: int
    status: str


class IngestResponse(BaseModel):
    results: list[IngestResult]
    total_chunks: int


class StatsResponse(BaseModel):
    chunk_count: int
    documents: list[str]


@router.post("/ingest", response_model=IngestResponse)
async def ingest() -> IngestResponse:
    results = await ingest_dir()
    return IngestResponse(
        results=[IngestResult(**r) for r in results],
        total_chunks=sum(r["chunks"] for r in results),
    )


@router.get("/documents", response_model=StatsResponse)
async def documents() -> StatsResponse:
    s = vectorstore.stats()
    return StatsResponse(chunk_count=s["chunk_count"], documents=s["documents"])
