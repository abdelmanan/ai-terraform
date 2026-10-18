import os
import shutil

from backend.config import settings
from backend.exceptions.api_exception import ApiException

PRESERVED_ENTRIES = {".terraform", ".terraform.lock.hcl"}


class TerraformService:

    def save(self, generation_id, project_name, files):

        project_path = os.path.join(settings.GENERATED_DIR, generation_id, project_name)
        project_dir_abs = os.path.abspath(project_path)

        try:

            if os.path.exists(project_path):
                self._clear(project_path)

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

    def _clear(self, project_path):
        """Remove the previous generation, keeping Terraform's local caches."""

        for entry in os.listdir(project_path):

            if entry in PRESERVED_ENTRIES:
                continue

            entry_path = os.path.join(project_path, entry)

            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)
