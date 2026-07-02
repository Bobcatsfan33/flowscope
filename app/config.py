"""Central configuration, loaded from environment / `.env`.

All API keys are optional. Helper properties expose which capabilities are
available so the aggregator can degrade gracefully when a key is absent.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- API keys (all optional) ---------------------------------------------
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    tradier_token: str = Field(default="", alias="TRADIER_TOKEN")
    tradier_env: str = Field(default="sandbox", alias="TRADIER_ENV")
    fmp_api_key: str = Field(default="", alias="FMP_API_KEY")
    alphavantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    newsapi_key: str = Field(default="", alias="NEWSAPI_KEY")
    quiver_api_key: str = Field(default="", alias="QUIVER_API_KEY")

    # --- SEC EDGAR (no key, but requires descriptive UA) ---------------------
    sec_user_agent: str = Field(
        default="FlowScope/1.0 (contact@example.com)", alias="SEC_USER_AGENT"
    )

    # --- Engine tuning -------------------------------------------------------
    refresh_interval_seconds: int = Field(default=300, alias="REFRESH_INTERVAL_SECONDS")
    universe_refresh_hours: int = Field(default=24, alias="UNIVERSE_REFRESH_HOURS")
    max_tickers_per_cycle: int = Field(default=120, alias="MAX_TICKERS_PER_CYCLE")
    http_timeout_seconds: float = Field(default=20.0, alias="HTTP_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Capability flags ----------------------------------------------------
    @property
    def has_finnhub(self) -> bool:
        return bool(self.finnhub_api_key.strip())

    @property
    def has_tradier(self) -> bool:
        return bool(self.tradier_token.strip())

    @property
    def has_fmp(self) -> bool:
        return bool(self.fmp_api_key.strip())

    @property
    def has_alphavantage(self) -> bool:
        return bool(self.alphavantage_api_key.strip())

    @property
    def has_newsapi(self) -> bool:
        return bool(self.newsapi_key.strip())

    @property
    def has_quiver(self) -> bool:
        return bool(self.quiver_api_key.strip())

    @property
    def tradier_base_url(self) -> str:
        return (
            "https://api.tradier.com"
            if self.tradier_env.strip().lower() == "production"
            else "https://sandbox.tradier.com"
        )

    def capability_report(self) -> dict[str, bool | str]:
        """Human-readable map of which integrations are active.

        Booleans mark integrations with live code paths. FMP / NewsAPI /
        Quiver / AlphaVantage are *reserved hooks*: their keys are read from
        the environment but no code path consumes them yet, so they report an
        honest string status instead of masquerading as live capabilities.
        """

        def reserved(configured: bool) -> str:
            return (
                "configured (not yet used)"
                if configured
                else "not configured (reserved hook)"
            )

        return {
            "yahoo_options": True,  # always available, no key
            "sec_edgar": True,  # always available, no key
            "usaspending_contracts": True,  # always available, no key
            "senate_disclosures": True,  # always available, no key
            "finnhub": self.has_finnhub,
            "tradier": self.has_tradier,
            "fmp": reserved(self.has_fmp),
            "newsapi": reserved(self.has_newsapi),
            "quiver": reserved(self.has_quiver),
            "alphavantage": reserved(self.has_alphavantage),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
