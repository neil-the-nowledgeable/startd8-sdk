"""R2-S2 — hardcoded-port detection (rescue a model that ignores the injected $PORT).

The harness injects an ephemeral $PORT; a model that hardcodes its listen port would otherwise
false-degrade (readiness probes the wrong port). The detector reads the generated source and probes
the hardcoded port instead — but only when the source does NOT read the PORT env (so a well-behaved
model is never demoted). These are pure unit tests over the detector.
"""
from __future__ import annotations

from startd8.benchmark_matrix.behavioral.execute import _detect_effective_port

INJECTED = 54321


def _write(tmp_path, name, src):
    (tmp_path / name).write_text(src, encoding="utf-8")
    return [name]


def test_env_port_keeps_injected(tmp_path):
    tfs = _write(tmp_path, "server.js", "const port = process.env.PORT || 8080;\nserver.listen(port);")
    assert _detect_effective_port(tmp_path, tfs, INJECTED) == (INJECTED, "injected")


def test_env_port_python_keeps_injected(tmp_path):
    tfs = _write(tmp_path, "server.py", "import os\nport = int(os.environ['PORT'])\n")
    assert _detect_effective_port(tmp_path, tfs, INJECTED) == (INJECTED, "injected")


def test_hardcoded_listen_overrides(tmp_path):
    tfs = _write(tmp_path, "server.js", "const app = express();\napp.listen(8080);\n")
    assert _detect_effective_port(tmp_path, tfs, INJECTED) == (8080, "hardcoded:8080")


def test_hardcoded_grpc_bind_string_overrides(tmp_path):
    tfs = _write(tmp_path, "server.js", 'server.bindAsync("0.0.0.0:50051", creds, cb);\n')
    assert _detect_effective_port(tmp_path, tfs, INJECTED) == (50051, "hardcoded:50051")


def test_no_source_falls_back_to_injected(tmp_path):
    # missing file → can't read → injected (today's behavior; never worse)
    assert _detect_effective_port(tmp_path, ["nope.js"], INJECTED) == (INJECTED, "injected")


def test_detected_equals_injected_is_not_flagged(tmp_path):
    tfs = _write(tmp_path, "server.js", f"app.listen({INJECTED});\n")
    assert _detect_effective_port(tmp_path, tfs, INJECTED) == (INJECTED, "injected")
