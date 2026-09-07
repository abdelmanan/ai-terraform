def build_landing_zone_prompt(request):

    return f"""
You are a Senior Cloud Architect, DevSecOps Engineer and Terraform Expert.

Your mission is to generate a COMPLETE, VALID and PRODUCTION-READY AWS Landing Zone using Terraform.

=========================
PROJECT INFORMATION
=========================

Cloud Provider: {request.cloud}
Project Name: {request.project_name}
Region: {request.region}
Template: {request.template}

Availability Zones: {request.availability_zones}

Public Subnets: {request.public_subnets}

Private Subnets: {request.private_subnets}

Enable NAT Gateway: {request.enable_nat_gateway}

Enable CloudTrail: {request.enable_cloudtrail}

Enable CloudWatch: {request.enable_cloudwatch}

Enable S3 Logs: {request.enable_s3_logs}

=========================
LANDING ZONE REQUIREMENTS
=========================

Generate a production-ready AWS Landing Zone.

Respect ALL user parameters exactly.

The infrastructure must include:

- AWS Provider configuration
- VPC
- Public Subnets
- Private Subnets
- Internet Gateway
- Route Tables
- Route Table Associations
- Security Groups
- Variables
- Outputs
- terraform.tfvars
- README.md

Infrastructure requirements:

- Create exactly the requested number of Availability Zones.
- Create exactly the requested number of Public Subnets.
- Create exactly the requested number of Private Subnets.
- If Enable NAT Gateway is false, DO NOT generate any NAT Gateway.
- If Enable CloudTrail is false, DO NOT generate CloudTrail resources.
- If Enable CloudWatch is false, DO NOT generate CloudWatch resources.
- If Enable S3 Logs is false, DO NOT generate any S3 bucket dedicated to logging.

=========================
TERRAFORM BEST PRACTICES
=========================

- Generate valid Terraform code.
- Use the latest stable syntax supported by the current AWS Terraform provider.
- Use variables whenever possible.
- Do not hardcode configurable values.
- Follow Terraform naming conventions.
- Generate readable and modular code.
- Avoid deprecated Terraform resources and arguments.
- Do not use deprecated AWS provider arguments.

AWS PROVIDER COMPATIBILITY RULES:

- For aws_eip resources, use:
  domain = "vpc"
  Do NOT use:
  vpc = true

- For S3 buckets, do NOT use the acl argument inside aws_s3_bucket.
- If an S3 bucket requires an ACL, use the dedicated aws_s3_bucket_acl resource.
- For S3 bucket ownership, use aws_s3_bucket_ownership_controls when required.
- For S3 versioning, prefer aws_s3_bucket_versioning.
- For S3 server-side encryption, prefer aws_s3_bucket_server_side_encryption_configuration.
- Do not use deprecated inline S3 bucket configuration blocks when a dedicated resource exists.

All generated resources must be compatible with the current stable AWS Terraform provider.

PROVIDER DECLARATION RULES (CRITICAL):

- Every provider used anywhere in the code MUST be declared in the
  `required_providers` block of provider.tf, not only the aws provider.
- If you use any `random_*` resource (for example `random_id` to build a unique
  S3 bucket name), you MUST declare it:
  random = {{
    source  = "hashicorp/random"
    version = "~> 3.0"
  }}
- The same rule applies to every other provider you might use (tls, local, null,
  archive, ...).
- Before finalizing the output, list every resource type prefix you used
  (aws_, random_, ...) and confirm each one has a matching entry in
  required_providers. This is a mandatory self-check.

DATA SOURCE RULES (CRITICAL):

- Every `data` block referenced anywhere in the code (e.g. `data.aws_availability_zones.available`) MUST be explicitly declared in main.tf.
- Never reference a `data.<type>.<name>` attribute without first declaring the matching `data "<type>" "<name>" { ... }` block in the same project.
- If you use `data.aws_availability_zones.available.names[count.index]` to distribute resources across Availability Zones, you MUST declare:
  data "aws_availability_zones" "available" {{
    state = "available"
  }}
- Before finalizing the output, double-check that every `data.` reference in main.tf has a corresponding declared `data` block. This is a mandatory self-check.

The generated project must be able to pass:

terraform fmt
terraform init
terraform validate

=========================
OUTPUT FORMAT
=========================

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
END_TEXT

=========================
RULES
=========================

- Return ONLY the requested files.
- Do NOT explain anything.
- Do NOT add introductions.
- Do NOT add conclusions.
- Do NOT generate files that are not requested.
- Respect the output format exactly.
- If a component is disabled, do not generate it.
- Do not invent AWS resources.
- Keep the output deterministic and consistent.

The generated project must successfully execute:

terraform init

terraform fmt

terraform validate

terraform plan
"""