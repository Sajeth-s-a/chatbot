import asyncio
import hashlib
from pathlib import Path

from app.config import settings
from app.llm.ollama_client import OllamaClient, ollama
from app.rag.chunker import Chunk, chunk_blocks
from app.rag.loader import load_docx
from app.rag.vectorstore import vectorstore

EMBED_BATCH = 32


def _chunk_id(doc_name: str, chunk_index: int, text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{doc_name}::{chunk_index}::{h}"


async def _embed_in_batches(client: OllamaClient, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        out.extend(client.embed(batch))
    return out


async def ingest_file(path: Path, client: OllamaClient | None = None) -> dict:
    client = client or ollama
    doc_name = path.name
    blocks = load_docx(path)
    chunks: list[Chunk] = chunk_blocks(blocks, doc_name)
    if not chunks:
        return {"doc_name": doc_name, "chunks": 0, "status": "empty"}

    vectorstore.delete_doc(doc_name)

    texts = [c.text for c in chunks]
    embeddings = await _embed_in_batches(client, texts)
    ids = [_chunk_id(c.doc_name, c.chunk_index, c.text) for c in chunks]
    metadatas = [
        {"doc_name": c.doc_name, "section": c.section, "chunk_index": c.chunk_index}
        for c in chunks
    ]
    vectorstore.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

    return {"doc_name": doc_name, "chunks": len(chunks), "status": "ok"}


async def ingest_dir(directory: Path | None = None) -> list[dict]:
    directory = directory or settings.sops_dir
    files = sorted(p for p in directory.glob("*.docx") if not p.name.startswith("~$"))
    if not files:
        return []
    results = []
    for f in files:
        try:
            results.append(await ingest_file(f))
        except Exception as e:
            results.append({"doc_name": f.name, "chunks": 0, "status": f"failed: {type(e).__name__}: {e}"})
    # Rebuild the hybrid retriever (BM25 index) so /chat sees fresh chunks.
    try:
        from app.rag.retriever import get_retriever

        n = get_retriever().reload()
        print(f"[ingest] hybrid retriever reloaded: {n} chunks")
    except Exception as e:
        print(f"[ingest] retriever reload failed: {e}")
    return results


async def retrieve(query: str, top_k: int | None = None, client: OllamaClient | None = None):
    client = client or ollama
    top_k = top_k or settings.retrieval_top_k
    [embedding] = await client.embed([query])
    return vectorstore.query(query_embedding=embedding, top_k=top_k)


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="RAG ingestion CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="Ingest all .docx in SOPS_DIR")
    sub.add_parser("stats", help="Show collection stats")
    q = sub.add_parser("query", help="Run a retrieval query")
    q.add_argument("text")
    q.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    if args.cmd == "ingest":
        results = asyncio.run(ingest_dir())
        for r in results:
            print(f"  {r['status']:6s}  {r['chunks']:4d} chunks  {r['doc_name']}")
        print(f"Total: {sum(r['chunks'] for r in results)} chunks across {len(results)} docs")
    elif args.cmd == "stats":
        print(vectorstore.stats())
    elif args.cmd == "query":
        hits = asyncio.run(retrieve(args.text, top_k=args.k))
        for h in hits:
            print(f"[{h['score']:.3f}] {h['metadata']['doc_name']} | {h['metadata']['section']}")
            print(f"    {h['text'][:200]}...")
            print()


if __name__ == "__main__":
    _cli()
