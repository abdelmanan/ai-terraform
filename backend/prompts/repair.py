from backend.config import settings

TEXT_FILES = {"README.md": ("BEGIN_TEXT", "END_TEXT")}

DEFAULT_MARKERS = ("BEGIN_TERRAFORM", "END_TERRAFORM")


def _render_files(files):

    blocks = []

    for filename, content in files.items():

        begin, end = TEXT_FILES.get(filename, DEFAULT_MARKERS)

        blocks.append(f"### {filename}\n{begin}\n{content}\n{end}")

    return "\n\n".join(blocks)


PARTIAL_OUTPUT = """Return ONLY the files you actually modified, using the exact same format:

### main.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

Do NOT return unchanged files."""

FULL_OUTPUT = """The previous targeted fix did not work, so rewrite the WHOLE project.

Return ALL SIX files, consistent with one another. Every resource referenced
must exist and every provider used must be declared in required_providers.

Use exactly this format, with no text before or after:

### provider.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### main.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### variables.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### outputs.tf
BEGIN_TERRAFORM
...
END_TERRAFORM

### terraform.tfvars
BEGIN_TERRAFORM
...
END_TERRAFORM

### README.md
BEGIN_TEXT
...
END_TEXT"""


def _output_rules(full_rewrite):

    return FULL_OUTPUT if full_rewrite else PARTIAL_OUTPUT


def build_repair_prompt(request, files, validation, full_rewrite=False):

    error_output = (
        (validation.get("stderr") or "").strip()
        or (validation.get("stdout") or "").strip()
        or "Unknown Terraform error."
    )

    return f"""You are a Senior Terraform Expert.

The Terraform project below was generated for project "{request.project_name}"
on {request.cloud} in region {request.region}, but it FAILED.

=========================
FAILED COMMAND
=========================

terraform {validation.get("step", "validate")}

=========================
ERROR OUTPUT
=========================

{error_output}

=========================
CURRENT PROJECT FILES
=========================

{_render_files(files)}

=========================
YOUR TASK
=========================

- Fix ONLY what is required to make `terraform validate` pass.
- The error output above is authoritative: trust it over your own assumptions.
- Do not redesign the infrastructure and do not rename resources.
- Keep every user parameter unchanged.
- Use arguments supported by the current stable AWS provider (for example
  `domain = "vpc"` on aws_eip, never the removed `vpc = true`).
- Every `data.<type>.<name>` reference must have a matching declared data block.
- Keep the provider versions pinned exactly as follows, never as a range:
  hashicorp/aws = "{settings.AWS_PROVIDER_VERSION}",
  hashicorp/random = "{settings.RANDOM_PROVIDER_VERSION}".

=========================
OUTPUT FORMAT
=========================

{_output_rules(full_rewrite)}

Do NOT explain anything.
Do NOT add introductions or conclusions.
"""
