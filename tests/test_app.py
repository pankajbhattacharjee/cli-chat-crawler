import json

from app import config
from app.main import load_result
from app.security import redact


def test_load_result_missing_file(tmp_path):
    data, problem = load_result(str(tmp_path / "nope.json"))
    assert data is None and "no result file" in problem


def test_load_result_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    data, problem = load_result(str(bad))
    assert data is None and "not valid JSON" in problem


def test_load_result_missing_keys(tmp_path):
    partial = tmp_path / "p.json"
    partial.write_text(json.dumps({"task": "x"}))
    data, problem = load_result(str(partial))
    assert data is None and "missing fields" in problem


def test_load_result_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_OUTPUT_BYTES", 10)
    f = tmp_path / "big.json"
    f.write_text("x" * 100)
    data, problem = load_result(str(f))
    assert data is None and "too large" in problem


def test_redact_masks_env_secret_and_key_patterns(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "supersecretvalue123")
    out = redact("leak supersecretvalue123 and sk-ant-abcdefgh12345")
    assert "supersecretvalue123" not in out
    assert "sk-ant-" not in out