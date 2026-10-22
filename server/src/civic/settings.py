"""Application configuration. Environment-first; see .env.example at repo root."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    civic_environment: Literal["dev", "staging", "prod"] = "dev"
    civic_log_level: str = "INFO"
    civic_cors_origins: str = "*"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me-dev"
    neo4j_database: str = "neo4j"

    embedding_base_url: str = "http://localhost:8081"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    llm_provider: Literal["openai", "azure", "anthropic", "local"] = "local"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:14b-instruct"
    llm_api_key: str = ""
    llm_timeout_s: float = 90.0

    retrieval_vector_k: int = 40
    retrieval_fulltext_k: int = 40
    retrieval_final_k: int = 8
    retrieval_min_score: float = 0.35
    enable_rerank: bool = False
    reranker_base_url: str = ""

    admin_token: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.civic_cors_origins.strip()
        return ["*"] if raw == "*" else [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
