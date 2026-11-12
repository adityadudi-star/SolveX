"""SolveX configuration. All secrets come from environment variables / .env (never the frontend)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

APP_NAME = "SolveX Financial Auditor"
APP_COMPANY = "SolveX"
APP_TAGLINE = "Extract the Facts. Investigate the Trust."
APP_DESCRIPTION = "An intelligent human-in-the-loop financial filing auditing platform."
APP_VERSION = "1.0.0"

# Demonstration defaults. These are configurable, NOT universal accounting standards.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "approval_confidence": 98.0,   # >= : potentially FULLY PASSED
    "review_confidence": 90.0,     # 90..98 : HUMAN CONSIDERATION RECOMMENDED ; < 90 : HUMAN APPROVAL REQUIRED
    "anomaly_mandatory_pct": 50.0,  # |YoY change| >= this -> mandatory human review
    "anomaly_warning_pct": 25.0,   # |YoY change| >= this -> non-blocking warning
    "accounting_tolerance_pct": 0.1,  # A = L + E tolerated difference, % of total assets (pass band)
}

# Guard rails: settings can never be used to bypass mandatory human review.
THRESHOLD_BOUNDS: dict[str, tuple[float, float]] = {
    "approval_confidence": (95.0, 100.0),
    "review_confidence": (80.0, 99.0),
    "anomaly_mandatory_pct": (10.0, 100.0),
    "anomaly_warning_pct": (5.0, 100.0),
    "accounting_tolerance_pct": (0.0, 1.0),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # --- SEC ---
    sec_contact_email: str = ""  # REQUIRED for live SEC calls (SEC fair-access policy)
    sec_rate_limit_per_sec: float = 8.0  # SEC allows 10 req/s; stay below it
    sec_timeout_seconds: float = 30.0
    sec_max_retries: int = 4
    sec_cache_ttl_seconds: int = 24 * 3600
    sec_base_data: str = "https://data.sec.gov"
    sec_base_www: str = "https://www.sec.gov"

    # --- storage ---
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'solvex.db').as_posix()}"
    checkpoint_db_path: str = str(BACKEND_DIR / "data" / "checkpoints.db")
    cache_dir: str = str(BACKEND_DIR / "data" / "sec_cache")

    # --- demo reviewer authentication (NOT production-grade) ---
    reviewer_token: str = "solvex-demo-reviewer"

    # --- LLM (optional; the audit pipeline works without it) ---
    llm_provider: str = "none"  # none | anthropic | openai
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""  # openai-compatible endpoints (e.g. local Ollama / vLLM)
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 45.0
    llm_input_cost_per_mtok: float = 0.0
    llm_output_cost_per_mtok: float = 0.0

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def sec_user_agent(self) -> str:
        return f"SolveX Financial Auditor/{APP_VERSION} (contact: {self.sec_contact_email})"

    @property
    def sec_configured(self) -> bool:
        e = self.sec_contact_email.strip()
        return "@" in e and "." in e.split("@")[-1] and not e.endswith("example.com")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
