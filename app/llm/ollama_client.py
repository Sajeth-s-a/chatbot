"""Lightweight sync HTTP wrapper around Ollama.

We deliberately use sync httpx and let FastAPI offload the call via
``run_in_threadpool``. Python 3.14 currently breaks the sniffio asyncio
detection that httpx's async client + httpcore connection pool rely on,
so the sync client is the most robust path until that's fixed upstream.
"""

from typing import Any

import httpx

from app.config import settings


class OllamaClient:
    def __init__(self, host: str | None = None, timeout: float = 120.0):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.timeout = timeout

    async def aclose(self) -> None:  # kept for lifespan compatibility
        return None

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or settings.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, **(options or {})},
        }
        with httpx.Client(base_url=self.host, timeout=self.timeout) as c:
            resp = c.post("/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        payload = {"model": model or settings.embed_model, "input": texts}
        with httpx.Client(base_url=self.host, timeout=self.timeout) as c:
            resp = c.post("/api/embed", json=payload)
            resp.raise_for_status()
            return resp.json()["embeddings"]

    def list_models(self) -> list[str]:
        with httpx.Client(base_url=self.host, timeout=self.timeout) as c:
            resp = c.get("/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]


ollama = OllamaClient()
