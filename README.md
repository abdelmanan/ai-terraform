# AI Terraform Landing Zone Generator

Génère une **AWS Landing Zone Terraform** (VPC, subnets, routing, NAT, logs) à partir d'un
formulaire, via un LLM — puis **valide et répare automatiquement** le code produit avant de
le livrer.

Le point clé : un LLM ne garantit pas du Terraform valide, même avec des règles explicites
dans le prompt. Le projet ne se contente donc pas de générer — il exécute `terraform
validate`, et **renvoie l'erreur au modèle pour qu'il se corrige** jusqu'à 2 fois.

---

## Fonctionnement

```
POST /api/generate
      │
      ├─ PromptService ......... construit le prompt à partir des paramètres
      ├─ TerraformAIService .... appelle Groq (openai/gpt-oss-120b)
      ├─ TerraformParser ....... découpe la réponse en fichiers .tf
      ├─ TerraformService ...... écrit le projet sur disque
      ├─ TerraformValidator .... terraform fmt → init → validate
      │      │
      │      └─ invalide ? ──► prompt de réparation (erreur + fichiers)
      │                        ──► re-parse ──► re-valide   (max 2 tours)
      └─ create_zip ............ archive téléchargeable
```

Chaque couche a une responsabilité unique et se teste isolément : le pipeline complet se
monte en test en ne simulant que `TerraformAIService.generate`.

### Le protocole de réponse

Le modèle doit répondre dans un format texte délimité, que le parser découpe :

```
### main.tf
BEGIN_TERRAFORM
resource "aws_vpc" "main" { ... }
END_TERRAFORM

### README.md
BEGIN_TEXT
...
END_TEXT
```

Un `### titre` n'est traité comme un en-tête de fichier que s'il est **immédiatement suivi
d'un marqueur `BEGIN_*`** — sinon un titre Markdown dans le README généré casserait le
découpage.

---

## Installation

Prérequis : **Python 3.12+**, **Terraform CLI** (`terraform version`), une clé **Groq**.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

echo "GROQ_API_KEY=gsk_..." > .env
```

Le premier `terraform init` télécharge les providers pinnés (~700 Mo) dans
`.terraform-plugin-cache/`, qui n'est pas versionné. Les générations suivantes réutilisent
ce cache — c'est ce qui garde `init` sous son budget de temps.

## Lancement

```bash
./run.sh
```

- Backend  : http://localhost:8000 (docs interactives sur `/docs`)
- Frontend : http://localhost:5173

Ou séparément :

```bash
uvicorn backend.app:app --reload --port 8000
cd frontend && python3 -m http.server 5173
```

## Tests

```bash
pytest          # 114 tests, sans réseau ni Terraform (tout est simulé)
```

---

## API

### `POST /api/generate`

```json
{
  "cloud": "aws",
  "project_name": "my-landing-zone",
  "region": "eu-west-3",
  "template": "landing-zone",
  "availability_zones": 3,
  "public_subnets": 3,
  "private_subnets": 3,
  "enable_nat_gateway": true,
  "enable_cloudtrail": false,
  "enable_cloudwatch": true,
  "enable_s3_logs": true
}
```

`project_name` : `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$`. Les compteurs sont bornés entre 1 et 10.

Réponse `200` :

```json
{
  "status": "success",
  "project": "my-landing-zone",
  "generated_files": ["provider.tf", "main.tf", "variables.tf", "outputs.tf",
                      "terraform.tfvars", "README.md"],
  "warnings": ["Terraform validation failed on the first attempt; 1 self-repair attempt(s) fixed the project."],
  "validation": { "valid": true, "step": "validate", "stdout": "Success!", "stderr": "" },
  "repair_attempts": 1,
  "download": "/api/download/my-landing-zone"
}
```

Un projet qui reste invalide après réparation renvoie quand même `200` avec
`validation.valid = false` : le projet est livré, à l'utilisateur de décider.

### `GET /api/download/{project_name}`

Renvoie l'archive `.zip` (sans `.terraform/` ni fichier de lock).

### Erreurs

Format uniforme `{"status": "error", "message": "..."}`.

| Code | Cas |
|------|-----|
| 422  | Paramètres invalides |
| 404  | Projet inexistant |
| 429  | Quota Groq atteint |
| 502  | Groq injoignable, ou réponse inexploitable |
| 504  | Groq ou Terraform en timeout |

---

## Configuration

| Variable | Défaut | Rôle |
|----------|--------|------|
| `GROQ_API_KEY` | — | **requis** |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | origines autorisées (séparées par des virgules) |
| `LOG_LEVEL` | `INFO` | niveau de log |

Réglages dans `backend/config.py` : modèle, timeouts IA (60 s, 2 retries), répertoire de
sortie, cache de providers Terraform.

**Versions de providers** (`AWS_PROVIDER_VERSION`, `RANDOM_PROVIDER_VERSION`) : les prompts
imposent au modèle ces versions exactes, jamais une plage `~>`. Une plage laissait le
registry résoudre vers une version absente du cache local, et le téléchargement épuisait le
budget d'`init` sur un projet pourtant valide. Toute modification de ces valeurs doit être
suivie d'un `terraform init` pour réamorcer le cache.

Budgets de temps dans `TerraformValidatorService` : `init` **180 s** (mesuré à ~57 s même
avec un cache chaud), autres commandes 60 s.

---

## Limites connues

Ce projet est une **démo fonctionnelle**, pas un service de production.

- **Pas d'authentification ni de rate limiting.** `/api/generate` consomme des tokens payants
  et lance des sous-processus : ne pas exposer publiquement en l'état.
- **`project_name` est le seul identifiant.** Deux générations du même nom s'écrasent, et
  l'URL de téléchargement est devinable. Un `generation_id` serait la vraie correction.
- **État sur le disque local.** `generated/` n'est jamais purgé et empêche de scaler
  horizontalement.
- **`cloud` et `region` ne sont pas validés.** `cloud="azure"` produit quand même du
  Terraform AWS ; une région inexistante ne casse qu'au `terraform plan`.
- **`terraform validate` prouve que le code est valide, pas qu'il respecte les paramètres
  demandés.** Vérifier le nombre de subnets ou la présence de la NAT demanderait des
  assertions sur le `plan`.
- **Le pin des versions de providers n'est qu'une consigne de prompt.** Rien ne vérifie
  côté code ce que le modèle a réellement écrit dans `provider.tf` : s'il ignore la
  consigne, le téléchargement d'une version non cachée peut à nouveau faire expirer
  `init`. Une normalisation déterministe de `provider.tf` après le parse serait la vraie
  garantie.
- Seuls `cloud=aws` et `template=landing-zone` sont réellement implémentés.

## Pistes

- Sortie structurée (JSON schema) côté modèle : supprimerait entièrement le parser maison
- Assertions sur `terraform plan` pour valider le respect des paramètres
- `generation_id`, purge de `generated/`, authentification
- Dockerfile et CI

## Structure

```
backend/
  app.py                 point d'entrée FastAPI, CORS, logging
  config.py              settings (clé API, modèle, timeouts, chemins)
  routes/generate.py     orchestration du pipeline + boucle de réparation
  schemas/               validation Pydantic des entrées
  prompts/               landing_zone.py (génération) · repair.py (correction)
  services/              ai/ · prompt · terraform (disque) · terraform_validator
  parser/                découpage de la réponse du modèle
  exceptions/            ApiException + handlers centralisés
  utils/zip_manager.py
frontend/                Vue 3 via CDN, sans build
tests/                   114 tests
```
