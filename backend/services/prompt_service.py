class PromptService:

    def build_prompt(self, request):

        return f"""
You are a Senior Cloud Architect, DevOps Engineer and Terraform Expert.

Your mission is to generate a COMPLETE and VALID Terraform project.

=========================
PROJECT INFORMATION
=========================

Cloud Provider: {request.cloud}
Project Name: {request.project_name}
Region: {request.region}
Template: {request.template}

=========================
REQUIREMENTS
=========================

Generate a production-ready Terraform project.

The infrastructure must follow Terraform best practices.

Generate exactly these files:

### provider.tf

### main.tf

### variables.tf

### outputs.tf

### terraform.tfvars

### README.md

=========================
RULES
=========================

- Return ONLY the Terraform project.
- Do NOT explain anything.
- Do NOT add introductions.
- Do NOT add conclusions.
- Do NOT write comments outside the files.
- Every file MUST start with its filename.
- Wrap Terraform code between:
BEGIN_TERRAFORM
...
END_TERRAFORM
- Wrap README between:
BEGIN_TEXT
...
END_TEXT
- Generate valid Terraform syntax.
- Use variables whenever possible.
- The project must work after:
terraform init
terraform validate
terraform plan

=========================
OUTPUT FORMAT
=========================

### provider.tf
BEGIN_TERRAFORM
<provider code>
END_TERRAFORM

### main.tf
BEGIN_TERRAFORM
<main code>
END_TERRAFORM

### variables.tf
BEGIN_TERRAFORM
<variables code>
END_TERRAFORM

### outputs.tf
BEGIN_TERRAFORM
<outputs code>
END_TERRAFORM

### terraform.tfvars
BEGIN_TERRAFORM
<tfvars code>
END_TERRAFORM

### README.md
BEGIN_TEXT
<readme content>
END_TEXT
"""