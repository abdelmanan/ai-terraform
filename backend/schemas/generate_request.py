import re

from pydantic import BaseModel, Field, field_validator

PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


class GenerateRequest(BaseModel):

    cloud: str

    project_name: str

    region: str

    template: str = "landing-zone"

    availability_zones: int = Field(default=2, ge=1, le=10)

    public_subnets: int = Field(default=2, ge=1, le=10)

    private_subnets: int = Field(default=2, ge=1, le=10)

    enable_nat_gateway: bool = True

    enable_cloudtrail: bool = True

    enable_cloudwatch: bool = True

    enable_s3_logs: bool = True

    @field_validator("project_name")
    @classmethod
    def validate_project_name(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("project_name must not be empty.")

        if not PROJECT_NAME_PATTERN.match(value):
            raise ValueError(
                "project_name must start with a letter or digit and contain only "
                "letters, digits, hyphens and underscores (max 63 characters)."
            )

        return value