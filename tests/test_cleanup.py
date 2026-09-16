import os

import pytest

from backend.config import settings
from backend.utils.cleanup import purge_expired_generations

OLD = "a" * 32
FRESH = "b" * 32
NOW = 1_000_000_000


@pytest.fixture
def generated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GENERATED_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "GENERATION_TTL_SECONDS", 3600)
    return tmp_path


def _make(root, name, age):
    path = root / name
    (path / "project").mkdir(parents=True)
    os.utime(path, (NOW - age, NOW - age))
    return path


def test_expired_generations_are_removed(generated):
    _make(generated, OLD, age=7200)
    _make(generated, FRESH, age=60)

    assert purge_expired_generations(now=NOW) == 1
    assert not (generated / OLD).exists()
    assert (generated / FRESH).exists()


def test_directories_that_are_not_generations_are_left_alone(generated):
    _make(generated, "my-old-project", age=10 ** 6)

    assert purge_expired_generations(now=NOW) == 0
    assert (generated / "my-old-project").exists()


def test_a_missing_generated_dir_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GENERATED_DIR", str(tmp_path / "absent"))

    assert purge_expired_generations(now=NOW) == 0
