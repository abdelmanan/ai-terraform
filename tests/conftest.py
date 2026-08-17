import httpx
import pytest


def _fake_response(status_code=500):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})


@pytest.fixture
def fake_openai_request():
    return httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


@pytest.fixture
def fake_openai_response():
    return _fake_response


@pytest.fixture
def valid_ai_response():
    return """### provider.tf
BEGIN_TERRAFORM
provider "aws" {
  region = "eu-west-1"
}
END_TERRAFORM

### main.tf
BEGIN_TERRAFORM
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
END_TERRAFORM

### variables.tf
BEGIN_TERRAFORM
variable "region" {
  type = string
}
END_TERRAFORM

### outputs.tf
BEGIN_TERRAFORM
output "vpc_id" {
  value = aws_vpc.main.id
}
END_TERRAFORM

### terraform.tfvars
BEGIN_TERRAFORM
region = "eu-west-1"
END_TERRAFORM

### README.md
BEGIN_TEXT
# Landing Zone

Generated project.
END_TEXT
"""


@pytest.fixture
def valid_generate_payload():
    return {
        "cloud": "aws",
        "project_name": "test-project",
        "region": "eu-west-1",
        "template": "landing-zone",
        "availability_zones": 2,
        "public_subnets": 2,
        "private_subnets": 2,
        "enable_nat_gateway": True,
        "enable_cloudtrail": True,
        "enable_cloudwatch": True,
        "enable_s3_logs": True
    }
