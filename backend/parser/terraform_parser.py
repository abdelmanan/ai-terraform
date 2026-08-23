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

            # Only treat a "### ..." line as a new file marker when it is
            # immediately followed by a BEGIN marker. This avoids breaking
            # on Markdown headings (e.g. "### Usage") inside README.md content.
            if header_match and next_line in self.BEGIN_MARKERS:

                # Save previous file
                if current_file:
                    self._save_file(
                        files,
                        current_file,
                        current_content
                    )

                current_file = header_match.group(1).strip()
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

        # No file marker ("### filename" followed by a BEGIN marker) found at all
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

        cleaned_content = self._clean_content(
            filename,
            content_text
        )

        if not cleaned_content:
            raise ApiException(
                message=f"File '{filename}' is empty.",
                status_code=502
            )

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
