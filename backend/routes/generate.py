import glob
import logging
import os
import shutil
import threading
import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.config import settings
from backend.exceptions.api_exception import ApiException
from backend.schemas.generate_request import PROJECT_NAME_PATTERN, GenerateRequest
from backend.services.prompt_service import PromptService
from backend.services.ai.terraform_ai_service import TerraformAIService
from backend.parser.terraform_parser import TerraformParser
from backend.services.terraform_service import TerraformService
from backend.services.terraform_validator_service import TerraformValidatorService
from backend.utils.cleanup import GENERATION_ID_PATTERN, purge_expired_generations
from backend.utils.provider_pin import pin_provider_versions
from backend.utils.storage import StorageError, is_remote, publish_archive
from backend.utils.zip_manager import create_zip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Terraform"])

MAX_REPAIR_ATTEMPTS = 2
UNFIXABLE_STEPS = ("skipped", "error")

prompt_service = PromptService()
ai_service = TerraformAIService()
parser = TerraformParser()
terraform_service = TerraformService()
validator = TerraformValidatorService()

generation_slots = threading.BoundedSemaphore(settings.MAX_CONCURRENT_GENERATIONS)

STEP_PENALTY = {
    "validate": 0,
    "init": 1_000,
    "error": 2_000,
    "skipped": 3_000,
}


def _quality_score(validation):
    """Compare two attempts: lower is better, 0 means valid.

    Ranking on the raw error count alone was wrong: a repair that broke
    `terraform init` scored better than the validate failure it started from.
    """

    if validation["valid"]:
        return 0

    penalty = STEP_PENALTY.get(validation.get("step"), STEP_PENALTY["init"])

    return penalty + max(1, (validation.get("stderr") or "").count("Error:"))


def _validate_project(project_path, missing_files):

    if {"provider.tf", "main.tf"} & set(missing_files):
        return {
            "valid": False,
            "step": "skipped",
            "stdout": "",
            "stderr": "Validation skipped: provider.tf or main.tf is missing."
        }

    try:
        return validator.validate(project_path)

    except ApiException as exc:
        logger.warning("Could not run Terraform validation: %s", exc.message)

        return {
            "valid": False,
            "step": "error",
            "stdout": "",
            "stderr": exc.message
        }


@router.post("/generate")
def generate(request: GenerateRequest):

    if not generation_slots.acquire(blocking=False):
        raise ApiException(
            message="The server is busy with other generations, please retry in a few minutes.",
            status_code=429
        )

    try:
        purge_expired_generations()
        return _generate(request)

    finally:
        generation_slots.release()


def _generate(request):

    generation_id = uuid.uuid4().hex

    logger.info(
        "Generating project '%s' [%s] (%s/%s, template=%s)",
        request.project_name, generation_id,
        request.cloud, request.region, request.template
    )

    prompt = prompt_service.build_prompt(request)

    warnings = []

    ai_response = ai_service.generate(prompt, warnings=warnings)

    files = pin_provider_versions(parser.parse(ai_response))

    missing_files = parser.missing_required_files(files)
    if missing_files:
        warnings.append(
            "The AI response was missing some expected files: "
            + ", ".join(missing_files)
        )

    project_path = terraform_service.save(
        generation_id,
        request.project_name,
        files
    )

    validation = _validate_project(project_path, missing_files)

    best_files = files
    best_validation = validation
    best_score = _quality_score(validation)

    repair_attempts = 0

    while (
        not validation["valid"]
        and validation["step"] not in UNFIXABLE_STEPS
        and repair_attempts < MAX_REPAIR_ATTEMPTS
    ):

        repair_attempts += 1

        logger.info(
            "Project '%s' failed terraform %s, self-repair attempt %d/%d",
            request.project_name, validation["step"],
            repair_attempts, MAX_REPAIR_ATTEMPTS
        )

        try:
            full_rewrite = repair_attempts == MAX_REPAIR_ATTEMPTS

            repair_prompt = prompt_service.build_repair_prompt(
                request,
                files,
                validation,
                full_rewrite=full_rewrite
            )
            repaired_files = parser.parse(
                ai_service.generate(repair_prompt, warnings=warnings)
            )

        except ApiException as exc:
            warnings.append(
                f"Self-repair attempt {repair_attempts} failed: {exc.message}"
            )
            break

        files = pin_provider_versions({**files, **repaired_files})
        missing_files = parser.missing_required_files(files)

        project_path = terraform_service.save(
            generation_id,
            request.project_name,
            files
        )

        validation = _validate_project(project_path, missing_files)

        score = _quality_score(validation)

        if score < best_score:
            best_files, best_validation, best_score = files, validation, score

    if _quality_score(validation) > best_score:

        logger.info(
            "Discarding a self-repair that made project '%s' worse "
            "(%d errors vs %d)",
            request.project_name, _quality_score(validation), best_score
        )

        warnings.append(
            "A self-repair attempt made the project worse; "
            "the best version produced was kept instead."
        )

        files = best_files
        validation = best_validation
        project_path = terraform_service.save(generation_id, request.project_name, files)

    if repair_attempts:
        warnings.append(
            "Terraform validation failed on the first attempt; "
            f"{repair_attempts} self-repair attempt(s) "
            + ("fixed the project." if validation["valid"] else "did not fix it.")
        )

    logger.info(
        "Project '%s' done: valid=%s, repairs=%d, files=%d",
        request.project_name, validation["valid"], repair_attempts, len(files)
    )

    try:
        zip_path = create_zip(project_path)
        download = publish_archive(zip_path, generation_id, request.project_name)

    except (OSError, StorageError) as exc:
        logger.error("Could not archive project '%s': %s", request.project_name, exc)
        warnings.append(f"The project could not be archived for download: {exc}")
        download = None

    else:
        if is_remote():
            shutil.rmtree(
                os.path.join(settings.GENERATED_DIR, generation_id),
                ignore_errors=True
            )

    return {
        "status": "success",
        "generation_id": generation_id,
        "project": request.project_name,
        "generated_files": list(files.keys()),
        "warnings": warnings,
        "validation": validation,
        "repair_attempts": repair_attempts,
        "download": download
    }


@router.get("/download/{generation_id}")
def download(generation_id: str):

    if not GENERATION_ID_PATTERN.match(generation_id):
        raise ApiException(message="Invalid generation id.", status_code=422)

    archives = [
        path for path in glob.glob(
            os.path.join(settings.GENERATED_DIR, generation_id, "*.zip")
        )
        if os.path.isfile(path)
    ]

    if not archives:
        raise ApiException(message="Generated project not found.", status_code=404)

    zip_path = archives[0]
    project_name = os.path.basename(zip_path)[:-len(".zip")]

    if not PROJECT_NAME_PATTERN.match(project_name):
        raise ApiException(message="Generated project not found.", status_code=404)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{project_name}.zip"
    )
