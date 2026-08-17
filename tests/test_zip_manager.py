import zipfile

from backend.utils.zip_manager import create_zip


def test_create_zip_includes_project_files(tmp_path):
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    (project_dir / "main.tf").write_text("resource \"aws_vpc\" \"main\" {}")
    (project_dir / "README.md").write_text("# hello")

    zip_path = create_zip(str(project_dir))

    assert zip_path == f"{project_dir}.zip"

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    assert names == {"main.tf", "README.md"}


def test_create_zip_excludes_terraform_artifacts(tmp_path):
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    (project_dir / "main.tf").write_text("resource \"aws_vpc\" \"main\" {}")
    (project_dir / ".terraform.lock.hcl").write_text("lock contents")

    tf_dir = project_dir / ".terraform" / "providers" / "hashicorp" / "aws"
    tf_dir.mkdir(parents=True)
    (tf_dir / "terraform-provider-aws").write_bytes(b"\x00" * 1024)

    zip_path = create_zip(str(project_dir))

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    assert names == ["main.tf"]
    assert not any(".terraform" in name for name in names)
