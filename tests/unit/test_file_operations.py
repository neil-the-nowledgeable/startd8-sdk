import json
from dataclasses import dataclass
from pathlib import Path

from startd8.utils.file_operations import atomic_write_json


@dataclass
class _ExampleDataclass:
    key: str
    value: int


class _KeyResultLike:
    def __init__(self, metric: str, target: str):
        self.metric = metric
        self.target = target


def test_atomic_write_json_serializes_nested_custom_objects(tmp_path: Path):
    out = tmp_path / "data.json"
    payload = {
        "objectives": [
            {
                "name": "Ship feature serial",
                "key_results": [_KeyResultLike("latency_p95", "<=250ms")],
            }
        ],
        "meta": _ExampleDataclass(key="attempt", value=1),
    }

    atomic_write_json(out, payload, indent=2)

    data = json.loads(out.read_text())
    assert data["objectives"][0]["key_results"][0]["metric"] == "latency_p95"
    assert data["meta"] == {"key": "attempt", "value": 1}


def test_atomic_write_json_uses_user_default_then_fallback(tmp_path: Path):
    out = tmp_path / "data.json"

    class _Custom:
        def __init__(self, value: str):
            self.value = value

    def _user_default(value):
        if isinstance(value, Path):
            return f"path:{value.name}"
        raise TypeError

    payload = {
        "path": Path("/tmp/some-file.txt"),
        "custom": _Custom("ok"),
    }
    atomic_write_json(out, payload, default=_user_default)

    data = json.loads(out.read_text())
    assert data["path"] == "path:some-file.txt"
    assert data["custom"] == {"value": "ok"}
