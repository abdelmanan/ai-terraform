import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


def _parse_cors_origins(raw_value):

    if not raw_value:
        return DEFAULT_CORS_ORIGINS

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    return origins or DEFAULT_CORS_ORIGINS


class Settings:

    PROJECT_NAME = "AI Terraform Landing Zone Generator"

    VERSION = "1.0.0"

    # Absolute so generated projects always land in the repo, whatever the
    # working directory uvicorn was started from.
    GENERATED_DIR = str(BASE_DIR / "generated")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    MODEL = "openai/gpt-oss-120b"

    # The SDK defaults to 600s, which would pin a worker for 10 minutes on a
    # hanging call and made our own APITimeoutError handler unreachable.
    AI_TIMEOUT_SECONDS = 60.0

    AI_MAX_RETRIES = 2

    # A full landing zone plus the repair prompt overflowed the previous 6000
    # budget, and the truncated answer silently replaced good files.
    AI_MAX_TOKENS = 12000

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    TERRAFORM_PLUGIN_CACHE_DIR = str(BASE_DIR / ".terraform-plugin-cache")

    CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS"))


settings = Settings()