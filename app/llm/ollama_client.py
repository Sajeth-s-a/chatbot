from typing import Any

import httpx

from app.config import settings


class OllamaClient:
    def __init__(self, host: str | None = None, timeout: float = 120.0):
        self.host = (host or settings.ollama_host).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.host, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
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
        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        payload = {"model": model or settings.embed_model, "input": texts}
        resp = await self._client.post("/api/embed", json=payload)
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def list_models(self) -> list[str]:
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]


ollama = OllamaClient()
