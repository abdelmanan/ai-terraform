import os


class TerraformGenerator:

    def __init__(self):
        pass

    def generate_files(self, project_path: str, files: dict):

        os.makedirs(project_path, exist_ok=True)

        for filename, content in files.items():

            file_path = os.path.join(project_path, filename)

            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)

        return project_path