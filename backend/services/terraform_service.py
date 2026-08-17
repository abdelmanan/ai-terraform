import os
from backend.exceptions.api_exception import ApiException

class TerraformService:
    def save(self, project_name, files):

     try:

        project_path = f"generated/{project_name}"

        os.makedirs(project_path, exist_ok=True)

        for filename, content in files.items():

            with open(f"{project_path}/{filename}", "w") as f:

                f.write(content)

        return project_path

     except Exception:

        raise ApiException(
            message="Unable to save Terraform project.",
            status_code=500
        )