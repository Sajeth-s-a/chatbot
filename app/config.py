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
    retrieval_top_n_dense: int = 10
    retrieval_top_n_bm25: int = 10
    retrieval_final_k: int = 5
    retrieval_min_score: float = 0.25
    ensemble_weight_dense: float = 0.5
    ensemble_weight_bm25: float = 0.5

    chat_temperature: float = 0.1

    eval_golden_path: Path = Path("data/eval/golden.jsonl")
    eval_reports_dir: Path = Path("data/eval/reports")

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    payments_detective_base_url: str = "https://localhost.csez.zohocorpin.com:8444"
    payments_detective_cookie: str = ""
    payments_detective_zcsrf_token: str = ""
    payments_detective_verify_ssl: bool = True
    payments_detective_timeout: float = 30.0


settings = Settings()
