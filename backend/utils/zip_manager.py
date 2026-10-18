import os
import zipfile

EXCLUDED_DIRS = {".terraform"}
EXCLUDED_FILES = {".terraform.lock.hcl"}


def create_zip(project_path):

    zip_path = f"{project_path}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:

        for root, dirs, files in os.walk(project_path):

            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for filename in files:

                if filename in EXCLUDED_FILES:
                    continue

                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, project_path)

                zip_file.write(file_path, arcname)

    return zip_path
