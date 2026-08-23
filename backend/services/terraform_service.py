import os
import shutil
from backend.exceptions.api_exception import ApiException

class TerraformService:
    def save(self, project_name, files):

     project_path = f"generated/{project_name}"
     project_dir_abs = os.path.abspath(project_path)

     try:

        if os.path.exists(project_path):
            shutil.rmtree(project_path)

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
