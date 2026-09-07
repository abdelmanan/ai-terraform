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


class FakePopen:
    """Minimal stand-in for the Popen object the service drives."""

    def __init__(self, result, on_communicate=None, call=None):
        self.pid = 4242
        self.returncode = result.returncode
        self._result = result
        self._on_communicate = on_communicate
        self._call = call
        self.killed = False

    def communicate(self, timeout=None):
        # The timeout moved from Popen to communicate(); record it where the
        # tests look for it.
        if self._call is not None:
            self._call["timeout"] = timeout
        if self._on_communicate:
            self._on_communicate()
        return self._result.stdout, self._result.stderr

    def kill(self):
        self.killed = True


def _record_runs(monkeypatch, results=None, on_communicate=None):
    """Capture the terraform sub-commands, not the exact argv.

    Asserting on the full command line made these tests fail whenever a flag
    was added, even though the behaviour was unchanged.
    """
    calls = []

    def fake_popen(command, **kwargs):
        call = {"subcommand": command[1], "argv": command, **kwargs}
        calls.append(call)
        result = results.pop(0) if results else _completed(0, stdout="ok")
        return FakePopen(result, on_communicate, call)

    monkeypatch.setattr(validator_module.subprocess, "Popen", fake_popen)
    return calls


def test_validate_success(monkeypatch, tmp_path):
    calls = _record_runs(monkeypatch)

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result == {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    assert [c["subcommand"] for c in calls] == ["fmt", "init", "validate"]


def test_validate_formats_the_project_before_init(monkeypatch, tmp_path):
    calls = _record_runs(monkeypatch)

    TerraformValidatorService().validate(str(tmp_path))

    fmt_call = calls[0]
    assert fmt_call["subcommand"] == "fmt"
    assert "-recursive" in fmt_call["argv"]


def test_failing_fmt_does_not_block_validation(monkeypatch, tmp_path):
    # fmt is best effort: its failure must never mask the real validate error.
    _record_runs(
        monkeypatch,
        results=[_completed(2, stderr="fmt failed"), _completed(0), _completed(0)]
    )

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is True
    assert result["step"] == "validate"


def test_init_gets_a_longer_timeout_than_the_other_commands(monkeypatch, tmp_path):
    # Measured: init takes ~57s even with a warm plugin cache.
    calls = _record_runs(monkeypatch)

    TerraformValidatorService().validate(str(tmp_path))

    timeouts = {c["subcommand"]: c["timeout"] for c in calls}

    assert timeouts["init"] == TerraformValidatorService.INIT_TIMEOUT_SECONDS
    assert timeouts["init"] > timeouts["validate"]
    assert timeouts["validate"] == TerraformValidatorService.COMMAND_TIMEOUT_SECONDS


def test_validate_stops_after_init_failure(monkeypatch, tmp_path):
    calls = _record_runs(
        monkeypatch,
        results=[_completed(0), _completed(1, stderr="init exploded")]
    )

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "init"
    assert result["stderr"] == "init exploded"
    assert "validate" not in [c["subcommand"] for c in calls]


def test_validate_reports_validate_failure(monkeypatch, tmp_path):
    _record_runs(
        monkeypatch,
        results=[_completed(0), _completed(0), _completed(1, stderr="invalid HCL")]
    )

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "validate"
    assert result["stderr"] == "invalid HCL"


def test_missing_terraform_binary_raises_api_exception(monkeypatch, tmp_path):
    def fake_popen(command, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(validator_module.subprocess, "Popen", fake_popen)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 500
    assert "not installed" in exc_info.value.message.lower()


def test_timeout_raises_api_exception(monkeypatch, tmp_path):
    def explode():
        raise subprocess.TimeoutExpired(cmd="terraform", timeout=60)

    _record_runs(monkeypatch, on_communicate=explode)
    monkeypatch.setattr(validator_module.os, "killpg", lambda pgid, sig: None)
    monkeypatch.setattr(validator_module.os, "getpgid", lambda pid: pid)

    with pytest.raises(ApiException) as exc_info:
        TerraformValidatorService().validate(str(tmp_path))

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.message.lower()


def test_plugin_cache_dir_is_passed_in_env(monkeypatch, tmp_path):
    calls = _record_runs(monkeypatch)

    TerraformValidatorService().validate(str(tmp_path))

    for call in calls:
        assert call["env"]["TF_PLUGIN_CACHE_DIR"] == (
            validator_module.settings.TERRAFORM_PLUGIN_CACHE_DIR
        )


def test_every_command_disables_terraform_colours(monkeypatch, tmp_path):
    # ANSI escape codes would be rendered as junk in the browser and fed back
    # into the self-repair prompt.
    calls = _record_runs(monkeypatch)

    TerraformValidatorService().validate(str(tmp_path))

    assert [c["subcommand"] for c in calls] == ["fmt", "init", "validate"]
    for call in calls:
        assert "-no-color" in call["argv"], call["subcommand"]


def test_init_retries_once_after_clearing_a_stale_local_cache(monkeypatch, tmp_path):
    # Preserving .terraform/ between runs leaves symlinks into the shared plugin
    # cache; a stale one makes init fail with "cannot install package into
    # target directory ... because it is a symlink".
    (tmp_path / ".terraform").mkdir()

    calls = _record_runs(
        monkeypatch,
        results=[
            _completed(0),                                  # fmt
            _completed(1, stderr="target directory is a symlink"),  # init KO
            _completed(0),                                  # init retry OK
            _completed(0),                                  # validate
        ]
    )

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is True
    assert [c["subcommand"] for c in calls] == ["fmt", "init", "init", "validate"]
    assert not (tmp_path / ".terraform").exists()


def test_init_is_not_retried_when_there_is_no_local_cache(monkeypatch, tmp_path):
    # Without a cache to blame, a second init would just burn another 180s.
    calls = _record_runs(
        monkeypatch,
        results=[_completed(0), _completed(1, stderr="genuine provider error")]
    )

    result = TerraformValidatorService().validate(str(tmp_path))

    assert result["valid"] is False
    assert result["step"] == "init"
    assert [c["subcommand"] for c in calls] == ["fmt", "init"]


def test_terraform_runs_in_its_own_process_group(monkeypatch, tmp_path):
    # Without this, a timeout kills terraform but leaves its provider plugins
    # running; they hold the provider binary open and break every later
    # `terraform init` with "text file busy" via the shared plugin cache.
    calls = _record_runs(monkeypatch)

    TerraformValidatorService().validate(str(tmp_path))

    assert calls, "no terraform command was run"
    for call in calls:
        assert call["start_new_session"] is True, call["subcommand"]


def test_timeout_kills_the_whole_process_group(monkeypatch, tmp_path):
    def explode():
        raise subprocess.TimeoutExpired(cmd="terraform", timeout=60)

    _record_runs(monkeypatch, on_communicate=explode)

    killed = {}
    monkeypatch.setattr(validator_module.os, "getpgid", lambda pid: 9999)
    monkeypatch.setattr(
        validator_module.os, "killpg",
        lambda pgid, sig: killed.update(pgid=pgid, sig=sig)
    )

    with pytest.raises(ApiException):
        TerraformValidatorService().validate(str(tmp_path))

    assert killed["pgid"] == 9999
    assert killed["sig"] == validator_module.signal.SIGKILL
