import pytest

from app import config, storage


def test_upload_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "S3_ENABLED", False)

    result = storage.upload_result(
        str(tmp_path / "result.json"),
        "test123",
    )

    assert result is None


def test_upload_requires_bucket(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "S3_ENABLED", True)
    monkeypatch.setattr(config, "S3_BUCKET", "")

    result_file = tmp_path / "result.json"
    result_file.write_text('{"status": "success"}')

    with pytest.raises(ValueError, match="S3_BUCKET"):
        storage.upload_result(str(result_file), "test123")


def test_upload_file_not_found(monkeypatch):
    monkeypatch.setattr(config, "S3_ENABLED", True)
    monkeypatch.setattr(config, "S3_BUCKET", "test-bucket")

    with pytest.raises(FileNotFoundError):
        storage.upload_result("missing.json", "test123")


def test_successful_s3_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "S3_ENABLED", True)
    monkeypatch.setattr(config, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(config, "AWS_REGION", "ap-south-1")

    result_file = tmp_path / "result.json"
    result_file.write_text('{"status": "success"}', encoding="utf-8")

    uploaded = {}

    class FakeS3:
        def upload_file(self, filename, bucket, key, ExtraArgs):
            uploaded["filename"] = filename
            uploaded["bucket"] = bucket
            uploaded["key"] = key
            uploaded["extra_args"] = ExtraArgs

    def fake_client(service, region_name):
        assert service == "s3"
        assert region_name == "ap-south-1"
        return FakeS3()

    monkeypatch.setattr(storage.boto3, "client", fake_client)

    result = storage.upload_result(str(result_file), "test123")

    assert result == "s3://test-bucket/crawl-results/test123.json"
    assert uploaded["bucket"] == "test-bucket"
    assert uploaded["key"] == "crawl-results/test123.json"
    assert uploaded["extra_args"]["ContentType"] == "application/json"
    assert uploaded["extra_args"]["ServerSideEncryption"] == "AES256"