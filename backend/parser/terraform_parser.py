import re

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

    BEGIN_MARKERS = {"BEGIN_TERRAFORM", "BEGIN_TEXT"}

    FILE_HEADER_PATTERN = re.compile(r"^### (.+)$")

    def parse(self, response: str):

        if not response or not response.strip():
            raise ApiException(
                message="The AI returned an empty response.",
                status_code=502
            )

        lines = response.splitlines()

        files = {}

        current_file = None
        current_content = []

        for index, raw_line in enumerate(lines):

            line = raw_line.strip()

            next_line = lines[index + 1].strip() if index + 1 < len(lines) else None

            header_match = self.FILE_HEADER_PATTERN.match(line)

            if header_match and next_line in self.BEGIN_MARKERS:

                if current_file:
                    self._save_file(
                        files,
                        current_file,
                        current_content
                    )

                current_file = header_match.group(1).strip()
                current_content = []

            else:
                current_content.append(raw_line)

        if current_file:
            self._save_file(
                files,
                current_file,
                current_content
            )

        if not files:
            raise ApiException(
                message=(
                    "The AI response format is invalid: no file markers "
                    "(expected '### filename.tf' sections) were found."
                ),
                status_code=502
            )

        return files

    def missing_required_files(self, files):
        return sorted(self.REQUIRED_FILES - set(files.keys()))

    def _save_file(self, files, filename, content):

        if not filename:
            return

        content_text = "\n".join(content).strip()

        cleaned_content = self._clean_content(
            filename,
            content_text
        )

        if not cleaned_content:
            return

        files[filename] = cleaned_content

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
