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
      ├─ pin_provider_versions . impose les versions de providers en cache
      ├─ TerraformService ...... écrit le projet sur disque
      ├─ TerraformValidator .... terraform fmt → init → validate
      │      │
      │      └─ invalide ? ──► prompt de réparation (erreur + fichiers)
      │                        ──► re-parse ──► re-valide   (max 2 tours)
      └─ create_zip ............ archive → disque local ou S3 (URL présignée)
```

Chaque génération reçoit un `generation_id` (UUID) : elle travaille dans
`generated/<generation_id>/<project_name>/`, et c'est cet identifiant — pas le nom du
projet — qui sert au téléchargement.

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

cp .env.example .env   # puis renseigner GROQ_API_KEY
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

### Avec Docker

```bash
docker compose up --build
```

Frontend sur http://localhost:5173 : nginx sert le statique et relaie `/api` vers le
backend. Le Terraform CLI est embarqué dans l'image backend ; le cache de providers et
les générations vivent dans des volumes nommés.

## Tests

```bash
pytest          # 157 tests, sans réseau, Terraform ni AWS (tout est simulé)
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
  "generation_id": "3f2c9a0e6b1d4c8e9f7a5b2d1c0e8f6a",
  "download": "/api/download/3f2c9a0e6b1d4c8e9f7a5b2d1c0e8f6a"
}
```

`download` est un chemin de l'API en local, ou une **URL S3 présignée** (valable 1 h) quand
`S3_BUCKET` est défini. Il vaut `null` si l'archivage a échoué.

Un projet qui reste invalide après réparation renvoie quand même `200` avec
`validation.valid = false` : le projet est livré, à l'utilisateur de décider.

**La requête est longue par choix** : jusqu'à trois appels au modèle et trois cycles
`init`/`validate`, soit plusieurs minutes. Aucun client ne doit lui appliquer un timeout
court. Tout ce qui a pu être produit est livré, et ce qui a mal tourné est signalé dans
`warnings` plutôt que d'échouer la requête — y compris une réponse du modèle tronquée au
plafond de tokens, que rien ne rendait visible auparavant.

### `GET /api/download/{generation_id}`

Renvoie l'archive `<project_name>.zip` (sans `.terraform/` ni fichier de lock). Mode local
uniquement : en mode S3, le lien présigné pointe directement sur le bucket.

### Erreurs

Format uniforme `{"status": "error", "message": "..."}`.

| Code | Cas |
|------|-----|
| 422  | Paramètres invalides (`cloud` ≠ `aws`, région mal formée, nom de projet…) |
| 401  | Authentification basique requise (nginx, si activée) |
| 404  | Génération inexistante ou purgée |
| 429  | Quota Groq atteint, trop de générations simultanées, ou limite de débit nginx |
| 502  | Groq injoignable, ou réponse inexploitable |
| 504  | Groq ou Terraform en timeout |

---

## Configuration

| Variable | Défaut | Rôle |
|----------|--------|------|
| `GROQ_API_KEY` | — | **requis** |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | origines autorisées (séparées par des virgules) |
| `LOG_LEVEL` | `INFO` | niveau de log |
| `S3_BUCKET` | — | bucket des archives ; vide = disque local |
| `S3_PREFIX` | `generated` | préfixe des clés S3 |
| `AWS_REGION` | — | région du bucket |
| `MAX_CONCURRENT_GENERATIONS` | `2` | générations simultanées avant de répondre 429 |
| `GENERATION_TTL_SECONDS` | `86400` | durée de vie des générations sur le disque local |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` | — | conteneur **frontend** : active l'authentification basique nginx |

Le modèle complet est dans [`.env.example`](.env.example).

Réglages dans `backend/config.py` : modèle, timeout IA (180 s, 2 retries), répertoire de
sortie, cache de providers Terraform.

**Versions de providers** (`AWS_PROVIDER_VERSION`, `RANDOM_PROVIDER_VERSION`) : les prompts
demandent ces versions exactes, jamais une plage `~>`, et `pin_provider_versions` les
réécrit de toute façon après chaque parse — le modèle ne peut plus y déroger. Une plage laissait le
registry résoudre vers une version absente du cache local, et le téléchargement épuisait le
budget d'`init` sur un projet pourtant valide. Toute modification de ces valeurs doit être
suivie d'un `terraform init` pour réamorcer le cache.

Budgets de temps dans `TerraformValidatorService` : `init` **420 s**, autres commandes
**120 s**. Ces budgets sont volontairement larges : `init` est mesuré à ~57 s avec un cache
chaud, mais doit aussi couvrir un cache froid où le provider épinglé pèse 675 Mo. Le parti
pris du projet est d'aboutir lentement plutôt que d'abandonner une génération valide.

---

## Déploiement

Chaque push sur `main` déclenche [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) :
tests → build des deux images → push sur ECR → `docker compose up` sur l'EC2 via SSM →
vérification de `/health`.

L'infrastructure d'hébergement est créée **manuellement** dans la console AWS. Il faut :

| Ressource | Détail |
|-----------|--------|
| **2 dépôts ECR** | backend et frontend |
| **Bucket S3** | archives (`generated/`) et compose de prod (`deploy/`). Bloquer l'accès public ; ajouter une règle de cycle de vie qui expire `generated/` (ex. 7 jours) |
| **Fournisseur OIDC** | `token.actions.githubusercontent.com`, audience `sts.amazonaws.com` |
| **Rôle IAM de déploiement** | confiance limitée à `repo:<owner>/<repo>:ref:refs/heads/main` ; droits : push ECR, `s3:PutObject` sur `deploy/*`, `ssm:SendCommand` sur l'instance, `ssm:GetCommandInvocation` |
| **Instance EC2** | Amazon Linux 2023, t3.medium ou plus conseillé (`terraform init` est gourmand, à ajuster à l’usage), ≥ 20 Go de disque (cache de providers ≈ 700 Mo), Docker + plugin compose, agent SSM |
| **Profil IAM de l'instance** | `AmazonSSMManagedInstanceCore`, pull ECR, `s3:GetObject` sur `deploy/*`, `s3:PutObject` + `s3:GetObject` sur `generated/*` |
| **Security group** | entrée 80 uniquement (pas de 22 : SSM remplace SSH) |
| **`/opt/ai-tf-landing-zone/.env`** | sur l'instance, d'après [`.env.example`](.env.example) — avec `BASIC_AUTH_*` |

Côté GitHub : secret `AWS_DEPLOY_ROLE_ARN`, variables `AWS_REGION`,
`ECR_REPOSITORY_BACKEND`, `ECR_REPOSITORY_FRONTEND`, `S3_BUCKET`, `EC2_INSTANCE_ID`,
`APP_HOST`.

### Protections en place

- **Authentification basique** nginx sur tout le site sauf `/health` (`BASIC_AUTH_*`).
- **Limite de débit** nginx : 1 génération/min par IP (marge de 2), une seule à la fois par
  IP ; 30 requêtes/min sur le reste de l'API.
- **Plafond global** côté backend (`MAX_CONCURRENT_GENERATIONS`) : 429 immédiat au-delà.
- **Purge** des générations locales passé `GENERATION_TTL_SECONDS` ; en mode S3, la copie
  locale est supprimée dès l'upload.

## Limites connues

Ce projet est une **démo fonctionnelle**, pas un service de production.

- **Pas de HTTPS.** L'authentification basique circule en clair sur le port 80 : ajouter un
  certificat (ALB + ACM, ou Caddy/certbot sur l'instance) avant d'y mettre un vrai mot de
  passe.
- **Requête synchrone de plusieurs minutes.** nginx l'autorise (900 s), mais un ALB placé
  devant la coupera à 60 s par défaut : relever son `idle timeout`, ou passer à une
  génération asynchrone (job + polling).
- **La limite de débit est par IP**, et derrière un load balancer elle verrait l'IP du LB
  (voir le commentaire en tête de `frontend/nginx.conf`).
- **`terraform validate` prouve que le code est valide, pas qu'il respecte les paramètres
  demandés.** Vérifier le nombre de subnets ou la présence de la NAT demanderait des
  assertions sur le `plan`.
- Seuls `cloud=aws` et `template=landing-zone` sont implémentés (les autres valeurs sont
  refusées en 422).

## Pistes

- HTTPS
- Génération asynchrone avec suivi de progression
- Sortie structurée (JSON schema) côté modèle : supprimerait entièrement le parser maison
- Assertions sur `terraform plan` pour valider le respect des paramètres

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
  utils/                 zip · stockage S3 · purge · pin des providers
frontend/                Vue 3 via CDN, sans build ; nginx.conf + auth optionnelle
tests/                   157 tests
.github/workflows/       CI/CD vers EC2
```
