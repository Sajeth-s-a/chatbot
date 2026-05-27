from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    chat_model: str = "qwen:4b"
    embed_model: str = "nomic-embed-text"

    sops_dir: Path = Path("resources")
    chroma_dir: Path = Path("data/chroma")
    chroma_collection: str = "sops"

    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.25

    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
