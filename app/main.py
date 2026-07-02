import os

from fastapi import FastAPI

from app.config import get_settings
from app.routers import admin, webhook


def _materialize_service_account_file() -> None:
    """
    If GOOGLE_SERVICE_ACCOUNT_JSON (raw JSON) was supplied instead of a file
    path, write it to disk once at startup and point
    GOOGLE_APPLICATION_CREDENTIALS at it. Lets Railway/Render deployments
    just paste the key JSON into a single env var.
    """
    settings = get_settings()
    if settings.google_service_account_json and not os.path.exists(settings.google_application_credentials):
        with open(settings.google_application_credentials, "w") as f:
            f.write(settings.google_service_account_json)


_materialize_service_account_file()

app = FastAPI(
    title="Dental Appointment Booking Agent",
    description="Backend for a VAPI-powered dental clinic voice receptionist.",
    version="1.0.0",
)

app.include_router(webhook.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "dental-booking-agent"}


@app.get("/health")
def health():
    return {"status": "healthy"}
