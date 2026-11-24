"""Application configuration.

All settings come from environment variables (or `backend/.env`). Nothing secret is
hardcoded. `Settings.voice_mode` decides whether the real Pipecat voice pipeline
(ElevenLabs STT/TTS + Gemini) is used or the clearly-labelled development mock.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "app" / "data" / "clinic.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General -----------------------------------------------------------
    app_name: str = "Voice AI Doctor Appointment Assistant"
    clinic_name: str = "Brightwell Family Clinic"
    clinic_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"
    database_path: Path = DEFAULT_DB_PATH
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # How many days ahead seeded availability is generated (relative to today).
    booking_horizon_days: int = 14

    # --- Voice mode --------------------------------------------------------
    # auto  -> "live" when every API key is present, otherwise "mock"
    # live  -> always use the real pipeline (fails clearly if a key is missing)
    # mock  -> always use the text-only development mock (no external calls)
    voice_mode: Literal["auto", "live", "mock"] = "auto"

    # --- Google Gemini (LLM) ----------------------------------------------
    google_api_key: str = Field(default="", repr=False)
    # Empty -> Pipecat's default Gemini model for the installed version.
    gemini_model: str = ""

    # --- ElevenLabs (STT + TTS) -------------------------------------------
    elevenlabs_api_key: str = Field(default="", repr=False)
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    # realtime -> WebSocket streaming STT (scribe_v2_realtime)
    # batch    -> file-based STT per utterance (scribe_v2), segmented by Silero VAD
    elevenlabs_stt_mode: Literal["realtime", "batch"] = "realtime"

    # --- Call limits -------------------------------------------------------
    call_idle_timeout_secs: int = 120
    call_max_duration_secs: int = 600
    tool_timeout_secs: float = 10.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def missing_live_keys(self) -> list[str]:
        missing = []
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY")
        if not self.elevenlabs_api_key:
            missing.append("ELEVENLABS_API_KEY")
        return missing

    @property
    def effective_voice_mode(self) -> Literal["live", "mock"]:
        if self.voice_mode == "mock":
            return "mock"
        if self.voice_mode == "live":
            return "live"
        return "live" if not self.missing_live_keys else "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
