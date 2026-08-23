import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.exceptions.api_exception import ApiException
from backend.schemas.generate_request import PROJECT_NAME_PATTERN, GenerateRequest
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
        "download": f"/api/download/{request.project_name}"
    }


@router.get("/download/{project_name}")
def download(project_name: str):

    if not PROJECT_NAME_PATTERN.match(project_name):
        raise ApiException(message="Invalid project name.", status_code=422)

    zip_path = os.path.abspath(f"generated/{project_name}.zip")
    generated_dir_abs = os.path.abspath("generated")

    if os.path.commonpath([generated_dir_abs, zip_path]) != generated_dir_abs:
        raise ApiException(message="Invalid project name.", status_code=422)

    if not os.path.isfile(zip_path):
        raise ApiException(message="Generated project not found.", status_code=404)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{project_name}.zip"
    )