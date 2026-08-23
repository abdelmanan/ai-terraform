import pytest
from pydantic import ValidationError

from backend.schemas.generate_request import GenerateRequest


VALID_NAMES = ["my-project", "project_1", "a", "A1", "x" * 63]

INVALID_NAMES = [
    "",
    "   ",
    "../evil",
    "/etc/passwd",
    "..",
    ".",
    ".hidden",
    "name with spaces",
    "name/with/slash",
    "x" * 64,
    "name;rm -rf /",
]


@pytest.mark.parametrize("name", VALID_NAMES)
def test_project_name_accepts_valid_values(name):
    request = GenerateRequest(cloud="aws", project_name=name, region="eu-west-1")
    assert request.project_name == name


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_project_name_rejects_invalid_values(name):
    with pytest.raises(ValidationError):
        GenerateRequest(cloud="aws", project_name=name, region="eu-west-1")


def test_project_name_is_stripped():
    request = GenerateRequest(cloud="aws", project_name="  my-project  ", region="eu-west-1")
    assert request.project_name == "my-project"


def test_defaults_are_applied():
    request = GenerateRequest(cloud="aws", project_name="my-project", region="eu-west-1")
    assert request.template == "landing-zone"
    assert request.availability_zones == 2
    assert request.enable_nat_gateway is True


BOUNDED_FIELDS = ["availability_zones", "public_subnets", "private_subnets"]

VALID_BOUND_VALUES = [1, 2, 10]

INVALID_BOUND_VALUES = [0, -1, 11, 100]


@pytest.mark.parametrize("field", BOUNDED_FIELDS)
@pytest.mark.parametrize("value", VALID_BOUND_VALUES)
def test_bounded_fields_accept_values_in_range(field, value):
    request = GenerateRequest(
        cloud="aws",
        project_name="my-project",
        region="eu-west-1",
        **{field: value}
    )
    assert getattr(request, field) == value


@pytest.mark.parametrize("field", BOUNDED_FIELDS)
@pytest.mark.parametrize("value", INVALID_BOUND_VALUES)
def test_bounded_fields_reject_values_out_of_range(field, value):
    with pytest.raises(ValidationError):
        GenerateRequest(
            cloud="aws",
            project_name="my-project",
            region="eu-west-1",
            **{field: value}
        )
