import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")

# Forme d'une région AWS (eu-west-3, us-gov-west-1, ap-southeast-4...). On ne
# tient pas de liste exhaustive : elle dériverait à chaque nouvelle région.
REGION_PATTERN = re.compile(r"^[a-z]{2}(-gov|-iso[a-z]?)?-[a-z]+-\d{1,2}$")


class GenerateRequest(BaseModel):

    # Seuls aws/landing-zone sont implémentés : `cloud="azure"` produisait
    # quand même du Terraform AWS, en silence.
    cloud: Literal["aws"]

    project_name: str

    region: str

    template: Literal["landing-zone"] = "landing-zone"

    availability_zones: int = Field(default=2, ge=1, le=10)

    public_subnets: int = Field(default=2, ge=1, le=10)

    private_subnets: int = Field(default=2, ge=1, le=10)

    enable_nat_gateway: bool = True

    enable_cloudtrail: bool = True

    enable_cloudwatch: bool = True

    enable_s3_logs: bool = True

    @field_validator("region")
    @classmethod
    def validate_region(cls, value: str) -> str:

        value = value.strip()

        if not REGION_PATTERN.match(value):
            raise ValueError("region must be an AWS region code, e.g. eu-west-3.")

        return value

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