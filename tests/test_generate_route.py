import re
import threading

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import settings
from backend.exceptions.api_exception import ApiException
from backend.routes import generate as generate_module

client = TestClient(app)
# Needed to observe the formatted 500 response instead of TestClient re-raising
# the original exception (its default behavior for unhandled server errors).
client_no_raise = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def stub_pipeline(monkeypatch):
    monkeypatch.setattr(
        generate_module.prompt_service, "build_prompt", lambda request: "a prompt"
    )
    monkeypatch.setattr(
        generate_module.ai_service,
        "generate",
        lambda prompt, warnings=None: "raw ai response"
    )
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {
            "provider.tf": "provider \"aws\" {}",
            "main.tf": "resource \"aws_vpc\" \"main\" {}",
            "variables.tf": "variable \"region\" {}",
            "outputs.tf": "output \"vpc_id\" { value = aws_vpc.main.id }",
            "terraform.tfvars": "region = \"eu-west-1\"",
            "README.md": "# Landing Zone",
        }
    )
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda generation_id, project_name, files: f"generated/{generation_id}/{project_name}"
    )
    monkeypatch.setattr(
        generate_module.validator,
        "validate",
        lambda project_path: {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    )
    monkeypatch.setattr(
        generate_module, "create_zip", lambda project_path: f"{project_path}.zip"
    )
    monkeypatch.setattr(generate_module, "purge_expired_generations", lambda: 0)


def test_generate_success(valid_generate_payload):
    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["project"] == valid_generate_payload["project_name"]
    assert set(body["generated_files"]) == {
        "provider.tf", "main.tf", "variables.tf", "outputs.tf",
        "terraform.tfvars", "README.md",
    }
    assert body["warnings"] == []
    assert body["validation"]["valid"] is True
    assert re.fullmatch(r"[0-9a-f]{32}", body["generation_id"])
    assert body["download"] == f"/api/download/{body['generation_id']}"


def test_two_generations_of_the_same_project_do_not_share_a_directory(
    monkeypatch, valid_generate_payload
):
    paths = []
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda gid, name, files: paths.append(f"generated/{gid}/{name}") or paths[-1]
    )

    first = client.post("/api/generate", json=valid_generate_payload).json()
    second = client.post("/api/generate", json=valid_generate_payload).json()

    assert first["generation_id"] != second["generation_id"]
    assert paths[0] != paths[1]
    assert first["download"] != second["download"]


def test_generate_answers_429_when_all_slots_are_busy(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(generate_module, "generation_slots", threading.BoundedSemaphore(1))
    generate_module.generation_slots.acquire()

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 429
    assert response.json()["status"] == "error"


def test_a_slot_is_released_even_when_the_generation_fails(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(generate_module, "generation_slots", threading.BoundedSemaphore(1))

    def raise_ai_error(prompt, warnings=None):
        raise ApiException(message="Groq is down", status_code=502)

    monkeypatch.setattr(generate_module.ai_service, "generate", raise_ai_error)

    assert client.post("/api/generate", json=valid_generate_payload).status_code == 502
    assert client.post("/api/generate", json=valid_generate_payload).status_code == 502


def test_provider_versions_are_pinned_before_saving(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {
            "provider.tf": (
                'terraform {\n  required_providers {\n    aws = {\n'
                '      source  = "hashicorp/aws"\n      version = "~> 5.0"\n'
                '    }\n  }\n}\n'
            ),
            "main.tf": "resource \"aws_vpc\" \"main\" {}",
        }
    )
    saved = []
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda gid, name, files: saved.append(dict(files)) or f"generated/{gid}/{name}"
    )

    client.post("/api/generate", json=valid_generate_payload)

    assert "~>" not in saved[0]["provider.tf"]
    assert f'version = "{settings.AWS_PROVIDER_VERSION}"' in saved[0]["provider.tf"]


def test_the_local_copy_is_removed_once_the_archive_is_on_s3(
    monkeypatch, tmp_path, valid_generate_payload
):
    monkeypatch.setattr(settings, "GENERATED_DIR", str(tmp_path))
    monkeypatch.setattr(generate_module, "is_remote", lambda: True)
    monkeypatch.setattr(
        generate_module, "publish_archive",
        lambda zip_path, gid, name: "https://bucket.s3.amazonaws.com/signed"
    )

    def save(gid, name, files):
        path = tmp_path / gid / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    monkeypatch.setattr(generate_module.terraform_service, "save", save)

    body = client.post("/api/generate", json=valid_generate_payload).json()

    assert body["download"] == "https://bucket.s3.amazonaws.com/signed"
    assert not (tmp_path / body["generation_id"]).exists()


def test_a_truncated_ai_answer_reaches_the_api_response(monkeypatch, valid_generate_payload):
    # The AI service reports truncation through the warnings list; this checks
    # the whole path up to the JSON the browser displays.
    def truncating_generate(prompt, warnings=None):
        warnings.append("The AI answer was cut off at the 12000 token limit.")
        return "raw ai response"

    monkeypatch.setattr(generate_module.ai_service, "generate", truncating_generate)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    assert any("cut off" in w for w in response.json()["warnings"])


def test_generate_reports_warnings_when_files_missing_but_still_succeeds(
    monkeypatch, valid_generate_payload
):
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {
            "provider.tf": "provider \"aws\" {}",
            "main.tf": "resource \"aws_vpc\" \"main\" {}",
        }
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert set(body["generated_files"]) == {"provider.tf", "main.tf"}
    assert any("missing" in w.lower() for w in body["warnings"])
    assert body["download"] == f"/api/download/{body['generation_id']}"


def test_generate_skips_validation_when_main_files_missing(
    monkeypatch, valid_generate_payload
):
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {"README.md": "# only a readme"}
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["validation"]["valid"] is False
    assert body["validation"]["step"] == "skipped"


def test_generate_reports_terraform_validation_failure(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(
        generate_module.validator,
        "validate",
        lambda project_path: {
            "valid": False, "step": "validate", "stdout": "", "stderr": "invalid HCL"
        }
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    assert response.json()["validation"]["valid"] is False


def test_generate_propagates_ai_service_failure(monkeypatch, valid_generate_payload):
    def raise_ai_error(prompt, warnings=None):
        raise ApiException(message="Groq is down", status_code=502)

    monkeypatch.setattr(generate_module.ai_service, "generate", raise_ai_error)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 502
    assert response.json() == {"status": "error", "message": "Groq is down"}


def test_generate_propagates_parser_failure(monkeypatch, valid_generate_payload):
    def raise_parser_error(response):
        raise ApiException(message="bad AI format", status_code=502)

    monkeypatch.setattr(generate_module.parser, "parse", raise_parser_error)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 502
    assert response.json()["message"] == "bad AI format"


def test_generate_unexpected_error_returns_500(monkeypatch, valid_generate_payload):
    def raise_unexpected(request):
        raise RuntimeError("something broke")

    monkeypatch.setattr(generate_module.prompt_service, "build_prompt", raise_unexpected)

    response = client_no_raise.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 500
    assert response.json()["status"] == "error"


def test_generate_rejects_invalid_project_name(valid_generate_payload):
    valid_generate_payload["project_name"] = "../evil"

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 422


@pytest.mark.parametrize("field,value", [
    ("cloud", "azure"),
    ("template", "kubernetes"),
    ("region", "paris"),
])
def test_generate_rejects_unsupported_inputs(valid_generate_payload, field, value):
    valid_generate_payload[field] = value

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 422


GENERATION_ID = "0123456789abcdef0123456789abcdef"


def _archive(generated, generation_id=GENERATION_ID, name="my-project"):
    workspace = generated / generation_id
    workspace.mkdir(parents=True)
    (workspace / f"{name}.zip").write_bytes(b"PK\x03\x04fake-zip")


def test_download_returns_zip(tmp_path, monkeypatch):
    _archive(tmp_path)
    monkeypatch.setattr(settings, "GENERATED_DIR", str(tmp_path))

    response = client.get(f"/api/download/{GENERATION_ID}")

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04fake-zip"
    assert response.headers["content-type"] == "application/zip"
    # The user gets their project name back, not the opaque id.
    assert 'filename="my-project.zip"' in response.headers["content-disposition"]


def test_download_is_independent_of_the_current_working_directory(
    tmp_path, monkeypatch
):
    generated = tmp_path / "generated"
    _archive(generated)
    monkeypatch.setattr(settings, "GENERATED_DIR", str(generated))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    response = client.get(f"/api/download/{GENERATION_ID}")

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04fake-zip"


def test_download_missing_generation_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "GENERATED_DIR", str(tmp_path))

    response = client.get(f"/api/download/{GENERATION_ID}")

    assert response.status_code == 404


@pytest.mark.parametrize("bad_id", ["my-project", "0123abc", "invalid%20name", "0123456789ABCDEF0123456789ABCDEF"])
def test_download_rejects_anything_but_a_generation_id(bad_id):
    response = client.get(f"/api/download/{bad_id}")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Self-repair loop
# ---------------------------------------------------------------------------

BROKEN = {
    "valid": False, "step": "validate", "stdout": "",
    "stderr": 'Error: Unsupported argument\n  66:   vpc = true',
}
FIXED = {"valid": True, "step": "validate", "stdout": "Success!", "stderr": ""}


def _count_ai_calls(monkeypatch):
    prompts = []

    def fake_generate(prompt, warnings=None):
        prompts.append(prompt)
        return "raw ai response"

    monkeypatch.setattr(generate_module.ai_service, "generate", fake_generate)
    return prompts


def _validations(monkeypatch, sequence):
    monkeypatch.setattr(
        generate_module.validator, "validate", lambda path: sequence.pop(0)
    )


def test_no_repair_attempted_when_validation_passes(monkeypatch, valid_generate_payload):
    prompts = _count_ai_calls(monkeypatch)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.json()["repair_attempts"] == 0
    assert len(prompts) == 1


def test_repair_fixes_an_invalid_project(monkeypatch, valid_generate_payload):
    prompts = _count_ai_calls(monkeypatch)
    _validations(monkeypatch, [BROKEN, FIXED])

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    assert body["validation"]["valid"] is True
    assert body["repair_attempts"] == 1
    assert len(prompts) == 2
    # The repair prompt must carry the actual terraform error.
    assert "vpc = true" in prompts[1]
    assert any("self-repair" in w.lower() for w in body["warnings"])


def test_repair_gives_up_after_max_attempts(monkeypatch, valid_generate_payload):
    prompts = _count_ai_calls(monkeypatch)
    monkeypatch.setattr(generate_module.validator, "validate", lambda path: BROKEN)

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    assert body["repair_attempts"] == generate_module.MAX_REPAIR_ATTEMPTS
    assert len(prompts) == 1 + generate_module.MAX_REPAIR_ATTEMPTS
    assert body["validation"]["valid"] is False
    # The project is still delivered, broken but downloadable.
    assert body["status"] == "success"
    assert body["download"].endswith(body["generation_id"])


def test_repair_is_skipped_when_validation_was_skipped(monkeypatch, valid_generate_payload):
    prompts = _count_ai_calls(monkeypatch)
    monkeypatch.setattr(
        generate_module.parser, "parse", lambda response: {"README.md": "# only a readme"}
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.json()["validation"]["step"] == "skipped"
    assert response.json()["repair_attempts"] == 0
    assert len(prompts) == 1


def test_repair_merges_only_the_files_the_ai_returned(monkeypatch, valid_generate_payload):
    _count_ai_calls(monkeypatch)
    _validations(monkeypatch, [BROKEN, FIXED])

    original = {
        "provider.tf": "provider \"aws\" {}",
        "main.tf": "vpc = true",
        "variables.tf": "variable \"region\" {}",
        "outputs.tf": "output \"vpc_id\" {}",
        "terraform.tfvars": "region = \"eu-west-1\"",
        "README.md": "# Landing Zone",
    }
    parses = [original, {"main.tf": "domain = \"vpc\""}]
    monkeypatch.setattr(generate_module.parser, "parse", lambda r: parses.pop(0))

    saved = []
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda gid, name, files: saved.append(dict(files)) or f"generated/{gid}/{name}"
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.json()["validation"]["valid"] is True
    # Second save keeps every original file, with main.tf replaced.
    assert set(saved[1]) == set(original)
    assert saved[1]["main.tf"] == "domain = \"vpc\""
    assert saved[1]["README.md"] == "# Landing Zone"


def test_failing_repair_call_still_returns_the_project(monkeypatch, valid_generate_payload):
    monkeypatch.setattr(generate_module.validator, "validate", lambda path: BROKEN)

    calls = {"n": 0}

    def flaky_generate(prompt, warnings=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise ApiException(message="Groq rate limit", status_code=429)
        return "raw ai response"

    monkeypatch.setattr(generate_module.ai_service, "generate", flaky_generate)

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["validation"]["valid"] is False
    assert any("Groq rate limit" in w for w in body["warnings"])


WORSE = {
    "valid": False, "step": "validate", "stdout": "",
    "stderr": "Error: Reference to undeclared resource\nError: Reference to undeclared resource",
}


def test_a_repair_that_makes_things_worse_is_discarded(monkeypatch, valid_generate_payload):
    # Observed for real: the repair returned a shortened main.tf while
    # outputs.tf still referenced the resources it had dropped.
    _count_ai_calls(monkeypatch)
    _validations(monkeypatch, [BROKEN, WORSE, WORSE])

    original = {
        "provider.tf": "provider \"aws\" {}",
        "main.tf": "GOOD main with every resource",
        "variables.tf": "v", "outputs.tf": "o",
        "terraform.tfvars": "t", "README.md": "r",
    }
    parses = [original, {"main.tf": "TRUNCATED"}, {"main.tf": "TRUNCATED AGAIN"}]
    monkeypatch.setattr(generate_module.parser, "parse", lambda r: parses.pop(0))

    saved = []
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda gid, name, files: saved.append(dict(files)) or f"generated/{gid}/{name}"
    )

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    # The last write to disk restores the least broken version.
    assert saved[-1]["main.tf"] == "GOOD main with every resource"
    # And the reported validation is the one that version actually produced.
    assert body["validation"]["stderr"] == BROKEN["stderr"]
    assert any("made the project worse" in w for w in body["warnings"])
    assert body["status"] == "success"


def test_a_repair_that_improves_without_fixing_is_kept(monkeypatch, valid_generate_payload):
    # Fewer errors is still progress: it must not be thrown away.
    _count_ai_calls(monkeypatch)
    _validations(monkeypatch, [WORSE, BROKEN, BROKEN])

    parses = [
        {"provider.tf": "p", "main.tf": "bad", "variables.tf": "v",
         "outputs.tf": "o", "terraform.tfvars": "t", "README.md": "r"},
        {"main.tf": "better"},
        {"main.tf": "better"},
    ]
    monkeypatch.setattr(generate_module.parser, "parse", lambda r: parses.pop(0))

    saved = []
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda gid, name, files: saved.append(dict(files)) or f"generated/{gid}/{name}"
    )

    response = client.post("/api/generate", json=valid_generate_payload)

    assert saved[-1]["main.tf"] == "better"
    assert not any("made the project worse" in w for w in response.json()["warnings"])


def _score(step, stderr, valid=False):
    return generate_module._quality_score(
        {"valid": valid, "step": step, "stderr": stderr}
    )


def test_quality_score_ranks_attempts():
    assert _score("validate", "", valid=True) == 0
    assert _score("validate", "Error: a") < _score("validate", "Error: a\nError: b")
    # A failure with no parsable "Error:" still counts as broken.
    assert _score("validate", "") > 0


def test_a_broken_init_ranks_worse_than_any_validate_failure():
    # Observed for real: a repair turned a 2-error validate failure into a
    # project that no longer initialised, and the naive count preferred it.
    many_validate_errors = "Error: x\n" * 50

    assert _score("init", "Error: one") > _score("validate", many_validate_errors)
    assert _score("error", "boom") > _score("init", "Error: one")
    assert _score("skipped", "missing files") > _score("error", "boom")


# ---------------------------------------------------------------------------
# Degraded modes: a late failure must never discard a usable generation
# ---------------------------------------------------------------------------

def test_terraform_failure_still_returns_the_project(monkeypatch, valid_generate_payload):
    # Observed for real: `terraform validate` timed out on a repair pass and the
    # whole request died with a 504, throwing away a project already on disk.
    def boom(project_path):
        raise ApiException(message="terraform validate timed out after 60s.", status_code=504)

    monkeypatch.setattr(generate_module.validator, "validate", boom)

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["validation"]["step"] == "error"
    assert "timed out" in body["validation"]["stderr"]
    assert body["download"].endswith(body["generation_id"])


def test_no_repair_is_attempted_when_terraform_itself_failed(monkeypatch, valid_generate_payload):
    # The AI cannot fix a broken terraform CLI: burning Groq calls is pointless.
    prompts = _count_ai_calls(monkeypatch)

    def boom(project_path):
        raise ApiException(message="Terraform CLI is not installed.", status_code=500)

    monkeypatch.setattr(generate_module.validator, "validate", boom)

    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.json()["repair_attempts"] == 0
    assert len(prompts) == 1


def test_failing_zip_still_returns_the_validation_result(monkeypatch, valid_generate_payload):
    def boom(project_path):
        raise OSError("No space left on device")

    monkeypatch.setattr(generate_module, "create_zip", boom)

    response = client.post("/api/generate", json=valid_generate_payload)
    body = response.json()

    assert response.status_code == 200
    assert body["validation"]["valid"] is True
    assert body["download"] is None
    assert any("could not be archived" in w for w in body["warnings"])


def test_last_repair_attempt_asks_for_a_full_rewrite(monkeypatch, valid_generate_payload):
    # A targeted patch cannot fix an inconsistency between two files: the model
    # repairs one side and breaks the other. Measured on "Missing required
    # provider" (main.tf used random_id, provider.tf never declared it).
    prompts = _count_ai_calls(monkeypatch)
    monkeypatch.setattr(generate_module.validator, "validate", lambda p: BROKEN)

    client.post("/api/generate", json=valid_generate_payload)

    assert len(prompts) == 1 + generate_module.MAX_REPAIR_ATTEMPTS
    assert "ONLY the files you actually modified" in prompts[1]
    assert "rewrite the WHOLE project" in prompts[-1]
    assert "ALL SIX files" in prompts[-1]
