"""Tests for the TODO scanner (REQ-TCW-100–103)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from startd8.validators.todo_scanner import (
    TodoEntry,
    TodoInventory,
    classify_todo,
    normalize_instrumentation_data,
    scan_directory,
    scan_file,
    scan_todos,
    uncomment_block,
)


# ---------------------------------------------------------------------------
# Fixtures: Java source files with various TODO patterns
# ---------------------------------------------------------------------------

JAVA_GRPC_SERVER = textwrap.dedent("""\
    package hipstershop;

    import io.grpc.Server;
    import io.grpc.ServerBuilder;

    public class AdService {

        private static final int PORT = 9555;

        public static void main(String[] args) throws Exception {
            AdService service = new AdService();
            service.start();
        }

        private void start() throws Exception {
            // initStats();  // TODO: uncomment when OTel SDK is added
            // initTracing();  // TODO: uncomment when OTel SDK is added
            Server server = ServerBuilder.forPort(PORT)
                .addService(new AdServiceImpl())
                .build();
            server.start();
        }

        private void initStats() {
            // TODO: implement metrics initialization
        }

        private void initTracing() {
            // TODO: implement tracing initialization
        }
    }
""")

JAVA_WITH_COMMENTED_BLOCK = textwrap.dedent("""\
    package hipstershop;

    public class ProfilerSetup {
        // TODO: uncomment profiler setup
        // import com.google.cloud.profiler.Agent;
        // Agent.init();
        // Agent.setProperty("service_name", "adservice");
        // Agent.start();

        public void run() {
            System.out.println("running");
        }
    }
""")

GO_SOURCE = textwrap.dedent("""\
    package main

    import "fmt"

    func initStats() {
        // TODO: implement stats initialization
    }

    func initTracing() {
        // TODO: implement tracing
    }

    func main() {
        fmt.Println("hello")
    }
""")

PYTHON_SOURCE = textwrap.dedent("""\
    import logging

    logger = logging.getLogger(__name__)

    def setup_metrics():
        # TODO: implement metrics setup
        pass

    def setup_tracing():
        # TODO: implement tracing setup
        pass

    def main():
        logger.info("Starting service")
""")

DOCKERFILE_WITH_COMMENTS = textwrap.dedent("""\
    FROM golang:1.21 AS builder
    WORKDIR /app
    COPY . .
    RUN go build -o server .

    FROM gcr.io/distroless/base
    COPY --from=builder /app/server /server

    # TODO: uncomment profiler download
    # RUN wget -q -O /tmp/profiler.tar.gz \\
    #     https://storage.googleapis.com/cloud-profiler/java/latest/profiler.tar.gz
    # RUN tar xzf /tmp/profiler.tar.gz -C /opt

    CMD ["/server"]
""")


# ---------------------------------------------------------------------------
# Test: scan_todos — raw detection
# ---------------------------------------------------------------------------

class TestScanTodos:
    """REQ-TCW-100: detect TODO markers."""

    def test_java_todo_detection(self):
        entries = scan_todos("AdService.java", JAVA_GRPC_SERVER, "java")
        assert len(entries) >= 4  # 2 in start(), 2 in stub methods

    def test_go_todo_detection(self):
        entries = scan_todos("main.go", GO_SOURCE, "go")
        assert len(entries) == 2

    def test_python_todo_detection(self):
        entries = scan_todos("server.py", PYTHON_SOURCE, "python")
        assert len(entries) == 2

    def test_dockerfile_todo_detection(self):
        entries = scan_todos("Dockerfile", DOCKERFILE_WITH_COMMENTS, "dockerfile")
        assert len(entries) >= 1

    def test_line_numbers_correct(self):
        entries = scan_todos("main.go", GO_SOURCE, "go")
        # First TODO should be in initStats (line 6)
        assert entries[0].line == 6

    def test_context_lines_populated(self):
        entries = scan_todos("main.go", GO_SOURCE, "go")
        assert entries[0].context_lines  # not empty

    def test_containing_function_detected(self):
        entries = scan_todos("main.go", GO_SOURCE, "go")
        assert entries[0].containing_function == "initStats"
        assert entries[1].containing_function == "initTracing"

    def test_java_containing_function(self):
        entries = scan_todos("AdService.java", JAVA_GRPC_SERVER, "java")
        fn_names = {e.containing_function for e in entries}
        assert "initStats" in fn_names
        assert "initTracing" in fn_names

    def test_all_default_to_category_c(self):
        entries = scan_todos("main.go", GO_SOURCE, "go")
        assert all(e.category == "C" for e in entries)

    def test_case_insensitive_todo(self):
        source = "// todo: fix this\n// TODO: fix that\n// Todo: one more\n"
        entries = scan_todos("test.java", source, "java")
        assert len(entries) == 3

    def test_fixme_detected(self):
        source = "// FIXME: broken\n"
        entries = scan_todos("test.java", source, "java")
        assert len(entries) == 1

    def test_at_todo_detected(self):
        source = "// @TODO: implement this\n"
        entries = scan_todos("test.java", source, "java")
        assert len(entries) == 1

    def test_python_hash_comment(self):
        source = "# TODO: implement this\n"
        entries = scan_todos("test.py", source, "python")
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Test: classify_todo — A/B/C classification
# ---------------------------------------------------------------------------

class TestClassifyTodo:
    """REQ-TCW-101: classify into A/B/C categories."""

    def test_category_a_commented_out_block(self):
        """Category A: TODO adjacent to commented-out code block."""
        lines = JAVA_WITH_COMMENTED_BLOCK.splitlines()
        entries = scan_todos("ProfilerSetup.java", JAVA_WITH_COMMENTED_BLOCK, "java")
        assert len(entries) >= 1

        classified = classify_todo(entries[0], lines)
        assert classified.category == "A"
        assert "commented-out code block" in classified.rationale

    def test_category_b_instrumentation_stub(self):
        """Category B: TODO in stub method with instrumentation vocabulary."""
        lines = JAVA_GRPC_SERVER.splitlines()
        entries = scan_todos("AdService.java", JAVA_GRPC_SERVER, "java")

        # Find the initStats TODO
        init_stats_entries = [
            e for e in entries
            if e.containing_function == "initStats"
            and "implement" in e.raw_text.lower()
        ]
        assert len(init_stats_entries) >= 1

        classified = classify_todo(init_stats_entries[0], lines)
        assert classified.category == "B"
        assert "instrumentation vocabulary" in classified.rationale.lower() or "stub" in classified.rationale.lower()

    def test_category_b_with_contract(self):
        """Category B with instrumentation contract → higher confidence."""
        lines = JAVA_GRPC_SERVER.splitlines()
        entries = scan_todos("AdService.java", JAVA_GRPC_SERVER, "java")
        init_stats = [e for e in entries if e.containing_function == "initStats" and "implement" in e.raw_text.lower()]
        assert len(init_stats) >= 1

        contract = {
            "metrics": {
                "required": [
                    {"name": "rpc_server_duration_seconds", "type": "histogram"},
                ],
            },
            "traces": {"required": []},
        }
        classified = classify_todo(init_stats[0], lines, contract)
        assert classified.category == "B"
        assert classified.confidence >= 0.9
        assert "metrics.required" in classified.contract_fields

    def test_category_c_default(self):
        """Category C: generic TODO with no special context."""
        source = textwrap.dedent("""\
            public class Foo {
                public void doSomething() {
                    int x = 42;
                    // TODO: add validation
                    return;
                }
            }
        """)
        lines = source.splitlines()
        entries = scan_todos("Foo.java", source, "java")
        assert len(entries) == 1
        classified = classify_todo(entries[0], lines)
        assert classified.category == "C"

    def test_category_a_dockerfile_profiler(self):
        """Category A in Dockerfile: commented-out RUN commands."""
        lines = DOCKERFILE_WITH_COMMENTS.splitlines()
        entries = scan_todos("Dockerfile", DOCKERFILE_WITH_COMMENTS, "dockerfile")
        assert len(entries) >= 1

        classified = classify_todo(entries[0], lines)
        assert classified.category == "A"

    def test_go_instrumentation_stub(self):
        """Category B in Go: initStats/initTracing stubs."""
        lines = GO_SOURCE.splitlines()
        entries = scan_todos("main.go", GO_SOURCE, "go")

        init_stats = [e for e in entries if e.containing_function == "initStats"]
        assert len(init_stats) == 1

        classified = classify_todo(init_stats[0], lines)
        assert classified.category == "B"

    def test_python_instrumentation_stub(self):
        """Category B in Python: setup_metrics/setup_tracing stubs."""
        lines = PYTHON_SOURCE.splitlines()
        entries = scan_todos("server.py", PYTHON_SOURCE, "python")

        metrics = [e for e in entries if e.containing_function == "setup_metrics"]
        assert len(metrics) == 1

        classified = classify_todo(metrics[0], lines)
        assert classified.category == "B"


# ---------------------------------------------------------------------------
# Test: TodoInventory
# ---------------------------------------------------------------------------

class TestTodoInventory:
    """REQ-TCW-103: inventory persistence."""

    def test_compute_summary(self):
        entries = [
            TodoEntry("f1.java", 1, "java", "// TODO", "A", "", "", confidence=0.9, rationale="block"),
            TodoEntry("f2.java", 2, "java", "// TODO", "B", "", "", confidence=0.8, rationale="stub"),
            TodoEntry("f3.java", 3, "java", "// TODO", "C", "", "", confidence=1.0, rationale=""),
        ]
        inv = TodoInventory(entries=entries)
        inv.compute_summary()
        assert inv.summary == {"A": 1, "B": 1, "C": 1, "total": 3, "security_todos": 0}

    def test_save_and_load(self, tmp_path):
        entries = [
            TodoEntry("f.java", 10, "java", "// TODO: fix", "C", "context", "main"),
        ]
        inv = TodoInventory(entries=entries)
        path = tmp_path / "todo-inventory.json"
        inv.save(path)

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["summary"]["total"] == 1
        assert loaded["entries"][0]["line"] == 10
        assert "id" in loaded["entries"][0]

    def test_todo_entry_id_stable(self):
        e1 = TodoEntry("f.java", 10, "java", "// TODO", "C", "", "")
        e2 = TodoEntry("f.java", 10, "java", "// TODO: different", "C", "", "")
        assert e1.id == e2.id  # same file + line = same ID


# ---------------------------------------------------------------------------
# Test: scan_file integration
# ---------------------------------------------------------------------------

class TestNormalizeInstrumentationData:
    """Cross-repo key name alignment: ContextCore hints → StartD8 contract."""

    def test_none_passthrough(self):
        assert normalize_instrumentation_data(None) is None

    def test_empty_dict_passthrough(self):
        assert normalize_instrumentation_data({}) == {}

    def test_already_normalized_passthrough(self):
        """StartD8 schema with metrics.required — returned unchanged."""
        contract = {
            "metrics": {
                "required": [{"name": "rpc_server_duration_seconds"}],
            },
        }
        result = normalize_instrumentation_data(contract)
        assert result["metrics"]["required"] == contract["metrics"]["required"]

    def test_contextcore_convention_based_normalized(self):
        """ContextCore schema with convention_based → creates metrics.required."""
        hints = {
            "metrics": {
                "convention_based": [
                    {"name": "rpc.server.duration", "type": "histogram"},
                    {"name": "rpc.server.request.size", "type": "histogram"},
                ],
                "manifest_declared": [
                    {"name": "custom_metric", "source": "semantic_conventions"},
                ],
            },
        }
        result = normalize_instrumentation_data(hints)
        assert "required" in result["metrics"]
        assert len(result["metrics"]["required"]) == 3
        # Originals preserved
        assert result["metrics"]["convention_based"] == hints["metrics"]["convention_based"]

    def test_contextcore_no_metrics_passthrough(self):
        hints = {"traces": {"required": [{"span_name": "test"}]}}
        result = normalize_instrumentation_data(hints)
        assert result == hints

    def test_does_not_mutate_input(self):
        """Normalization must not mutate the original dict."""
        hints = {
            "metrics": {
                "convention_based": [{"name": "m1"}],
            },
        }
        original_metrics = dict(hints["metrics"])
        normalize_instrumentation_data(hints)
        assert hints["metrics"] == original_metrics
        assert "required" not in hints["metrics"]

    def test_category_b_with_contextcore_hints(self):
        """End-to-end: ContextCore hints schema triggers Category B classification."""
        lines = JAVA_GRPC_SERVER.splitlines()
        entries = scan_todos("AdService.java", JAVA_GRPC_SERVER, "java")
        init_stats = [e for e in entries if e.containing_function == "initStats" and "implement" in e.raw_text.lower()]
        assert len(init_stats) >= 1

        # Use ContextCore's schema (convention_based, not required)
        hints = {
            "metrics": {
                "convention_based": [
                    {"name": "rpc.server.duration", "type": "histogram"},
                ],
            },
            "traces": {"required": []},
        }
        # normalize_instrumentation_data bridges the gap
        normalized = normalize_instrumentation_data(hints)
        classified = classify_todo(init_stats[0], lines, normalized)
        assert classified.category == "B"
        assert classified.confidence >= 0.9
        assert "metrics.required" in classified.contract_fields

    def test_scan_file_with_contextcore_hints(self, tmp_path):
        """scan_file auto-normalizes ContextCore hints."""
        java_file = tmp_path / "AdService.java"
        java_file.write_text(JAVA_GRPC_SERVER, encoding="utf-8")

        hints = {
            "metrics": {
                "convention_based": [
                    {"name": "rpc.server.duration", "type": "histogram"},
                ],
            },
            "traces": {"required": []},
        }
        entries = scan_file(java_file, instrumentation_contract=hints)
        b_entries = [e for e in entries if e.category == "B" and e.contract_fields]
        assert len(b_entries) >= 1


class TestScanFile:
    """Integration: scan_file reads from disk and classifies."""

    def test_scan_java_file(self, tmp_path):
        java_file = tmp_path / "AdService.java"
        java_file.write_text(JAVA_GRPC_SERVER, encoding="utf-8")

        entries = scan_file(java_file)
        categories = {e.category for e in entries}
        assert "B" in categories  # initStats/initTracing are Category B

    def test_scan_nonexistent_file(self, tmp_path):
        entries = scan_file(tmp_path / "nope.java")
        assert entries == []

    def test_scan_directory_integration(self, tmp_path):
        # Create a few files
        (tmp_path / "Server.java").write_text(JAVA_GRPC_SERVER, encoding="utf-8")
        (tmp_path / "main.go").write_text(GO_SOURCE, encoding="utf-8")

        inventory = scan_directory(tmp_path)
        assert inventory.summary["total"] >= 4  # at least 4 TODOs across files


# ---------------------------------------------------------------------------
# Test: uncomment_block (REQ-TCW-253)
# ---------------------------------------------------------------------------

class TestUncommentBlock:
    """REQ-TCW-253: shared uncomment utility."""

    def test_python_uncomment(self):
        code = (
            "def setup():\n"
            "    # TODO: uncomment\n"
            "    # import otel\n"
            "    # metrics = otel.get_metrics()\n"
            "    # metrics.init()\n"
            "    pass\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 1
        assert "import otel" in result
        assert "# TODO" not in result

    def test_go_uncomment(self):
        code = (
            "func initMetrics() {\n"
            "    // TODO: uncomment\n"
            "    // stats := otel.NewProvider()\n"
            "    // stats.RegisterCallback(f)\n"
            "    // stats.Start()\n"
            "}\n"
        )
        result, count = uncomment_block(code, language="go")
        assert count == 1
        assert "stats := otel.NewProvider()" in result

    def test_no_op_when_no_blocks(self):
        code = "def foo():\n    pass\n"
        result, count = uncomment_block(code)
        assert count == 0
        assert result == code


# ---------------------------------------------------------------------------
# Test: comment_block structured field (REQ-TCW-301)
# ---------------------------------------------------------------------------

class TestCommentBlockField:
    """REQ-TCW-301: classify_todo populates comment_block for Cat A."""

    def test_category_a_has_comment_block(self):
        source = textwrap.dedent("""\
            # TODO: enable
            # import otel
            # meter = otel.get_meter()
            # meter.start()
            pass
        """)
        lines = source.splitlines()
        entries = scan_todos("test.py", source, "python")
        assert len(entries) >= 1
        classified = classify_todo(entries[0], lines)
        assert classified.category == "A"
        assert classified.comment_block is not None
        assert "start_line" in classified.comment_block
        assert "end_line" in classified.comment_block
        assert "content_lines" in classified.comment_block
        assert len(classified.comment_block["content_lines"]) >= 3

    def test_category_b_has_no_comment_block(self):
        """Category B should not have comment_block."""
        source = textwrap.dedent("""\
            def initMetrics():
                # TODO: implement metrics
                pass
        """)
        lines = source.splitlines()
        entries = scan_todos("test.py", source, "python")
        assert len(entries) >= 1
        classified = classify_todo(entries[0], lines)
        # This is either B or C — either way, no comment_block
        assert classified.comment_block is None


# ---------------------------------------------------------------------------
# Test: scan_directory deduplication (REQ-TCW-308)
# ---------------------------------------------------------------------------

class TestScanDirectoryDedup:
    """REQ-TCW-308: deduplicate TODOs across generated/ and src/ copies."""

    def test_dedup_same_file_different_paths(self, tmp_path):
        """Same file in src/ and generated/ — generated/ preferred."""
        src = tmp_path / "src"
        src.mkdir()
        gen = tmp_path / "generated"
        gen.mkdir()

        content = textwrap.dedent("""\
            def initMetrics():
                # TODO: implement metrics
                pass
        """)
        (src / "service.py").write_text(content, encoding="utf-8")
        (gen / "service.py").write_text(content, encoding="utf-8")

        inventory = scan_directory(tmp_path)
        # Only one entry for this TODO (deduplicated)
        todo_entries = [
            e for e in inventory.entries
            if "implement metrics" in e.raw_text
        ]
        assert len(todo_entries) == 1
        assert "generated" in todo_entries[0].file_path

    def test_excludes_stale_run_dirs(self, tmp_path):
        """Stale prior-run directories matching /run-NNN-/ are excluded."""
        stale = tmp_path / "run-042-online-boutique"
        stale.mkdir()
        content = textwrap.dedent("""\
            def initStats():
                # TODO: implement stats
                pass
        """)
        (stale / "service.py").write_text(content, encoding="utf-8")

        inventory = scan_directory(tmp_path)
        assert len(inventory.entries) == 0


class TestCurrentRunDirNotSelfExcluded:
    """Regression: scan_directory must not exclude the current run's own dir.

    All pipeline output is namespaced under run-NNN-TIMESTAMP/, so when
    _run_todo_scan_and_inject() scans <...>/run-107-.../generated/, the
    /run-NNN-/ filter previously excluded 100% of files → zero TODOs found.
    """

    def test_scans_files_under_current_run_dir(self, tmp_path):
        gen = tmp_path / "run-107-online-boutique" / "plan-ingestion" / "generated"
        gen.mkdir(parents=True)
        content = textwrap.dedent("""\
            def initStats():
                # TODO: implement stats
                pass
        """)
        (gen / "service.py").write_text(content, encoding="utf-8")

        inventory = scan_directory(gen)
        todos = [e for e in inventory.entries if "implement stats" in e.raw_text]
        assert len(todos) == 1, "current run's own files must not be self-excluded"

    def test_sibling_runs_still_excluded_from_broad_root(self, tmp_path):
        """Root NOT under a run dir → nested run-NNN- siblings still excluded."""
        stale = tmp_path / "run-042-old"
        stale.mkdir()
        (stale / "svc.py").write_text(
            "def initStats():\n    # TODO: implement stats\n    pass\n",
            encoding="utf-8",
        )
        inventory = scan_directory(tmp_path)
        assert len(inventory.entries) == 0


class TestJavaInitMethodClassification:
    """Regression: Java instrumentation-init stubs must classify as B, not C.

    The reference AdService keeps a guard clause + logging + dead variables in
    initStats()/initTracing(), which dropped the stub ratio below 0.5 so the
    "Implement OpenTelemetry X" TODO fell through to Category C and was dropped
    by the A/B-only injection filter — identical Go TODOs classified as B.
    """

    def test_java_init_method_with_boilerplate_is_category_b(self):
        src = textwrap.dedent("""\
            class AdService {
              private static void initStats() {
                if (System.getenv("DISABLE_STATS") != null) {
                  logger.info("Stats disabled.");
                  return;
                }
                logger.info("Stats enabled, but temporarily unavailable");
                long sleepTime = 10;
                int maxAttempts = 5;
                // TODO(arbrown) Implement OpenTelemetry stats
              }
            }
        """)
        lines = src.splitlines()
        entries = scan_todos("AdService.java", src, "java")
        impl = [e for e in entries if "Implement OpenTelemetry" in e.raw_text]
        assert impl, "TODO should be detected"
        classified = classify_todo(impl[0], lines)
        assert classified.category == "B"

    def test_non_init_method_instrumentation_todo_stays_c(self):
        """Guard: the override is scoped to init/setup methods only.

        A non-init method with a substantive (non-stub) body keeps Category C
        even when its TODO carries instrumentation vocabulary — the override
        must not promote arbitrary methods.
        """
        src = textwrap.dedent("""\
            class Foo {
              private void handleRequest() {
                validate(input);
                var r = lookup(id);
                persist(r);
                // TODO(arbrown) Implement OpenTelemetry stats
                notify(r);
                audit(r);
              }
            }
        """)
        lines = src.splitlines()
        entries = scan_todos("Foo.java", src, "java")
        todo = [e for e in entries if "Implement OpenTelemetry" in e.raw_text]
        assert todo
        classified = classify_todo(todo[0], lines)
        assert classified.category == "C"
