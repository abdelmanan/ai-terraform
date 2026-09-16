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
    # hanging call and made our own APITimeoutError handler unreachable. But 60s
    # was the opposite mistake: a full landing zone is a long completion, and
    # cutting it off threw away the whole generation to save two minutes. We
    # would rather answer slowly than not answer at all, so the budget is
    # generous and merely bounded.
    AI_TIMEOUT_SECONDS = 180.0

    AI_MAX_RETRIES = 2

    # A full landing zone plus the repair prompt overflowed the previous 6000
    # budget, and the truncated answer silently replaced good files.
    AI_MAX_TOKENS = 12000

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    TERRAFORM_PLUGIN_CACHE_DIR = str(BASE_DIR / ".terraform-plugin-cache")

    # Left free, the model picked a range like `~> 5.0` and the registry
    # resolved it to whatever was newest that day. When that landed on a version
    # the plugin cache did not hold, `terraform init` spent its whole 180s
    # budget downloading a 675 MB provider and the generation failed on a valid
    # project. Pinning keeps every init on the cached copy, well inside the
    # budget. Bump these together with the cached versions, and warm the cache
    # with one `terraform init` before relying on the new ones.
    AWS_PROVIDER_VERSION = "5.100.0"

    RANDOM_PROVIDER_VERSION = "3.9.0"

    # Sans bucket, les archives restent sur le disque local et sont servies par
    # /api/download : c'est le mode développement (./run.sh) et celui des tests.
    # Avec un bucket, le conteneur devient jetable — le lien de téléchargement
    # ne dépend plus de l'instance qui a produit le fichier.
    S3_BUCKET = os.getenv("S3_BUCKET")

    S3_PREFIX = os.getenv("S3_PREFIX", "generated")

    AWS_REGION = os.getenv("AWS_REGION")

    # Durée de validité de l'URL présignée. Assez large pour que l'utilisateur
    # parte manger entre la génération et le clic, assez courte pour qu'un lien
    # qui fuite ne serve pas éternellement.
    DOWNLOAD_URL_TTL_SECONDS = 3600

    CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS"))

    # Chaque génération lance jusqu'à trois `terraform init` et occupe un
    # worker plusieurs minutes. Sur une petite instance, trois en parallèle
    # suffisent à saturer mémoire et CPU : au-delà, on répond 429 tout de suite
    # plutôt que de tout ralentir jusqu'au timeout.
    MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))

    # Les générations locales (projet + .terraform + zip) sont purgées passé
    # ce délai. En mode S3 l'archive vit dans le bucket : sa durée de vie est
    # celle de la règle de cycle de vie du bucket, pas celle-ci.
    GENERATION_TTL_SECONDS = int(os.getenv("GENERATION_TTL_SECONDS", str(24 * 3600)))


settings = Settings()