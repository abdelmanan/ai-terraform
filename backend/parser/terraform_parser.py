from backend.exceptions.api_exception import ApiException


class TerraformParser:

    REQUIRED_FILES = {
        "provider.tf",
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraform.tfvars",
        "README.md",
    }

    def parse(self, response: str):

        if not response or not response.strip():
            raise ApiException(
                message="The AI returned an empty response.",
                status_code=502
            )

        files = {}

        current_file = None
        current_content = []

        for line in response.splitlines():

            line = line.strip()

            # Detect file header
            if line.startswith("### "):

                # Save previous file
                if current_file:
                    self._save_file(
                        files,
                        current_file,
                        current_content
                    )

                current_file = line.replace("### ", "", 1).strip()
                current_content = []

            else:

                current_content.append(line)

        # Save last file
        if current_file:
            self._save_file(
                files,
                current_file,
                current_content
            )

        # No file marker ("### filename") found at all -> unrecognized format
        if not files:
            raise ApiException(
                message=(
                    "The AI response format is invalid: no file markers "
                    "(expected '### filename.tf' sections) were found."
                ),
                status_code=502
            )

        # Check required files
        missing_files = self.REQUIRED_FILES - set(files.keys())

        if missing_files:

            raise ApiException(
                message=(
                    "The AI response is missing required files: "
                    + ", ".join(sorted(missing_files))
                ),
                status_code=502
            )

        return files

    def _save_file(self, files, filename, content):

        if not filename:
            raise ApiException(
                message="Invalid filename detected in AI response.",
                status_code=502
            )

        content_text = "\n".join(content).strip()

        if not content_text:
            raise ApiException(
                message=f"File '{filename}' is empty.",
                status_code=502
            )

        files[filename] = self._clean_content(
            filename,
            content_text
        )

    def _clean_content(self, filename, content):

        if filename == "README.md":

            if content.startswith("BEGIN_TEXT"):
                content = content[len("BEGIN_TEXT"):].strip()

            if content.endswith("END_TEXT"):
                content = content[:-len("END_TEXT")].strip()

        else:

            if content.startswith("BEGIN_TERRAFORM"):
                content = content[len("BEGIN_TERRAFORM"):].strip()

            if content.endswith("END_TERRAFORM"):
                content = content[:-len("END_TERRAFORM")].strip()

        return content