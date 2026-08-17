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