import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routes.generate import router as generate_router
from backend.exceptions.exception_handler import register_exception_handlers

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)

app = FastAPI(
    title="AI Terraform Landing Zone Generator",
    description="Generate Terraform Landing Zones using AI",
    version="1.0.0"
)

# Autoriser le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gestion centralisée des erreurs
register_exception_handlers(app)

# Routes
app.include_router(generate_router, prefix="/api")

@app.get("/")
def home():
    return {
        "application": "AI Terraform Landing Zone Generator",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Le navigateur la réclame à chaque chargement de page : évite un 404 dans les logs
    return Response(status_code=204)
