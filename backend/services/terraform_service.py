import os


class TerraformService:

    def save(self, project_name, files):

        project_path = f"generated/{project_name}"

        os.makedirs(project_path, exist_ok=True)

        for filename, content in files.items():

            with open(f"{project_path}/{filename}", "w") as f:

                f.write(content)

        return project_path