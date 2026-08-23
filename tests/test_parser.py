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
        "BEGIN_TERRAFORM\n"
        "provider \"aws\" {}\n"
        "END_TERRAFORM\n"
        "### main.tf\n"
        "BEGIN_TERRAFORM\n"
        "resource \"aws_vpc\" \"main\" {}\n"
        "END_TERRAFORM\n"
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
        "BEGIN_TERRAFORM\n"
        "END_TERRAFORM\n"
        "### main.tf\n"
        "BEGIN_TERRAFORM\nresource \"aws_vpc\" \"main\" {}\nEND_TERRAFORM\n"
        "### variables.tf\nBEGIN_TERRAFORM\nx\nEND_TERRAFORM\n"
        "### outputs.tf\nBEGIN_TERRAFORM\nx\nEND_TERRAFORM\n"
        "### terraform.tfvars\nBEGIN_TERRAFORM\nx\nEND_TERRAFORM\n"
        "### README.md\nBEGIN_TEXT\nx\nEND_TEXT\n"
    )

    with pytest.raises(ApiException) as exc_info:
        parser.parse(response)

    assert "provider.tf" in exc_info.value.message
    assert "empty" in exc_info.value.message.lower()


def test_readme_begin_end_text_markers_are_stripped(parser, valid_ai_response):
    files = parser.parse(valid_ai_response)
    assert "BEGIN_TEXT" not in files["README.md"]
    assert "END_TEXT" not in files["README.md"]


def test_markdown_heading_inside_readme_does_not_break_parsing(parser):
    response = (
        "### provider.tf\n"
        "BEGIN_TERRAFORM\nprovider \"aws\" {}\nEND_TERRAFORM\n"
        "### main.tf\n"
        "BEGIN_TERRAFORM\nresource \"aws_vpc\" \"main\" {}\nEND_TERRAFORM\n"
        "### variables.tf\n"
        "BEGIN_TERRAFORM\nvariable \"region\" { type = string }\nEND_TERRAFORM\n"
        "### outputs.tf\n"
        "BEGIN_TERRAFORM\noutput \"vpc_id\" { value = aws_vpc.main.id }\nEND_TERRAFORM\n"
        "### terraform.tfvars\n"
        "BEGIN_TERRAFORM\nregion = \"eu-west-1\"\nEND_TERRAFORM\n"
        "### README.md\n"
        "BEGIN_TEXT\n"
        "# Landing Zone\n"
        "\n"
        "### Usage\n"
        "\n"
        "Run terraform init.\n"
        "END_TEXT\n"
    )

    files = parser.parse(response)

    assert set(files.keys()) == TerraformParser.REQUIRED_FILES
    assert "### Usage" in files["README.md"]
    assert "Run terraform init." in files["README.md"]
