from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.generate import router as generate_router
from backend.exceptions.exception_handler import register_exception_handlers

app = FastAPI(
    title="AI Terraform Landing Zone Generator",
    description="Generate Terraform Landing Zones using AI",
    version="1.0.0"
)

# Autoriser le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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