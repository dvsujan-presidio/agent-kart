from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    foundry_resource: str = ""  # Foundry resource name, e.g. my-foundry-resource
    model_endpoint: str = ""  # e.g. https://my-foundry-resource.cognitiveservices.azure.com/
    model_api_version: str = "2024-12-01-preview"
    model_reasoning_effort: str = "low"  # fast turns; "none" also supported by gpt-5.6
    model_api_key: str = ""
    model_deployment: str = "gpt-5.6-luna"
    model_deployment_fast: str = "gpt-5.6-luna"

    approval_hmac_secret: str = "dev-only-change-me"
    approval_ttl_seconds: int = 90

    voice_mode: bool = True
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    demo_mode: bool = False
    real_store_mode: bool = True
    real_store_search: bool = True
    real_store_cart: bool = True
    real_store_handoff: bool = True
    real_store_replay: bool = False
    real_store_record: bool = False
    real_store_scenarios: str = "camping_weekend,first_apartment,home_gym"
    agent_profile_url_env: str = Field(default="", validation_alias="AGENT_PROFILE_URL")
    store_urls: str = (
        "http://localhost:8201,http://localhost:8202,http://localhost:8203,http://localhost:8204"
    )
    web_url: str = "http://localhost:3000"
    track_interval_seconds: float = 2.0
    saved_address_line1: str = "12, 4th Cross, Indiranagar"
    saved_address_area: str = "Indiranagar"
    saved_address_city: str = "Bengaluru"
    saved_address_pincode: str = "560038"

    @property
    def agent_profile_url(self) -> str | None:
        if self.agent_profile_url_env:
            return self.agent_profile_url_env
        f = Path(__file__).resolve().parents[2] / ".run" / "profile_url"
        return f.read_text().strip() if f.exists() and f.read_text().strip() else None

    default_timezone: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
