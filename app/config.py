"""
Centralized application settings, loaded from environment variables / .env.
Keeping this in one place means every service (Calendar, Twilio, Firestore)
reads credentials the same way, and swapping test <-> prod creds is a
one-file change.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    port: int = 8000
    environment: str = "development"
    admin_api_key: str = "change-me"

    # VAPI
    vapi_webhook_secret: str = ""

    # Google Calendar / Firestore auth
    # Either point to a JSON key file on disk...
    google_application_credentials: str = "./service-account.json"
    # ...or paste the raw JSON key contents into one env var (handy on
    # Railway/Render where uploading a file isn't convenient). If set, this
    # takes priority and gets written to disk on startup (see main.py).
    google_service_account_json: str = ""
    google_calendar_id: str = ""
    clinic_timezone: str = "Asia/Kolkata"
    appointment_duration_minutes: int = 30

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    test_patient_phone_number: str = ""

    # Firestore
    # Postgres Database
    database_url: str = "postgresql://postgres:123456@localhost:5432/dental_agent"
    
    # Ngrok
    ngrok_url: str = ""

@lru_cache
def get_settings() -> Settings:
    return Settings()
