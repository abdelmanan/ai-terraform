import logging
import os

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
from backend.utils.zip_manager import create_zip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Terraform"])

# A prompt rule cannot guarantee valid HCL: the model still emitted the removed
# `vpc = true` on aws_eip despite an explicit rule forbidding it. Showing it the
# actual terraform error fixes that reliably, so we retry instead of giving the
# raw stderr to a user who does not know Terraform.
MAX_REPAIR_ATTEMPTS = 2

# Steps the AI cannot fix: no files to reason about, or Terraform itself is
# unavailable.
UNFIXABLE_STEPS = ("skipped", "error")

prompt_service = PromptService()
ai_service = TerraformAIService()
parser = TerraformParser()
terraform_service = TerraformService()
validator = TerraformValidatorService()


# How bad a failure at each step is. A project that no longer initialises is
# worse than one that initialises but has HCL errors, however many.
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
        # Terraform being missing, hanging or crashing says nothing about the
        # generated code. Report it and still hand over the project rather than
        # throwing away work the user can perfectly well use.
        logger.warning("Could not run Terraform validation: %s", exc.message)

        return {
            "valid": False,
            "step": "error",
            "stdout": "",
            "stderr": exc.message
        }


@router.post("/generate")
def generate(request: GenerateRequest):

    logger.info(
        "Generating project '%s' (%s/%s, template=%s)",
        request.project_name, request.cloud, request.region, request.template
    )

    prompt = prompt_service.build_prompt(request)

    # Declared before the first call: the AI service reports a truncated answer
    # through it, and that has to reach the user, not just the log.
    warnings = []

    ai_response = ai_service.generate(prompt, warnings=warnings)

    files = parser.parse(ai_response)

    missing_files = parser.missing_required_files(files)
    if missing_files:
        warnings.append(
            "The AI response was missing some expected files: "
            + ", ".join(missing_files)
        )

    project_path = terraform_service.save(
        request.project_name,
        files
    )

    validation = _validate_project(project_path, missing_files)

    # A repair can make things worse: the model may return a shortened main.tf
    # while outputs.tf still references what it dropped. We keep the least
    # broken attempt and always ship that one.
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
            # Last attempt: a targeted patch has already failed, so ask for a
            # coherent rewrite of the whole project instead of another patch.
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
            # A failed repair must not lose the project already on disk: keep
            # the last validation result and let the user download it anyway.
            warnings.append(
                f"Self-repair attempt {repair_attempts} failed: {exc.message}"
            )
            break

        # The repair prompt only returns the files it changed.
        files = {**files, **repaired_files}
        missing_files = parser.missing_required_files(files)

        project_path = terraform_service.save(
            request.project_name,
            files
        )

        validation = _validate_project(project_path, missing_files)

        score = _quality_score(validation)

        if score < best_score:
            best_files, best_validation, best_score = files, validation, score

    # Only roll back when the project on disk is genuinely worse than an
    # earlier attempt: an equally good later version is fine to keep.
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
        project_path = terraform_service.save(request.project_name, files)

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

    download = f"/api/download/{request.project_name}"

    try:
        create_zip(project_path)

    except OSError as exc:
        # Same rule as validation: a late failure must not discard a generation
        # the user already paid for. The files stay on disk.
        logger.error("Could not archive project '%s': %s", request.project_name, exc)
        warnings.append(f"The project could not be archived for download: {exc}")
        download = None

    return {
        "status": "success",
        "project": request.project_name,
        "generated_files": list(files.keys()),
        "warnings": warnings,
        "validation": validation,
        "repair_attempts": repair_attempts,
        "download": download
    }


@router.get("/download/{project_name}")
def download(project_name: str):

    if not PROJECT_NAME_PATTERN.match(project_name):
        raise ApiException(message="Invalid project name.", status_code=422)

    generated_dir_abs = os.path.abspath(settings.GENERATED_DIR)
    zip_path = os.path.abspath(
        os.path.join(generated_dir_abs, f"{project_name}.zip")
    )

    if os.path.commonpath([generated_dir_abs, zip_path]) != generated_dir_abs:
        raise ApiException(message="Invalid project name.", status_code=422)

    if not os.path.isfile(zip_path):
        raise ApiException(message="Generated project not found.", status_code=404)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{project_name}.zip"
    )