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