from types import SimpleNamespace

from backend.config import settings
from backend.prompts.landing_zone import build_landing_zone_prompt
from backend.prompts.repair import build_repair_prompt


def test_landing_zone_prompt_requires_every_provider_to_be_declared():
    # 100% of the observed validate failures were "Missing required provider":
    # random_id used in main.tf, hashicorp/random never declared.
    request = SimpleNamespace(
        cloud="aws", project_name="p", region="eu-west-1", template="landing-zone",
        availability_zones=2, public_subnets=2, private_subnets=2,
        enable_nat_gateway=True, enable_cloudtrail=True,
        enable_cloudwatch=True, enable_s3_logs=True,
    )

    prompt = build_landing_zone_prompt(request)

    assert "required_providers" in prompt
    assert "hashicorp/random" in prompt
    assert "random_id" in prompt


def test_landing_zone_prompt_pins_the_cached_provider_versions():
    # A free `~> 5.0` resolved to whatever the registry served that day; an
    # uncached version made terraform init blow its whole download budget.
    request = SimpleNamespace(
        cloud="aws", project_name="p", region="eu-west-1", template="landing-zone",
        availability_zones=2, public_subnets=2, private_subnets=2,
        enable_nat_gateway=True, enable_cloudtrail=True,
        enable_cloudwatch=True, enable_s3_logs=True,
    )

    prompt = build_landing_zone_prompt(request)

    assert f'version = "{settings.AWS_PROVIDER_VERSION}"' in prompt
    assert f'version = "{settings.RANDOM_PROVIDER_VERSION}"' in prompt
    # The only `~>` left is the rule forbidding it, never an example to copy.
    assert 'version = "~>' not in prompt


def test_repair_prompt_keeps_the_versions_pinned():
    # The repair rewrites provider.tf; without this it reintroduced the range.
    request = SimpleNamespace(
        cloud="aws", project_name="p", region="eu-west-1", template="landing-zone",
    )

    prompt = build_repair_prompt(
        request,
        {"provider.tf": "terraform {}"},
        {"valid": False, "step": "validate", "stdout": "", "stderr": "Error: boom"}
    )

    assert settings.AWS_PROVIDER_VERSION in prompt
    assert settings.RANDOM_PROVIDER_VERSION in prompt
