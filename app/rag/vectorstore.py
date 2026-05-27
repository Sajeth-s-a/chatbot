from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


class VectorStore:
    def __init__(self) -> None:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_doc(self, doc_name: str) -> int:
        existing = self.collection.get(where={"doc_name": doc_name})
        ids = existing.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        out: list[dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append(
                {
                    "id": i,
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                    "score": 1.0 - dist,
                }
            )
        return out

    def stats(self) -> dict[str, Any]:
        count = self.collection.count()
        sample = self.collection.get(limit=count if count < 5000 else 5000)
        docs = sorted({m.get("doc_name") for m in sample.get("metadatas", []) if m})
        return {"chunk_count": count, "documents": docs}


vectorstore = VectorStore()
