# AI Terraform Landing Zone Generator — Vue d'ensemble du projet

Document généré le 2026-08-18. Il contient : l'arborescence du projet, une explication complète de son fonctionnement, puis le code source intégral de chaque fichier.

---

## 1. Arborescence du projet

Fichiers de code et de configuration versionnés (hors `.venv/`, `generated/`, `__pycache__/`, `.git/` qui sont des artefacts d'exécution ou de dépendances) :

```
AI-Terraform-Landing-Zone-Generator/
├── .env                                  # secrets locaux (GROQ_API_KEY) — non inclus dans ce document
├── .gitignore
├── pytest.ini
├── README.md                             # vide
├── requirements.txt
│
├── backend/
│   ├── app.py                            # point d'entrée FastAPI
│   ├── config.py                         # settings globaux (clé API, modèle, dossiers)
│   │
│   ├── exceptions/
│   │   ├── api_exception.py              # exception métier ApiException
│   │   └── exception_handler.py          # handlers FastAPI centralisés
│   │
│   ├── parser/
│   │   └── terraform_parser.py           # parseur de la réponse IA -> fichiers Terraform
│   │
│   ├── prompts/
│   │   ├── landing_zone.py               # template de prompt envoyé à l'IA
│   │   └── aws_prompt.py.save            # ⚠️ fichier orphelin (brouillon jamais nettoyé, non utilisé)
│   │
│   ├── routes/
│   │   └── generate.py                   # endpoint POST /api/generate, orchestration du pipeline
│   │
│   ├── schemas/
│   │   └── generate_request.py           # modèle Pydantic de la requête entrante
│   │
│   ├── services/
│   │   ├── prompt_service.py             # sélection du bon template de prompt
│   │   ├── terraform_service.py          # écriture des fichiers générés sur disque
│   │   ├── terraform_validator_service.py# exécution de `terraform init` / `terraform validate`
│   │   └── ai/
│   │       └── terraform_ai_service.py   # client Groq (SDK OpenAI-compatible)
│   │
│   └── utils/
│       └── zip_manager.py                # création du zip téléchargeable
│
├── docs/                                 # vide avant ce document
├── templates/                            # vide
│
└── tests/
    ├── conftest.py                       # fixtures partagées (payload valide, réponse IA valide, mocks httpx)
    ├── test_exception_handlers.py
    ├── test_generate_route.py
    ├── test_parser.py
    ├── test_schemas.py
    ├── test_terraform_ai_service.py
    ├── test_terraform_validator_service.py
    └── test_zip_manager.py
```

**Dossiers hors du répertoire de travail git (ignorés)** : `.venv/` (environnement Python), `generated/` (sortie runtime : un dossier + un `.zip` par projet généré via l'API), `.terraform-plugin-cache/` (cache partagé des providers Terraform), `__pycache__/`, `.pytest_cache/`.

---

## 2. Explication complète

### 2.1 Ce que fait l'application

C'est une **API backend FastAPI** qui génère, à la demande, un projet Terraform complet représentant une "AWS Landing Zone" (VPC, subnets publics/privés, IGW, route tables, security groups, NAT Gateway optionnelle, CloudTrail/CloudWatch/S3 logs optionnels), en s'appuyant sur un LLM hébergé chez **Groq** (via le SDK `openai`, pointé sur `https://api.groq.com/openai/v1`, modèle `openai/gpt-oss-120b`).

Le client envoie un JSON décrivant l'infrastructure voulue → le backend construit un prompt → interroge le LLM → parse sa réponse texte en fichiers `.tf` → les écrit sur disque → **valide réellement** le résultat en exécutant le CLI `terraform` (`init` + `validate`) → zippe le tout → renvoie un JSON avec le statut, la liste des fichiers, le résultat de validation et le chemin du zip.

### 2.2 Flux d'une requête `POST /api/generate`

Orchestré entièrement dans `backend/routes/generate.py`, sans logique métier dans la route elle-même (chaque étape est déléguée à un service dédié) :

```
1. GenerateRequest (Pydantic)        valide le JSON entrant (schemas/generate_request.py)
        │
2. PromptService.build_prompt()      choisit le template ("landing-zone") et construit le prompt texte
        │                            (services/prompt_service.py -> prompts/landing_zone.py)
        │
3. TerraformAIService.generate()     appelle Groq, gère toutes les erreurs réseau/API,
        │                            renvoie le texte brut de la réponse
        │                            (services/ai/terraform_ai_service.py)
        │
4. TerraformParser.parse()           découpe le texte en {nom_fichier: contenu},
        │                            vérifie que les fichiers obligatoires sont présents et non vides
        │                            (parser/terraform_parser.py)
        │
5. TerraformService.save()           écrit chaque fichier dans generated/<project_name>/,
        │                            en bloquant toute tentative d'écriture hors de ce dossier
        │                            (services/terraform_service.py)
        │
6. TerraformValidatorService.validate() lance `terraform init` puis `terraform validate`
        │                            en sous-processus réel, avec cache de plugins partagé
        │                            (services/terraform_validator_service.py)
        │
7. create_zip()                      zippe le dossier généré (hors .terraform/ et lock file)
        │                            (utils/zip_manager.py)
        │
8. Réponse JSON                      { status, project, generated_files, validation, download }
```

Toute erreur à n'importe quelle étape lève une `ApiException(message, status_code)`, interceptée par les handlers globaux (`exceptions/exception_handler.py`) qui la transforment en réponse JSON `{"status": "error", "message": ...}` avec le bon code HTTP (429 rate limit, 502 réponse IA invalide, 504 timeout, 500 erreur serveur, 422 payload invalide, etc.).

### 2.3 Rôle de chaque fichier

| Fichier | Rôle |
|---|---|
| `backend/app.py` | Crée l'app FastAPI, active le CORS (`*` — permissif), enregistre les handlers d'erreurs, monte le router sous `/api`, expose `/` et `/health`. |
| `backend/config.py` | Objet `settings` unique : clé API Groq (lue depuis `.env` via `python-dotenv`), nom du modèle, dossier de sortie `generated`, chemin du cache de plugins Terraform. |
| `backend/exceptions/api_exception.py` | Exception métier custom portant un `message` et un `status_code` HTTP — utilisée par tous les services pour signaler un échec typé. |
| `backend/exceptions/exception_handler.py` | Branche 3 handlers FastAPI : `ApiException` → JSON avec le code voulu ; `RequestValidationError` → 422 avec détails Pydantic ; toute autre `Exception` → 500 générique. |
| `backend/parser/terraform_parser.py` | Parseur "en production" (celui réellement utilisé par la route). Découpe la réponse IA sur les marqueurs `### fichier` / `BEGIN_.../END_...`, exige que les 6 fichiers obligatoires (`provider.tf`, `main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars`, `README.md`) soient présents et non vides, lève des `ApiException` (502) sinon. |
| `backend/prompts/landing_zone.py` | Le prompt système/utilisateur envoyé à l'IA : rôle ("Senior Cloud Architect"), paramètres du projet interpolés depuis la requête, exigences d'infrastructure, règles de compatibilité provider AWS récentes (`aws_eip.domain` au lieu de `vpc = true`, ressources S3 dédiées, etc.), format de sortie strict attendu. |
| `backend/prompts/aws_prompt.py.save` | Fichier orphelin : brouillon antérieur d'un générateur de prompt plus simple (signature `build_prompt(project_name, region)`), jamais importé nulle part. Reste versionné dans git par oubli — à supprimer. |
| `backend/routes/generate.py` | Unique endpoint métier. Instancie les services (au niveau module, donc partagés entre requêtes) et exécute le pipeline décrit en 2.2. |
| `backend/schemas/generate_request.py` | `GenerateRequest` (Pydantic) : `cloud`, `project_name`, `region`, `template`, nombre d'AZ/subnets, flags `enable_*`. Un validateur dédié sur `project_name` rejette tout ce qui n'est pas `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$` — c'est ce qui empêche un `project_name` du type `../evil` d'atteindre le système de fichiers. |
| `backend/services/prompt_service.py` | Sélectionne le bon constructeur de prompt selon `request.template` (seul `"landing-zone"` existe ; tout autre valeur → `ApiException` 400). |
| `backend/services/terraform_service.py` | Écrit les fichiers parsés dans `generated/<project_name>/`. Résout chaque chemin de fichier en absolu et vérifie via `os.path.commonpath` qu'il reste bien confiné sous le dossier du projet, sinon lève une `ApiException` 502 — protection contre un nom de fichier malveillant/halluciné par l'IA (ex. `../../evil.py`). |
| `backend/services/terraform_validator_service.py` | Exécute réellement `terraform init -input=false` puis `terraform validate` via `subprocess.run`, avec un `TF_PLUGIN_CACHE_DIR` partagé (évite de retélécharger le provider AWS à chaque génération), timeout de 60s, et convertit les erreurs système (binaire absent, timeout) en `ApiException`. |
| `backend/services/ai/terraform_ai_service.py` | Client Groq. Envoie le prompt (`temperature=0.2`, `max_tokens=6000`, `reasoning_effort=low`), et mappe finement chaque exception du SDK OpenAI vers un code HTTP pertinent : timeout→504, rate limit→429, auth→500, connexion→502, erreur API générique→502, réponse tronquée (`finish_reason == "length"`)→502, réponse vide→502. |
| `backend/utils/zip_manager.py` | Zippe récursivement le dossier du projet généré, en excluant `.terraform/` et `.terraform.lock.hcl`, pour produire le fichier téléchargeable. |
| `tests/conftest.py` | Fixtures partagées : requêtes/réponses HTTP factices pour simuler les erreurs Groq, un exemple de réponse IA valide, un payload de requête valide. |
| `tests/test_generate_route.py` | Teste la route bout-en-bout avec tous les services stubbés : succès, propagation d'une validation Terraform échouée, propagation d'une erreur IA/parser, erreur inattendue → 500, et rejet d'un `project_name` malveillant → 422. |
| `tests/test_parser.py` | Teste `TerraformParser` : cas valide, réponse vide, format non reconnu, fichiers requis manquants, fichier vide, nettoyage des marqueurs `BEGIN_TEXT/END_TEXT`. |
| `tests/test_schemas.py` | Teste `GenerateRequest.project_name` sur une liste de noms valides et invalides (dont tentatives de traversée de chemin et d'injection shell), et les valeurs par défaut. |
| `tests/test_terraform_ai_service.py` | Teste `TerraformAIService` en mockant `client.chat.completions.create` : succès, paramètres envoyés, contenu vide, absence de choix, réponse tronquée, et chaque type d'erreur SDK (timeout, connexion, rate limit, auth, erreur générique). |
| `tests/test_terraform_validator_service.py` | Teste `TerraformValidatorService` en mockant `subprocess.run` : succès, arrêt après échec d'`init`, échec de `validate`, binaire `terraform` absent, timeout, et propagation du `TF_PLUGIN_CACHE_DIR` dans l'environnement du sous-processus. |
| `tests/test_zip_manager.py` | Teste `create_zip` : inclusion des fichiers du projet, exclusion de `.terraform/` et `.terraform.lock.hcl`. |
| `tests/test_exception_handlers.py` | Teste les 3 handlers globaux sur une mini-app FastAPI de test : `ApiException` custom, exception générique non gérée, erreur de validation Pydantic. |
| `requirements.txt` | Dépendances Python (FastAPI, Pydantic, openai SDK, uvicorn, pytest...). |
| `.gitignore` | Exclut `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, les artefacts Terraform (`.terraform/`, `*.tfstate`...) et `generated/`. |
| `pytest.ini` | Config pytest : dossier de tests, marker `integration` pour les tests qui frappent réellement Groq/`terraform` (non exécutés par défaut). |

### 2.4 Architecture en couches

```
routes/           orchestration HTTP (aucune logique métier)
  │
schemas/          validation d'entrée
prompts/ + services/prompt_service.py   construction de la demande à l'IA
services/ai/      communication avec le LLM
parser/           structuration de la réponse IA
services/(terraform_service, terraform_validator_service) + utils/zip_manager  matérialisation et vérification du résultat
exceptions/       vocabulaire d'erreur uniforme, transverse à toutes les couches
```

Séparation des responsabilités classique et cohérente pour la taille du projet. Chaque service est injectable/mockable indépendamment, ce qui explique la bonne couverture de tests (chaque fichier de service a son fichier de test dédié, avec mocking systématique des I/O externes : appel HTTP Groq, sous-processus `terraform`, système de fichiers).

### 2.5 Points de vigilance connus (déjà traités ou identifiés lors de la revue)

- ✅ **Path traversal via nom de fichier IA** — corrigé dans `terraform_service.py` (vérification `os.path.commonpath`).
- ✅ **Code mort** (`terraform_generator.py`, doublon de `terraform_parser.py`, `file_manager.py` vide) — supprimé.
- ✅ **`generated/` et `.venv/` versionnés dans git** — untrackés, `generated/` ajouté au `.gitignore`.
- ✅ **Dépendances mortes** (`google-genai`, `google-auth`, `tenacity`, etc.) — retirées de `requirements.txt`.
- ⚠️ `backend/prompts/aws_prompt.py.save` : fichier orphelin toujours versionné, à supprimer.
- ⚠️ `TerraformService.save` n'efface pas les anciens fichiers d'un projet avant réécriture : régénérer un projet existant avec moins de fichiers peut laisser des fichiers obsolètes dans le zip final.
- ⚠️ CORS `allow_origins=["*"]` combiné à `allow_credentials=True` (`app.py`) — à resserrer hors environnement local.
- ⚠️ `README.md` et les dossiers `docs/`, `templates/` sont vides.

---

## 3. Code source complet

### 3.1 Racine

#### `requirements.txt`
```txt
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.14.1
certifi==2026.6.17
charset-normalizer==3.4.9
click==8.4.2
distro==1.9.0
fastapi==0.139.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.18
jiter==0.16.0
openai==2.45.0
pydantic==2.13.4
pydantic_core==2.46.4
pytest==9.1.1
pytest-mock==3.15.1
python-dotenv==1.2.2
python-multipart==0.0.32
sniffio==1.3.1
starlette==1.3.1
tqdm==4.68.4
typing-inspection==0.4.2
typing_extensions==4.16.0
urllib3==2.7.0
uvicorn==0.51.0
websockets==16.1
```

#### `pytest.ini`
```ini
[pytest]
testpaths = tests
addopts = -q
markers =
    integration: hits the real Groq API and/or the real terraform CLI (slow, network required)
```

#### `.gitignore`
```gitignore
.env
.venv/

# Python
__pycache__/
*.pyc
.pytest_cache/

# Terraform artifacts (generated per landing zone, and the shared plugin cache)
.terraform/
.terraform.lock.hcl
*.tfstate
*.tfstate.*
.terraform-plugin-cache/

# Generated landing zone projects (runtime output of /generate)
generated/
```

---

### 3.2 `backend/app.py`
```python
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
```

### 3.3 `backend/config.py`
```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:

    PROJECT_NAME = "AI Terraform Landing Zone Generator"

    VERSION = "1.0.0"

    GENERATED_FOLDER = "generated"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    MODEL = "openai/gpt-oss-120b"

    TERRAFORM_PLUGIN_CACHE_DIR = str(BASE_DIR / ".terraform-plugin-cache")


settings = Settings()
```

---

### 3.4 `backend/exceptions/api_exception.py`
```python
class ApiException(Exception):

    def __init__(self, message: str, status_code: int = 400):

        self.message = message

        self.status_code = status_code

        super().__init__(message)
```

### 3.5 `backend/exceptions/exception_handler.py`
```python
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.exceptions.api_exception import ApiException


def register_exception_handlers(app: FastAPI):

    @app.exception_handler(ApiException)
    async def api_exception_handler(
        request: Request,
        exc: ApiException
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": exc.message
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "message": "Invalid request parameters.",
                "details": jsonable_encoder(exc.errors())
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception
    ):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal Server Error",
                "details": str(exc)
            }
        )
```

---

### 3.6 `backend/parser/terraform_parser.py`
```python
from backend.exceptions.api_exception import ApiException


class TerraformParser:

    REQUIRED_FILES = {
        "provider.tf",
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraform.tfvars",
        "README.md",
    }

    def parse(self, response: str):

        if not response or not response.strip():
            raise ApiException(
                message="The AI returned an empty response.",
                status_code=502
            )

        files = {}

        current_file = None
        current_content = []

        for line in response.splitlines():

            line = line.strip()

            # Detect file header
            if line.startswith("### "):

                # Save previous file
                if current_file:
                    self._save_file(
                        files,
                        current_file,
                        current_content
                    )

                current_file = line.replace("### ", "", 1).strip()
                current_content = []

            else:

                current_content.append(line)

        # Save last file
        if current_file:
            self._save_file(
                files,
                current_file,
                current_content
            )

        # No file marker ("### filename") found at all -> unrecognized format
        if not files:
            raise ApiException(
                message=(
                    "The AI response format is invalid: no file markers "
                    "(expected '### filename.tf' sections) were found."
                ),
                status_code=502
            )

        # Check required files
        missing_files = self.REQUIRED_FILES - set(files.keys())

        if missing_files:

            raise ApiException(
                message=(
                    "The AI response is missing required files: "
                    + ", ".join(sorted(missing_files))
                ),
                status_code=502
            )

        return files

    def _save_file(self, files, filename, content):

        if not filename:
            raise ApiException(
                message="Invalid filename detected in AI response.",
                status_code=502
            )

        content_text = "\n".join(content).strip()

        if not content_text:
            raise ApiException(
                message=f"File '{filename}' is empty.",
                status_code=502
            )

        files[filename] = self._clean_content(
            filename,
            content_text
        )

    def _clean_content(self, filename, content):

        if filename == "README.md":

            if content.startswith("BEGIN_TEXT"):
                content = content[len("BEGIN_TEXT"):].strip()

            if content.endswith("END_TEXT"):
                content = content[:-len("END_TEXT")].strip()

        else:

            if content.startswith("BEGIN_TERRAFORM"):
                content = content[len("BEGIN_TERRAFORM"):].strip()

            if content.endswith("END_TERRAFORM"):
                content = content[:-len("END_TERRAFORM")].strip()

        return content
```

---

### 3.7 `backend/prompts/landing_zone.py`
```python
def build_landing_zone_prompt(request):

    return f"""
You are a Senior Cloud Architect, DevSecOps Engineer and Terraform Expert.

Your mission is to generate a COMPLETE, VALID and PRODUCTION-READY AWS Landing Zone using Terraform.

=========================
PROJECT INFORMATION
=========================

Cloud Provider: {{request.cloud}}
Project Name: {{request.project_name}}
Region: {{request.region}}
Template: {{request.template}}

Availability Zones: {{request.availability_zones}}

Public Subnets: {{request.public_subnets}}

Private Subnets: {{request.private_subnets}}

Enable NAT Gateway: {{request.enable_nat_gateway}}

Enable CloudTrail: {{request.enable_cloudtrail}}

Enable CloudWatch: {{request.enable_cloudwatch}}

Enable S3 Logs: {{request.enable_s3_logs}}

=========================
LANDING ZONE REQUIREMENTS
=========================

Generate a production-ready AWS Landing Zone.

Respect ALL user parameters exactly.

The infrastructure must include:

- AWS Provider configuration
- VPC
- Public Subnets
- Private Subnets
- Internet Gateway
- Route Tables
- Route Table Associations
- Security Groups
- Variables
- Outputs
- terraform.tfvars
- README.md

Infrastructure requirements:

- Create exactly the requested number of Availability Zones.
- Create exactly the requested number of Public Subnets.
- Create exactly the requested number of Private Subnets.
- If Enable NAT Gateway is false, DO NOT generate any NAT Gateway.
- If Enable CloudTrail is false, DO NOT generate CloudTrail resources.
- If Enable CloudWatch is false, DO NOT generate CloudWatch resources.
- If Enable S3 Logs is false, DO NOT generate any S3 bucket dedicated to logging.

=========================
TERRAFORM BEST PRACTICES
=========================

- Generate valid Terraform code.
- Use the latest stable syntax supported by the current AWS Terraform provider.
- Use variables whenever possible.
- Do not hardcode configurable values.
- Follow Terraform naming conventions.
- Generate readable and modular code.
- Avoid deprecated Terraform resources and arguments.
- Do not use deprecated AWS provider arguments.

AWS PROVIDER COMPATIBILITY RULES:

- For aws_eip resources, use:
  domain = "vpc"
  Do NOT use:
  vpc = true

- For S3 buckets, do NOT use the acl argument inside aws_s3_bucket.
- If an S3 bucket requires an ACL, use the dedicated aws_s3_bucket_acl resource.
- For S3 bucket ownership, use aws_s3_bucket_ownership_controls when required.
- For S3 versioning, prefer aws_s3_bucket_versioning.
- For S3 server-side encryption, prefer aws_s3_bucket_server_side_encryption_configuration.
- Do not use deprecated inline S3 bucket configuration blocks when a dedicated resource exists.

All generated resources must be compatible with the current stable AWS Terraform provider.

The generated project must be able to pass:

terraform fmt
terraform init
terraform validate

=========================
OUTPUT FORMAT
=========================

### provider.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### main.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### variables.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### outputs.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### terraform.tfvars
BEGIN_TERRAFORM
...
END_TERRAFORM

### README.md
BEGIN_TEXT
...
END_TEXT

=========================
RULES
=========================

- Return ONLY the requested files.
- Do NOT explain anything.
- Do NOT add introductions.
- Do NOT add conclusions.
- Do NOT generate files that are not requested.
- Respect the output format exactly.
- If a component is disabled, do not generate it.
- Do not invent AWS resources.
- Keep the output deterministic and consistent.

The generated project must successfully execute:

terraform init

terraform fmt

terraform validate

terraform plan
"""
```
> Note : les `{{request.xxx}}` ci-dessus sont des f-string Python (`{request.xxx}`) échappées pour l'affichage dans ce document Markdown — dans le fichier réel ce sont de vraies interpolations Python.

---

### 3.8 `backend/routes/generate.py`
```python
from fastapi import APIRouter

from backend.schemas.generate_request import GenerateRequest
from backend.services.prompt_service import PromptService
from backend.services.ai.terraform_ai_service import TerraformAIService
from backend.parser.terraform_parser import TerraformParser
from backend.services.terraform_service import TerraformService
from backend.services.terraform_validator_service import TerraformValidatorService
from backend.utils.zip_manager import create_zip

router = APIRouter(tags=["Terraform"])

prompt_service = PromptService()
ai_service = TerraformAIService()
parser = TerraformParser()
terraform_service = TerraformService()
validator = TerraformValidatorService()


@router.post("/generate")
def generate(request: GenerateRequest):

    prompt = prompt_service.build_prompt(request)

    ai_response = ai_service.generate(prompt)

    files = parser.parse(ai_response)

    project_path = terraform_service.save(
        request.project_name,
        files
    )

    validation = validator.validate(project_path)

    zip_path = create_zip(project_path)

    return {
        "status": "success",
        "project": request.project_name,
        "generated_files": list(files.keys()),
        "validation": validation,
        "download": zip_path
    }
```

---

### 3.9 `backend/schemas/generate_request.py`
```python
import re

from pydantic import BaseModel, field_validator

PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


class GenerateRequest(BaseModel):

    cloud: str

    project_name: str

    region: str

    template: str = "landing-zone"

    availability_zones: int = 2

    public_subnets: int = 2

    private_subnets: int = 2

    enable_nat_gateway: bool = True

    enable_cloudtrail: bool = True

    enable_cloudwatch: bool = True

    enable_s3_logs: bool = True

    @field_validator("project_name")
    @classmethod
    def validate_project_name(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("project_name must not be empty.")

        if not PROJECT_NAME_PATTERN.match(value):
            raise ValueError(
                "project_name must start with a letter or digit and contain only "
                "letters, digits, hyphens and underscores (max 63 characters)."
            )

        return value
```

---

### 3.10 `backend/services/prompt_service.py`
```python
from backend.prompts.landing_zone import build_landing_zone_prompt
from backend.exceptions.api_exception import ApiException

class PromptService:

    def build_prompt(self, request):

        if request.template == "landing-zone":
            return build_landing_zone_prompt(request)

        raise ApiException(
              message=f"Unknown template: {request.template}",
              status_code=400
        )
```

### 3.11 `backend/services/terraform_service.py`
```python
import os
from backend.exceptions.api_exception import ApiException

class TerraformService:
    def save(self, project_name, files):

     project_path = f"generated/{project_name}"
     project_dir_abs = os.path.abspath(project_path)

     try:

        os.makedirs(project_path, exist_ok=True)

        for filename, content in files.items():

            file_path = os.path.abspath(os.path.join(project_path, filename))

            if os.path.commonpath([project_dir_abs, file_path]) != project_dir_abs:
                raise ApiException(
                    message=f"Invalid file path in AI response: '{filename}'.",
                    status_code=502
                )

            with open(file_path, "w") as f:

                f.write(content)

        return project_path

     except ApiException:

        raise

     except Exception:

        raise ApiException(
            message="Unable to save Terraform project.",
            status_code=500
        )
```

### 3.12 `backend/services/terraform_validator_service.py`
```python
import os
import subprocess

from backend.config import settings
from backend.exceptions.api_exception import ApiException


class TerraformValidatorService:

    TIMEOUT_SECONDS = 60

    def __init__(self):
        os.makedirs(settings.TERRAFORM_PLUGIN_CACHE_DIR, exist_ok=True)

    def validate(self, project_path):

        init_result = self._run(["terraform", "init", "-input=false"], project_path)

        if init_result.returncode != 0:
            return {
                "valid": False,
                "step": "init",
                "stdout": init_result.stdout,
                "stderr": init_result.stderr
            }

        validate_result = self._run(["terraform", "validate"], project_path)

        return {
            "valid": validate_result.returncode == 0,
            "step": "validate",
            "stdout": validate_result.stdout,
            "stderr": validate_result.stderr
        }

    def _run(self, command, project_path):

        env = {
            **os.environ,
            "TF_PLUGIN_CACHE_DIR": settings.TERRAFORM_PLUGIN_CACHE_DIR
        }

        try:
            return subprocess.run(
                command,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SECONDS,
                env=env
            )

        except FileNotFoundError:
            raise ApiException(
                message="Terraform CLI is not installed or not found on the server.",
                status_code=500
            )

        except subprocess.TimeoutExpired:
            raise ApiException(
                message=(
                    f"Terraform command '{' '.join(command)}' timed out "
                    f"after {self.TIMEOUT_SECONDS}s."
                ),
                status_code=504
            )

        except OSError as e:
            raise ApiException(
                message=f"Unable to run Terraform: {e}",
                status_code=500
            )
```

### 3.13 `backend/services/ai/terraform_ai_service.py`
```python
from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    AuthenticationError,
    APIStatusError,
)

from backend.config import settings
from backend.exceptions.api_exception import ApiException

class TerraformAIService:

    def __init__(self):

        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate(self, prompt: str):
        try:
            response = self.client.chat.completions.create(
                model=settings.MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=6000,
                extra_body={"reasoning_effort": "low"}
            )

        except APITimeoutError:
            raise ApiException(
                message="The AI service (Groq) did not respond in time. Please try again.",
                status_code=504
            )

        except RateLimitError:
            raise ApiException(
                message="The AI service (Groq) rate limit was reached. Please try again later.",
                status_code=429
            )

        except AuthenticationError:
            raise ApiException(
                message="Unable to authenticate with the AI service (Groq). Check the API key configuration.",
                status_code=500
            )

        except APIConnectionError:
            raise ApiException(
                message="Unable to reach the AI service (Groq). Please check your connection and try again.",
                status_code=502
            )

        except APIStatusError as e:
            raise ApiException(
                message=f"The AI service (Groq) returned an error: {e.message}",
                status_code=502
            )

        except Exception:
            raise ApiException(
                message="Unexpected error while generating the Terraform project using AI.",
                status_code=500
            )

        if not response.choices:
            raise ApiException(
                message="The AI service (Groq) returned no completion choices.",
                status_code=502
            )

        choice = response.choices[0]

        if choice.finish_reason == "length":
            raise ApiException(
                message=(
                    "The AI service (Groq) response was truncated because it hit "
                    "the token limit. Try a smaller project or simplify the request."
                ),
                status_code=502
            )

        content = choice.message.content

        if not content or not content.strip():
            raise ApiException(
                message="The AI service (Groq) returned an empty response.",
                status_code=502
            )

        return content
```

### 3.14 `backend/utils/zip_manager.py`
```python
import os
import zipfile

EXCLUDED_DIRS = {".terraform"}
EXCLUDED_FILES = {".terraform.lock.hcl"}


def create_zip(project_path):

    zip_path = f"{project_path}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:

        for root, dirs, files in os.walk(project_path):

            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for filename in files:

                if filename in EXCLUDED_FILES:
                    continue

                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, project_path)

                zip_file.write(file_path, arcname)

    return zip_path
```

---

### 3.15 Tests

#### `tests/conftest.py`
```python
import httpx
import pytest


def _fake_response(status_code=500):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})


@pytest.fixture
def fake_openai_request():
    return httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


@pytest.fixture
def fake_openai_response():
    return _fake_response


@pytest.fixture
def valid_ai_response():
    return """### provider.tf
BEGIN_TERRAFORM
provider "aws" {
  region = "eu-west-1"
}
END_TERRAFORM

### main.tf
BEGIN_TERRAFORM
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
END_TERRAFORM

### variables.tf
BEGIN_TERRAFORM
variable "region" {
  type = string
}
END_TERRAFORM

### outputs.tf
BEGIN_TERRAFORM
output "vpc_id" {
  value = aws_vpc.main.id
}
END_TERRAFORM

### terraform.tfvars
BEGIN_TERRAFORM
region = "eu-west-1"
END_TERRAFORM

### README.md
BEGIN_TEXT
# Landing Zone

Generated project.
END_TEXT
"""


@pytest.fixture
def valid_generate_payload():
    return {
        "cloud": "aws",
        "project_name": "test-project",
        "region": "eu-west-1",
        "template": "landing-zone",
        "availability_zones": 2,
        "public_subnets": 2,
        "private_subnets": 2,
        "enable_nat_gateway": True,
        "enable_cloudtrail": True,
        "enable_cloudwatch": True,
        "enable_s3_logs": True
    }
```

#### `tests/test_generate_route.py`
```python
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.exceptions.api_exception import ApiException
from backend.routes import generate as generate_module

client = TestClient(app)
# Needed to observe the formatted 500 response instead of TestClient re-raising
# the original exception (its default behavior for unhandled server errors).
client_no_raise = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def stub_pipeline(monkeypatch):
    monkeypatch.setattr(
        generate_module.prompt_service, "build_prompt", lambda request: "a prompt"
    )
    monkeypatch.setattr(
        generate_module.ai_service, "generate", lambda prompt: "raw ai response"
    )
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {"main.tf": "resource \"aws_vpc\" \"main\" {}"}
    )
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda project_name, files: f"generated/{project_name}"
    )
    monkeypatch.setattr(
        generate_module.validator,
        "validate",
        lambda project_path: {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    )
    monkeypatch.setattr(
        generate_module, "create_zip", lambda project_path: f"{project_path}.zip"
    )


def test_generate_success(valid_generate_payload):
    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["project"] == valid_generate_payload["project_name"]
    assert body["generated_files"] == ["main.tf"]
    assert body["validation"]["valid"] is True
    assert body["download"] == f"generated/{valid_generate_payload['project_name']}.zip"


def test_generate_reports_terraform_validation_failure(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(
        generate_module.validator,
        "validate",
        lambda project_path: {
            "valid": False, "step": "validate", "stdout": "", "stderr": "invalid HCL"
        }
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    assert response.json()["validation"]["valid"] is False


def test_generate_propagates_ai_service_failure(monkeypatch, valid_generate_payload):
    def raise_ai_error(prompt):
        raise ApiException(message="Groq is down", status_code=502)

    monkeypatch.setattr(generate_module.ai_service, "generate", raise_ai_error)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 502
    assert response.json() == {"status": "error", "message": "Groq is down"}


def test_generate_propagates_parser_failure(monkeypatch, valid_generate_payload):
    def raise_parser_error(response):
        raise ApiException(message="bad AI format", status_code=502)

    monkeypatch.setattr(generate_module.parser, "parse", raise_parser_error)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 502
    assert response.json()["message"] == "bad AI format"


def test_generate_unexpected_error_returns_500(monkeypatch, valid_generate_payload):
    def raise_unexpected(request):
        raise RuntimeError("something broke")

    monkeypatch.setattr(generate_module.prompt_service, "build_prompt", raise_unexpected)

    response = client_no_raise.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 500
    assert response.json()["status"] == "error"


def test_generate_rejects_invalid_project_name(valid_generate_payload):
    valid_generate_payload["project_name"] = "../evil"

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 422
```

#### `tests/test_parser.py`
```python
import pytest

from backend.exceptions.api_exception import ApiException
from backend.parser.terraform_parser import TerraformParser


@pytest.fixture
def parser():
    return TerraformParser()


def test_parse_valid_response(parser, valid_ai_response):
    files = parser.parse(valid_ai_response)

    assert set(files.keys()) == TerraformParser.REQUIRED_FILES
    assert 'resource "aws_vpc" "main"' in files["main.tf"]
    assert "BEGIN_TERRAFORM" not in files["main.tf"]
    assert "END_TERRAFORM" not in files["main.tf"]


def test_parse_empty_response_raises(parser):
    with pytest.raises(ApiException) as exc_info:
        parser.parse("")

    assert exc_info.value.status_code == 502
    assert "empty" in exc_info.value.message.lower()


def test_parse_whitespace_only_response_raises(parser):
    with pytest.raises(ApiException):
        parser.parse("   \n   ")


def test_parse_unrecognized_format_raises(parser):
    response = "BEGIN_TERRAFORM\nresource \"aws_vpc\" \"main\" {}\nEND_TERRAFORM"

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert exc_info.value.status_code == 502
    assert "no file markers" in exc_info.value.message.lower()


def test_parse_missing_required_files_raises(parser):
    response = (
        "### provider.tf\n"
        "provider \"aws\" {}\n"
        "### main.tf\n"
        "resource \"aws_vpc\" \"main\" {}\n"
    )

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert exc_info.value.status_code == 502
    assert "missing required files" in exc_info.value.message.lower()
    for missing in ("outputs.tf", "variables.tf", "terraform.tfvars", "README.md"):
        assert missing in exc_info.value.message


def test_parse_file_with_empty_content_raises(parser):
    response = (
        "### provider.tf\n"
        "\n"
        "### main.tf\n"
        "resource \"aws_vpc\" \"main\" {}\n"
        "### variables.tf\nx\n"
        "### outputs.tf\nx\n"
        "### terraform.tfvars\nx\n"
        "### README.md\nx\n"
    )

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert "provider.tf" in exc_info.value.message
    assert "empty" in exc_info.value.message.lower()


def test_readme_begin_end_text_markers_are_stripped(parser, valid_ai_response):
    files = parser.parse(valid_ai_response)
    assert "BEGIN_TEXT" not in files["README.md"]
    assert "END_TEXT" not in files["README.md"]
```

#### `tests/test_schemas.py`
```python
import pytest
from pydantic import ValidationError

from backend.schemas.generate_request import GenerateRequest


VALID_NAMES = ["my-project", "project_1", "a", "A1", "x" * 63]

INVALID_NAMES = [
    "",
    "   ",
    "../evil",
    "/etc/passwd",
    "..",
    ".",
    ".hidden",
    "name with spaces",
    "name/with/slash",
    "x" * 64,
    "name;rm -rf /",
]


@pytest.mark.parametrize("name", VALID_NAMES)
def test_project_name_accepts_valid_values(name):
    request = GenerateRequest(cloud="aws", project_name=name, region="eu-west-1")
    assert request.project_name == name


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_project_name_rejects_invalid_values(name):
    with pytest.raises(ValidationError):
        GenerateRequest(cloud="aws", project_name=name, region="eu-west-1")


def test_project_name_is_stripped():
    request = GenerateRequest(cloud="aws", project_name="  my-project  ", region="eu-west-1")
    assert request.project_name == "my-project"


def test_defaults_are_applied():
    request = GenerateRequest(cloud="aws", project_name="my-project", region="eu-west-1")
    assert request.template == "landing-zone"
    assert request.availability_zones == 2
    assert request.enable_nat_gateway is True
```

#### `tests/test_terraform_ai_service.py`
```python
from types import SimpleNamespace

import openai
import pytest

from backend.exceptions.api_exception import ApiException
from backend.services.ai.terraform_ai_service import TerraformAIService


@pytest.fixture
def service():
    return TerraformAIService()


def _completion(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def test_generate_success(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("### provider.tf\n...")
    )

    result = service.generate("prompt")

    assert result == "### provider.tf\n..."


def test_generate_passes_expected_params(monkeypatch, service):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion("ok")

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)

    service.generate("my prompt")

    assert captured["messages"] == [{"role": "user", "content": "my prompt"}]
    assert captured["max_tokens"] > 0
    assert captured["extra_body"] == {"reasoning_effort": "low"}


def test_generate_empty_content_raises(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("   ")
    )

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502
    assert "empty" in exc_info.value.message.lower()


def test_generate_no_choices_raises(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: SimpleNamespace(choices=[])
    )

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502


def test_generate_truncated_response_raises(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("### provider.tf\npartial...", finish_reason="length")
    )

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502
    assert "truncated" in exc_info.value.message.lower()


def test_generate_timeout_maps_to_504(monkeypatch, service, fake_openai_request):
    def raise_timeout(**kwargs):
        raise openai.APITimeoutError(request=fake_openai_request)

    monkeypatch.setattr(service.client.chat.completions, "create", raise_timeout)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 504


def test_generate_connection_error_maps_to_502(monkeypatch, service, fake_openai_request):
    def raise_connection_error(**kwargs):
        raise openai.APIConnectionError(request=fake_openai_request)

    monkeypatch.setattr(service.client.chat.completions, "create", raise_connection_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502


def test_generate_rate_limit_maps_to_429(monkeypatch, service, fake_openai_response):
    def raise_rate_limit(**kwargs):
        raise openai.RateLimitError(
            "rate limited",
            response=fake_openai_response(429),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_rate_limit)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 429


def test_generate_authentication_error_maps_to_500(monkeypatch, service, fake_openai_response):
    def raise_auth_error(**kwargs):
        raise openai.AuthenticationError(
            "bad key",
            response=fake_openai_response(401),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_auth_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 500


def test_generate_generic_status_error_maps_to_502(monkeypatch, service, fake_openai_response):
    def raise_status_error(**kwargs):
        raise openai.APIStatusError(
            "model not found",
            response=fake_openai_response(404),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_status_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502
    assert "model not found" in exc_info.value.message
```

#### `tests/test_terraform_validator_service.py`
```python
import subprocess
from types import SimpleNamespace

import pytest

from backend.exceptions.api_exception import ApiException
from backend.services import terraform_validator_service as validator_module
from backend.services.terraform_validator_service import TerraformValidatorService


@pytest.fixture(autouse=True)
def isolated_plugin_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        validator_module.settings,
        "TERRAFORM_PLUGIN_CACHE_DIR",
        str(tmp_path / "plugin-cache")
    )


def _completed(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_validate_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(0, stdout="ok")

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result == {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    assert calls == [
        ["terraform", "init", "-input=false"],
        ["terraform", "validate"]
    ]


def test_validate_stops_after_init_failure(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(1, stderr="init exploded")

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "init"
    assert result["stderr"] == "init exploded"
    assert len(calls) == 1


def test_validate_reports_validate_failure(monkeypatch, tmp_path):
    responses = [_completed(0), _completed(1, stderr="invalid HCL")]

    def fake_run(command, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "validate"
    assert result["stderr"] == "invalid HCL"


def test_missing_terraform_binary_raises_api_exception(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 500
    assert "not installed" in exc_info.value.message.lower()


def test_timeout_raises_api_exception(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=60)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.message.lower()


def test_plugin_cache_dir_is_passed_in_env(monkeypatch, tmp_path):
    captured_env = {}

    def fake_run(command, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        return _completed(0)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    TerraformValidatorService().validate(str(tmp_path))

    assert captured_env["TF_PLUGIN_CACHE_DIR"] == validator_module.settings.TERRAFORM_PLUGIN_CACHE_DIR
```

#### `tests/test_zip_manager.py`
```python
import zipfile

from backend.utils.zip_manager import create_zip


def test_create_zip_includes_project_files(tmp_path):
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    (project_dir / "main.tf").write_text("resource \"aws_vpc\" \"main\" {}")
    (project_dir / "README.md").write_text("# hello")

    zip_path = create_zip(str(project_dir))

    assert zip_path == f"{project_dir}.zip"

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    assert names == {"main.tf", "README.md"}


def test_create_zip_excludes_terraform_artifacts(tmp_path):
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    (project_dir / "main.tf").write_text("resource \"aws_vpc\" \"main\" {}")
    (project_dir / ".terraform.lock.hcl").write_text("lock contents")

    tf_dir = project_dir / ".terraform" / "providers" / "hashicorp" / "aws"
    tf_dir.mkdir(parents=True)
    (tf_dir / "terraform-provider-aws").write_bytes(b"\x00" * 1024)

    zip_path = create_zip(str(project_dir))

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    assert names == ["main.tf"]
    assert not any(".terraform" in name for name in names)
```

#### `tests/test_exception_handlers.py`
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.exceptions.api_exception import ApiException
from backend.exceptions.exception_handler import register_exception_handlers


def build_test_app():
    app = FastAPI()
    register_exception_handlers(app)

    class Payload(BaseModel):
        name: str

    @app.get("/boom-api-exception")
    def boom_api_exception():
        raise ApiException(message="custom failure", status_code=418)

    @app.get("/boom-generic")
    def boom_generic():
        raise RuntimeError("unexpected failure")

    @app.post("/validated")
    def validated(payload: Payload):
        return {"name": payload.name}

    return app


client = TestClient(build_test_app(), raise_server_exceptions=False)


def test_api_exception_is_formatted():
    response = client.get("/boom-api-exception")

    assert response.status_code == 418
    assert response.json() == {"status": "error", "message": "custom failure"}


def test_generic_exception_is_formatted():
    response = client.get("/boom-generic")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Internal Server Error"
    assert "unexpected failure" in body["details"]


def test_validation_error_is_formatted():
    response = client.post("/validated", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Invalid request parameters."
    assert isinstance(body["details"], list)
    assert body["details"][0]["loc"] == ["body", "name"]
```
