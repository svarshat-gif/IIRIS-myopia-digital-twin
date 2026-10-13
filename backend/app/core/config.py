"""Application configuration.

Every setting can be overridden with an environment variable (or a .env file).
See .env.example for the full list.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from typing import Literal
from pydantic import model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", str(BASE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "Iiris API"
    product_name: str = "Iiris"
    api_version: str = "0.1.0"
    environment: str = "development"

    # --- Database ----------------------------------------------------------
    # SQLite by default so the project runs with zero infrastructure.
    # Swap to Postgres with:
    #   DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/myopia_twin
    database_url: str = f"sqlite:///{BASE_DIR / 'artifacts' / 'myopia_twin.db'}"

    # --- ML artifacts ------------------------------------------------------
    artifacts_dir: Path = BASE_DIR / "artifacts"
    model_bundle_name: str = "progression_model.joblib"

    # --- Security ----------------------------------------------------------
    # When set, every /api/v1 request must send `X-API-Key: <value>`.
    # This is a deployment-level gate, separate from user sign-in.
    api_key: str = ""

    # Session signing key. MUST be set in production. When left empty a random
    # key is generated at startup, so every restart signs users out -- a safe
    # default with an obvious symptom.
    jwt_secret: str = ""
    jwt_expire_minutes: int = 30
    auth_gate: Literal["jwt", "api_key"] = "jwt"
    rate_limit_enabled: bool = True
    max_request_bytes: int = 11 * 1024 * 1024
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    # --- Evidence retrieval -------------------------------------------------
    europe_pmc_base_url: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ncbi_api_key: str = ""            # optional, raises PubMed rate limit
    evidence_contact_email: str = ""  # polite identification for NCBI
    evidence_timeout_seconds: float = 8.0
    evidence_offline: bool = False    # force the bundled local corpus

    # --- Agent LLM ----------------------------------------------------------
    # The agent is fully functional with NO LLM (deterministic tool router).
    # An LLM only rephrases tool output into prose; it never invents values.
    llm_provider: Literal["none", "ollama"] = "none"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_timeout_seconds: float = 60.0

    # --- Clinical safety ----------------------------------------------------
    disclaimer: str = (
        "Model estimate for clinical decision support only. Not a diagnosis, "
        "not a treatment recommendation, and not evidence of a causal effect."
    )

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.llm_provider == "ollama":
            url = urlparse(self.llm_base_url)
            if url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.scheme not in {"http", "https"}:
                raise ValueError("Ollama must use a loopback endpoint")
        if not 1 <= self.jwt_expire_minutes <= 60:
            raise ValueError("JWT_EXPIRE_MINUTES must be between 1 and 60")
        if self.environment == "production":
            failures = []
            if len(self.jwt_secret) < 32:
                failures.append("JWT_SECRET must have at least 32 characters")
            if self.auth_gate == "api_key" and len(self.api_key) < 32:
                failures.append("API_KEY gate requires at least 32 characters")
            if not self.database_url.startswith(("postgresql+psycopg://", "postgresql://")):
                failures.append("DATABASE_URL must use Postgres")
            if not self.cors_origin_list or any(urlparse(o).scheme != "https" or '*' in o or
                not urlparse(o).hostname or urlparse(o).path not in {"", "/"} for o in self.cors_origin_list):
                failures.append("CORS_ORIGINS must be explicit HTTPS origins")
            if self.storage_backend != "s3" or not all((self.s3_endpoint_url, self.s3_bucket,
                                                          self.s3_access_key_id, self.s3_secret_access_key)):
                failures.append("Production uploads require configured S3-compatible storage")
            if failures:
                raise ValueError("; ".join(failures))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_path(self) -> Path:
        return self.artifacts_dir / self.model_bundle_name


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.artifacts_dir.mkdir(parents=True, exist_ok=True)
    if not s.jwt_secret:
        import secrets as _secrets
        s.jwt_secret = _secrets.token_urlsafe(48)
    return s


settings = get_settings()
