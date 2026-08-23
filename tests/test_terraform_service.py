import os

import pytest

from backend.exceptions.api_exception import ApiException
from backend.services.terraform_service import TerraformService


@pytest.fixture(autouse=True)
def isolated_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def service():
    return TerraformService()


def test_save_writes_files(service):
    project_path = service.save(
        "my-project",
        {"main.tf": "resource \"aws_vpc\" \"main\" {}"}
    )

    assert project_path == "generated/my-project"
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
