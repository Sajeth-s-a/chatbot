from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
    chat_model_present: bool
    embed_model_present: bool
    available_models: list[str]


class SmokeRequest(BaseModel):
    prompt: str = Field(default="Reply with the single word: pong.")


class SmokeResponse(BaseModel):
    model: str
    reply: str
