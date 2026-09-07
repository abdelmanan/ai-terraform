from types import SimpleNamespace

from backend.prompts.landing_zone import build_landing_zone_prompt


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
