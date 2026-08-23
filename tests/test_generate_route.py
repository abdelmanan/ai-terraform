import pytest
from fastapi.testclient import TestClient

from backend.app import app
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
        generate_module.ai_service, "generate", lambda prompt: "raw ai response"
    )
    monkeypatch.setattr(
        generate_module.parser,
        "parse",
        lambda response: {"main.tf": "resource \"aws_vpc\" \"main\" {}"}
    )
    monkeypatch.setattr(
        generate_module.terraform_service,
        "save",
        lambda project_name, files: f"generated/{project_name}"
    )
    monkeypatch.setattr(
        generate_module.validator,
        "validate",
        lambda project_path: {"valid": True, "step": "validate", "stdout": "ok", "stderr": ""}
    )
    monkeypatch.setattr(
        generate_module, "create_zip", lambda project_path: f"{project_path}.zip"
    )


def test_generate_success(valid_generate_payload):
    response = client.post("/api/generate", json=valid_generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["project"] == valid_generate_payload["project_name"]
    assert body["generated_files"] == ["main.tf"]
    assert body["validation"]["valid"] is True
    assert body["download"] == f"/api/download/{valid_generate_payload['project_name']}"


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
    def raise_ai_error(prompt):
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


def test_download_returns_zip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "my-project.zip").write_bytes(b"PK\x03\x04fake-zip")

    response = client.get("/api/download/my-project")

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04fake-zip"
    assert response.headers["content-type"] == "application/zip"


def test_download_missing_project_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "generated").mkdir()

    response = client.get("/api/download/does-not-exist")

    assert response.status_code == 404


def test_download_rejects_invalid_project_name():
    response = client.get("/api/download/invalid%20name")

    assert response.status_code == 422
