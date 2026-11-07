from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite://"
    ollama_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen3:8b"

    @field_validator("ollama_url")
    @classmethod
    def local_endpoint(cls, value: str) -> str:
        # Closed allowlist: configuration must not silently enable a remote provider.
        if value not in ("http://127.0.0.1:11434", "http://localhost:11434", "http://ollama:11434"):
            raise ValueError("Only the local Ollama endpoint is supported")
        return value

    @field_validator("ai_model")
    @classmethod
    def local_model(cls, value: str) -> str:
        if value != "qwen3:8b":
            raise ValueError("This release supports only qwen3:8b")
        return value
