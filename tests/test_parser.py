import pytest

from backend.exceptions.api_exception import ApiException
from backend.parser.terraform_parser import TerraformParser


@pytest.fixture
def parser():
    return TerraformParser()


def test_parse_valid_response(parser, valid_ai_response):
    files = parser.parse(valid_ai_response)

    assert set(files.keys()) == TerraformParser.REQUIRED_FILES
    assert 'resource "aws_vpc" "main"' in files["main.tf"]
    assert "BEGIN_TERRAFORM" not in files["main.tf"]
    assert "END_TERRAFORM" not in files["main.tf"]


def test_parse_empty_response_raises(parser):
    with pytest.raises(ApiException) as exc_info:
        parser.parse("")

    assert exc_info.value.status_code == 502
    assert "empty" in exc_info.value.message.lower()


def test_parse_whitespace_only_response_raises(parser):
    with pytest.raises(ApiException):
        parser.parse("   \n   ")


def test_parse_unrecognized_format_raises(parser):
    response = "BEGIN_TERRAFORM\nresource \"aws_vpc\" \"main\" {}\nEND_TERRAFORM"

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert exc_info.value.status_code == 502
    assert "no file markers" in exc_info.value.message.lower()


def test_parse_missing_required_files_raises(parser):
    response = (
        "### provider.tf\n"
        "provider \"aws\" {}\n"
        "### main.tf\n"
        "resource \"aws_vpc\" \"main\" {}\n"
    )

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert exc_info.value.status_code == 502
    assert "missing required files" in exc_info.value.message.lower()
    for missing in ("outputs.tf", "variables.tf", "terraform.tfvars", "README.md"):
        assert missing in exc_info.value.message


def test_parse_file_with_empty_content_raises(parser):
    response = (
        "### provider.tf\n"
        "\n"
        "### main.tf\n"
        "resource \"aws_vpc\" \"main\" {}\n"
        "### variables.tf\nx\n"
        "### outputs.tf\nx\n"
        "### terraform.tfvars\nx\n"
        "### README.md\nx\n"
    )

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert "provider.tf" in exc_info.value.message
    assert "empty" in exc_info.value.message.lower()


def test_readme_begin_end_text_markers_are_stripped(parser, valid_ai_response):
    files = parser.parse(valid_ai_response)
    assert "BEGIN_TEXT" not in files["README.md"]
    assert "END_TEXT" not in files["README.md"]
