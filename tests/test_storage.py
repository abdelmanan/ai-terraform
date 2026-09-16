import pytest
from botocore.exceptions import ClientError

from backend.config import settings
from backend.utils import storage
from backend.utils.storage import StorageError, publish_archive

GID = "0123456789abcdef0123456789abcdef"


class FakeS3Client:

    def __init__(self, fail=False):
        self.fail = fail
        self.uploads = []
        self.presign_params = None

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        if self.fail:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "PutObject")
        self.uploads.append((filename, bucket, key, ExtraArgs))

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.presign_params = (operation, Params, ExpiresIn)
        return f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}?sig=x"


@pytest.fixture
def s3(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr(settings, "S3_BUCKET", "my-bucket")
    monkeypatch.setattr(settings, "S3_PREFIX", "generated/")
    monkeypatch.setattr(storage.boto3, "client", lambda service, region_name=None: client)
    return client


def test_without_bucket_the_archive_is_served_by_the_api(monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET", None)

    assert publish_archive("/tmp/x.zip", GID, "my-project") == f"/api/download/{GID}"


def test_with_bucket_the_archive_is_uploaded_under_its_generation_id(s3):
    url = publish_archive("/tmp/x.zip", GID, "my-project")

    filename, bucket, key, extra = s3.uploads[0]

    assert (filename, bucket) == ("/tmp/x.zip", "my-bucket")
    assert key == f"generated/{GID}/my-project.zip"
    assert extra == {"ContentType": "application/zip"}
    assert url.startswith("https://my-bucket.s3.amazonaws.com/")


def test_presigned_url_expires_and_keeps_the_project_file_name(s3):
    publish_archive("/tmp/x.zip", GID, "my-project")

    operation, params, expires = s3.presign_params

    assert operation == "get_object"
    assert expires == settings.DOWNLOAD_URL_TTL_SECONDS
    assert params["ResponseContentDisposition"] == 'attachment; filename="my-project.zip"'


def test_an_s3_failure_is_reported_as_a_storage_error(s3):
    s3.fail = True

    with pytest.raises(StorageError):
        publish_archive("/tmp/x.zip", GID, "my-project")


def test_a_bucket_without_boto3_is_a_storage_error(monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "my-bucket")
    monkeypatch.setattr(storage, "boto3", None)

    with pytest.raises(StorageError):
        publish_archive("/tmp/x.zip", GID, "my-project")
