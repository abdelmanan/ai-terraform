import os

import pytest

from backend.config import settings
from backend.exceptions.api_exception import ApiException
from backend.services.terraform_service import TerraformService


@pytest.fixture(autouse=True)
def generated_dir(monkeypatch, tmp_path):
    target = tmp_path / "generated"
    monkeypatch.setattr(settings, "GENERATED_DIR", str(target))
    return target


@pytest.fixture
def service():
    return TerraformService()


def test_save_writes_files(service, generated_dir):
    project_path = service.save(
        "my-project",
        {"main.tf": "resource \"aws_vpc\" \"main\" {}"}
    )

    assert project_path == str(generated_dir / "my-project")
    with open(os.path.join(project_path, "main.tf")) as f:
        assert f.read() == "resource \"aws_vpc\" \"main\" {}"


def test_save_removes_stale_files_from_previous_generation(service):
    service.save(
        "my-project",
        {
            "main.tf": "old main",
            "orphan.tf": "leftover from a previous, different generation",
        }
    )

    project_path = service.save("my-project", {"main.tf": "new main"})

    assert set(os.listdir(project_path)) == {"main.tf"}
    assert not os.path.exists(os.path.join(project_path, "orphan.tf"))

    with open(os.path.join(project_path, "main.tf")) as f:
        assert f.read() == "new main"


def test_save_rejects_path_traversal(service):
    with pytest.raises(ApiException) as exc_info:
        service.save("evil-project", {"../../evil.py": "malicious"})

    assert exc_info.value.status_code == 502


def test_save_is_independent_of_the_current_working_directory(
    service, generated_dir, monkeypatch, tmp_path
):
    # uvicorn may be started from anywhere (systemd, docker, another shell):
    # the project must still land under settings.GENERATED_DIR.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    project_path = service.save("my-project", {"main.tf": "resource {}"})

    assert os.path.isabs(project_path)
    assert project_path == str(generated_dir / "my-project")
    assert (generated_dir / "my-project" / "main.tf").is_file()
    assert not (elsewhere / "generated").exists()
