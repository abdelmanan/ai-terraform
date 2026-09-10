# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12-slim
ARG TERRAFORM_VERSION=1.15.8

# ---------------------------------------------------------------------------
# Étape 0 : on ne « télécharge » pas Terraform, on prend le binaire officiel.
# C'est un exécutable Go statique, il fonctionne tel quel sur Debian slim.
# ---------------------------------------------------------------------------
FROM hashicorp/terraform:${TERRAFORM_VERSION} AS terraform

# ---------------------------------------------------------------------------
# Étape 1 : build des dépendances Python dans un venv isolé.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# requirements.txt est copié SEUL et AVANT le code : tant qu'il ne change pas,
# Docker réutilise le cache de la couche pip et ne réinstalle rien.
COPY requirements.txt ./

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --requirement requirements.txt

# ---------------------------------------------------------------------------
# Étape 2 : image finale. Elle ne contient ni pip cache, ni compilateur.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO

COPY --from=terraform /bin/terraform /usr/local/bin/terraform
COPY --from=builder   /opt/venv      /opt/venv

WORKDIR /app

# Utilisateur non-root : un conteneur qui exécute du code généré par une IA
# n'a aucune raison de tourner en root.
RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser backend/ ./backend/

# GENERATED_DIR et TF_PLUGIN_CACHE_DIR (backend/config.py) sont relatifs à
# /app : ils doivent exister et appartenir à appuser avant le USER.
RUN mkdir -p /app/generated /app/.terraform-plugin-cache \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Pas de curl dans l'image : le healthcheck utilise le Python déjà présent.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Forme exec (pas de shell), host 0.0.0.0 pour être joignable hors du conteneur,
# et surtout PAS de --reload : c'est un flag de développement.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
