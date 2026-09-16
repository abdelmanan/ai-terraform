from backend.config import settings
from backend.utils.provider_pin import pin_provider_versions

AWS = f'version = "{settings.AWS_PROVIDER_VERSION}"'
RANDOM = f'version = "{settings.RANDOM_PROVIDER_VERSION}"'

PROVIDER_WITH_RANGE = '''terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
'''


def test_a_version_range_is_replaced_by_the_cached_version():
    files = pin_provider_versions({"provider.tf": PROVIDER_WITH_RANGE})

    assert "~> 5.0" not in files["provider.tf"]
    assert AWS in files["provider.tf"]
    # Terraform's own constraint is not a provider version: leave it alone.
    assert 'required_version = ">= 1.5"' in files["provider.tf"]


def test_a_missing_version_is_added():
    content = 'terraform {\n  required_providers {\n    aws = {\n      source = "hashicorp/aws"\n    }\n  }\n}\n'

    files = pin_provider_versions({"provider.tf": content})

    assert AWS in files["provider.tf"]


def test_a_missing_required_providers_block_is_created():
    files = pin_provider_versions({
        "provider.tf": 'provider "aws" {\n  region = "eu-west-3"\n}\n',
        "main.tf": 'resource "aws_vpc" "main" {}',
    })

    assert "required_providers" in files["provider.tf"]
    assert AWS in files["provider.tf"]
    assert "random" not in files["provider.tf"]
    assert 'provider "aws"' in files["provider.tf"]


def test_the_random_provider_is_declared_when_random_resources_are_used():
    files = pin_provider_versions({
        "provider.tf": PROVIDER_WITH_RANGE,
        "main.tf": 'resource "random_id" "suffix" {\n  byte_length = 4\n}',
    })

    assert files["provider.tf"].count("hashicorp/random") == 1
    assert RANDOM in files["provider.tf"]


def test_an_already_declared_random_provider_is_not_duplicated():
    content = PROVIDER_WITH_RANGE.replace(
        "    }\n  }\n}",
        '    }\n    random = {\n      source  = "hashicorp/random"\n      version = ">= 3.0"\n    }\n  }\n}',
        1,
    )

    files = pin_provider_versions({
        "provider.tf": content,
        "main.tf": 'resource "random_id" "suffix" {}',
    })

    assert files["provider.tf"].count("hashicorp/random") == 1
    assert RANDOM in files["provider.tf"]
    assert ">= 3.0" not in files["provider.tf"]


def test_non_terraform_files_are_untouched():
    readme = 'required_providers {\n  aws = { version = "~> 5.0" }\n}'

    files = pin_provider_versions({"provider.tf": PROVIDER_WITH_RANGE, "README.md": readme})

    assert files["README.md"] == readme


def test_the_input_dict_is_not_mutated():
    original = {"provider.tf": PROVIDER_WITH_RANGE}

    pin_provider_versions(original)

    assert original["provider.tf"] == PROVIDER_WITH_RANGE
