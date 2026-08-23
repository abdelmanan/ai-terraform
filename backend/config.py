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

    GENERATED_FOLDER = "generated"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    MODEL = "openai/gpt-oss-120b"

    TERRAFORM_PLUGIN_CACHE_DIR = str(BASE_DIR / ".terraform-plugin-cache")

    CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS"))


settings = Settings()