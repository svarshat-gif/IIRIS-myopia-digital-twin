"""Application configuration.

Every setting can be overridden with an environment variable (or a .env file).
See .env.example for the full list.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

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
    jwt_expire_minutes: int = 60 * 24 * 14   # two weeks
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
    llm_provider: str = "none"        # none | ollama | openai_compatible
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 60.0

    # --- Clinical safety ----------------------------------------------------
    disclaimer: str = (
        "Model estimate for clinical decision support only. Not a diagnosis, "
        "not a treatment recommendation, and not evidence of a causal effect."
    )

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
