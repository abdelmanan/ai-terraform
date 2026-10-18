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

    GENERATED_DIR = str(BASE_DIR / "generated")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    MODEL = "openai/gpt-oss-120b"

    AI_TIMEOUT_SECONDS = 180.0

    AI_MAX_RETRIES = 2

    AI_MAX_TOKENS = 12000

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    TERRAFORM_PLUGIN_CACHE_DIR = str(BASE_DIR / ".terraform-plugin-cache")

    AWS_PROVIDER_VERSION = "5.100.0"

    RANDOM_PROVIDER_VERSION = "3.9.0"

    S3_BUCKET = os.getenv("S3_BUCKET")

    S3_PREFIX = os.getenv("S3_PREFIX", "generated")

    AWS_REGION = os.getenv("AWS_REGION")

    DOWNLOAD_URL_TTL_SECONDS = 3600

    CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS"))

    MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))

    GENERATION_TTL_SECONDS = int(os.getenv("GENERATION_TTL_SECONDS", str(24 * 3600)))


settings = Settings()
