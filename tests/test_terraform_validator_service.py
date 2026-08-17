import subprocess
from types import SimpleNamespace

import pytest

from backend.exceptions.api_exception import ApiException
from backend.services import terraform_validator_service as validator_module
from backend.services.terraform_validator_service import TerraformValidatorService


@pytest.fixture(autouse=True)
def isolated_plugin_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        validator_module.settings,
        "TERRAFORM_PLUGIN_CACHE_DIR",
        str(tmp_path / "plugin-cache")
    )


def _completed(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_validate_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(0, stdout="ok")

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result == {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    assert calls == [
        ["terraform", "init", "-input=false"],
        ["terraform", "validate"]
    ]


def test_validate_stops_after_init_failure(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(1, stderr="init exploded")

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "init"
    assert result["stderr"] == "init exploded"
    assert len(calls) == 1


def test_validate_reports_validate_failure(monkeypatch, tmp_path):
    responses = [_completed(0), _completed(1, stderr="invalid HCL")]

    def fake_run(command, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "validate"
    assert result["stderr"] == "invalid HCL"


def test_missing_terraform_binary_raises_api_exception(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 500
    assert "not installed" in exc_info.value.message.lower()


def test_timeout_raises_api_exception(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=60)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.message.lower()


def test_plugin_cache_dir_is_passed_in_env(monkeypatch, tmp_path):
    captured_env = {}

    def fake_run(command, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        return _completed(0)

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)

    TerraformValidatorService().validate(str(tmp_path))

    assert captured_env["TF_PLUGIN_CACHE_DIR"] == validator_module.settings.TERRAFORM_PLUGIN_CACHE_DIR
