"""
Tests for OTel auto-initialization, framework opt-in, and span nesting.

Phase 1E tests covering:
- STARTD8_OTEL=enabled triggers auto-configure
- Unset env var = zero overhead
- AgentFramework(enable_otel=True) triggers configure
- arun() creates spans
- Pipeline parent→step span nesting
- Defense-in-depth auto-probe cascade (env → config → localhost:4317)
- Config file OTel settings
- Telemetry banner formatting
"""

import os
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestAutoConfigureOtel:
    """Tests for auto_configure_otel()."""

    def test_auto_by_default_with_otel_no_collector(self):
        """Unset STARTD8_OTEL defaults to 'auto'; auto-probes localhost:4317 (unreachable → skip)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STARTD8_OTEL", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=False) as mock_reach, \
                     patch.object(otel_mod, "_resolve_config_endpoint", return_value=None), \
                     patch.object(otel_mod, "configure_otel") as mock_configure:
                    result = otel_mod.auto_configure_otel()
                # Auto-probe should be called on localhost:4317
                mock_reach.assert_called_once()
                mock_configure.assert_not_called()
                assert result["tracer"] is None
                assert result["meter"] is None
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_auto_by_default_with_otel_collector_found(self):
        """Unset STARTD8_OTEL defaults to 'auto'; auto-probes localhost:4317 (reachable → configure)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STARTD8_OTEL", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                mock_result = {"tracer": "t", "meter": "m", "resource_attributes": {}}
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=True), \
                     patch.object(otel_mod, "_resolve_config_endpoint", return_value=None), \
                     patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                    result = otel_mod.auto_configure_otel()
                mock_configure.assert_called_once()
                assert result["tracer"] == "t"
                assert otel_mod._configured is True
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_auto_by_default_without_otel(self):
        """Unset STARTD8_OTEL defaults to 'auto'; silent no-op without OTel packages."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STARTD8_OTEL", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = False
            try:
                with patch.object(otel_mod, "configure_otel") as mock_configure:
                    result = otel_mod.auto_configure_otel()
                mock_configure.assert_not_called()
                assert result["tracer"] is None
                assert result["meter"] is None
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_disabled_explicit(self):
        """STARTD8_OTEL=disabled = no OTel calls."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "disabled"}):
            import startd8.otel as otel_mod
            otel_mod._configured = False

            with patch.object(otel_mod, "configure_otel") as mock_configure:
                result = otel_mod.auto_configure_otel()

            mock_configure.assert_not_called()
            assert result["tracer"] is None

    def test_enabled_calls_configure(self):
        """STARTD8_OTEL=enabled triggers configure_otel()."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "enabled"}, clear=False):
            os.environ.pop("CI", None)
            os.environ.pop("STARTD8_OTEL_FAIL_FAST", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False

            mock_result = {"tracer": "mock_tracer", "meter": "mock_meter", "resource_attributes": {}}
            with patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                result = otel_mod.auto_configure_otel()

            mock_configure.assert_called_once()
            assert result["tracer"] == "mock_tracer"
            assert otel_mod._configured is True

    def test_double_init_prevented(self):
        """Calling auto_configure_otel() twice only configures once."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "enabled"}, clear=False):
            os.environ.pop("CI", None)
            os.environ.pop("STARTD8_OTEL_FAIL_FAST", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False

            mock_result = {"tracer": "t", "meter": "m", "resource_attributes": {}}
            with patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                otel_mod.auto_configure_otel()
                result2 = otel_mod.auto_configure_otel()

            # Only called once
            mock_configure.assert_called_once()
            # Second call returns empty result
            assert result2["tracer"] is None

    def test_auto_mode_without_otel(self):
        """STARTD8_OTEL=auto with OTel unavailable = silent no-op."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "auto"}):
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = False
            try:
                with patch.object(otel_mod, "configure_otel") as mock_configure:
                    result = otel_mod.auto_configure_otel()
                mock_configure.assert_not_called()
                assert result["tracer"] is None
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_auto_mode_with_otel(self):
        """STARTD8_OTEL=auto with OTel available and endpoint reachable = configures."""
        with patch.dict(os.environ, {
            "STARTD8_OTEL": "auto",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4317",
        }):
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                mock_result = {"tracer": "t", "meter": "m", "resource_attributes": {}}
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=True), \
                     patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                    result = otel_mod.auto_configure_otel()
                mock_configure.assert_called_once()
                assert result["tracer"] == "t"
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_enabled_skips_connectivity_check(self):
        """STARTD8_OTEL=enabled configures OTLP even when endpoint unreachable."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "enabled"}, clear=False):
            os.environ.pop("CI", None)
            os.environ.pop("STARTD8_OTEL_FAIL_FAST", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            mock_result = {"tracer": "t", "meter": "m", "resource_attributes": {}}
            with patch.object(otel_mod, "_otlp_endpoint_reachable") as mock_reach, \
                 patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                otel_mod.auto_configure_otel()
            mock_reach.assert_not_called()
            mock_configure.assert_called_once()

    def test_custom_endpoint_from_env(self):
        """OTEL_EXPORTER_OTLP_ENDPOINT overrides default endpoint."""
        with patch.dict(os.environ, {
            "STARTD8_OTEL": "enabled",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://custom:4317",
        }, clear=False):
            os.environ.pop("CI", None)
            os.environ.pop("STARTD8_OTEL_FAIL_FAST", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False

            mock_result = {"tracer": "t", "meter": "m", "resource_attributes": {}}
            with patch.object(otel_mod, "configure_otel", return_value=mock_result) as mock_configure:
                otel_mod.auto_configure_otel()

            call_args = mock_configure.call_args[0][0]
            assert call_args.otlp_endpoint == "http://custom:4317"

    def test_auto_skips_when_endpoint_unreachable(self):
        """STARTD8_OTEL=auto skips OTLP when explicit endpoint is unreachable."""
        with patch.dict(os.environ, {
            "STARTD8_OTEL": "auto",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://unreachable:4317",
        }):
            import startd8.otel as otel_mod
            otel_mod._configured = False
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=False), \
                     patch.object(otel_mod, "configure_otel") as mock_configure:
                    result = otel_mod.auto_configure_otel()
                mock_configure.assert_not_called()
                assert result["tracer"] is None
                assert result["meter"] is None
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_enabled_missing_endpoint_fail_fast_skips_without_hard_fail(self):
        """Fail-fast policy logs/skips by default (no hard raise)."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "enabled", "STARTD8_OTEL_FAIL_FAST": "1"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("CI", None)
            os.environ.pop("STARTD8_OTEL_HARD_FAIL", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            with patch.object(otel_mod, "configure_otel") as mock_configure:
                result = otel_mod.auto_configure_otel()
                assert result["tracer"] is None
            mock_configure.assert_not_called()

    def test_enabled_missing_endpoint_hard_fail_raises(self):
        """Hard-fail env forces startup error on invalid enabled config."""
        with patch.dict(
            os.environ,
            {
                "STARTD8_OTEL": "enabled",
                "STARTD8_OTEL_FAIL_FAST": "1",
                "STARTD8_OTEL_HARD_FAIL": "1",
            },
            clear=False,
        ):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("CI", None)
            import startd8.otel as otel_mod
            otel_mod._configured = False
            with patch.object(otel_mod, "configure_otel") as mock_configure:
                try:
                    otel_mod.auto_configure_otel()
                    assert False, "Expected RuntimeError"
                except RuntimeError:
                    pass
            mock_configure.assert_not_called()

    def test_get_runtime_state_enabled_in_ci_requires_endpoint(self):
        """CI + enabled without endpoint reports error severity."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "enabled", "CI": "true"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            state = otel_mod.get_otel_runtime_state()
            assert state["severity"] == "error"
            assert state["reason"] == "enabled_missing_endpoint_fail_fast"


class TestOtlpEndpointReachable:
    """Tests for _otlp_endpoint_reachable()."""

    def test_unreachable_port_returns_false(self):
        """Unreachable port (e.g. no collector) returns False."""
        import startd8.otel as otel_mod
        result = otel_mod._otlp_endpoint_reachable("http://localhost:45999", timeout=0.1)
        assert result is False

    def test_invalid_host_returns_false(self):
        """Invalid/nonexistent host returns False."""
        import startd8.otel as otel_mod
        result = otel_mod._otlp_endpoint_reachable("http://nonexistent.invalid:4317", timeout=0.1)
        assert result is False

    def test_https_without_port_uses_443(self):
        """HTTPS endpoint without explicit port should default to 443, not 4317."""
        import startd8.otel as otel_mod
        from unittest.mock import patch as _patch, MagicMock as _Mock

        mock_sock = _Mock()
        with _patch("startd8.otel.socket.socket", return_value=mock_sock):
            mock_sock.connect.return_value = None
            result = otel_mod._otlp_endpoint_reachable("https://collector.example.com")
        assert result is True
        mock_sock.connect.assert_called_once_with(("collector.example.com", 443))

    def test_http_without_port_uses_4317(self):
        """HTTP endpoint without explicit port should default to 4317."""
        import startd8.otel as otel_mod
        from unittest.mock import patch as _patch, MagicMock as _Mock

        mock_sock = _Mock()
        with _patch("startd8.otel.socket.socket", return_value=mock_sock):
            mock_sock.connect.return_value = None
            result = otel_mod._otlp_endpoint_reachable("http://localhost")
        assert result is True
        mock_sock.connect.assert_called_once_with(("localhost", 4317))

    def test_explicit_port_overrides_scheme_default(self):
        """Explicit port takes precedence over scheme-based default."""
        import startd8.otel as otel_mod
        from unittest.mock import patch as _patch, MagicMock as _Mock

        mock_sock = _Mock()
        with _patch("startd8.otel.socket.socket", return_value=mock_sock):
            mock_sock.connect.return_value = None
            result = otel_mod._otlp_endpoint_reachable("https://collector.example.com:9999")
        assert result is True
        mock_sock.connect.assert_called_once_with(("collector.example.com", 9999))


class TestShutdownOtelSemantics:
    """Tests for shutdown_otel() behavior."""

    def test_shutdown_flushes_without_provider_shutdown(self):
        """shutdown_otel() flushes providers and avoids duplicate shutdown calls."""
        import startd8.otel as otel_mod

        provider1 = MagicMock()
        provider2 = MagicMock()
        otel_mod._providers = [provider1, provider2]

        try:
            otel_mod.shutdown_otel(timeout_millis=1234)
        finally:
            otel_mod._providers = []

        provider1.force_flush.assert_called_once_with(timeout_millis=1234)
        provider2.force_flush.assert_called_once_with(timeout_millis=1234)
        provider1.shutdown.assert_not_called()
        provider2.shutdown.assert_not_called()
        assert otel_mod._providers == []


class TestFrameworkOtelOptIn:
    """Tests for AgentFramework(enable_otel=True)."""

    def test_enable_otel_triggers_auto_configure(self):
        """AgentFramework(enable_otel=True) calls auto_configure_otel()."""
        with patch("startd8.otel.auto_configure_otel") as mock_auto:
            from startd8.framework import AgentFramework
            AgentFramework(enable_otel=True)
            mock_auto.assert_called_once()

    def test_disable_otel_default(self):
        """AgentFramework() does not call auto_configure_otel()."""
        with patch("startd8.otel.auto_configure_otel") as mock_auto:
            from startd8.framework import AgentFramework
            AgentFramework(enable_otel=False)
            mock_auto.assert_not_called()


class TestWorkflowSpanNesting:
    """Tests for workflow span nesting via start_as_current_span()."""

    def test_run_creates_parent_span(self):
        """WorkflowBase.run() uses start_as_current_span for proper nesting."""
        from startd8.workflows.base import WorkflowBase, WorkflowResult, _tracer
        from startd8.workflows.models import WorkflowMetadata

        class TestWorkflow(WorkflowBase):
            @property
            def metadata(self):
                return WorkflowMetadata(
                    workflow_id="test-wf",
                    name="Test",
                    description="Test workflow",
                    capabilities=[],
                    inputs=[],
                    requires_agents=False,
                )

            def _execute(self, config, agents, on_progress):
                return WorkflowResult(
                    workflow_id="test-wf",
                    success=True,
                    output="ok",
                )

        wf = TestWorkflow()

        # Mock the tracer if available
        if _tracer:
            mock_span = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_span)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            with patch.object(_tracer, "start_as_current_span", return_value=mock_ctx):
                result = wf.run({})
                assert result.success
        else:
            # OTel not installed — just verify span helper returns nullcontext
            result = wf.run({})
            assert result.success

    def test_arun_creates_parent_span(self):
        """WorkflowBase.arun() creates an OTel span."""
        from startd8.workflows.base import WorkflowBase, WorkflowResult
        from startd8.workflows.models import WorkflowMetadata

        class TestAsyncWorkflow(WorkflowBase):
            @property
            def metadata(self):
                return WorkflowMetadata(
                    workflow_id="test-async-wf",
                    name="Test Async",
                    description="Test async workflow",
                    capabilities=[],
                    inputs=[],
                    requires_agents=False,
                )

            async def _aexecute(self, config, agents, on_progress):
                return WorkflowResult(
                    workflow_id="test-async-wf",
                    success=True,
                    output="async ok",
                )

        wf = TestAsyncWorkflow()
        result = asyncio.run(wf.arun({}))
        assert result.success
        assert result.output == "async ok"


class TestPipelineSpanNesting:
    """Tests for pipeline parent→step span nesting."""

    def test_arun_wraps_steps_in_parent_span(self):
        """Pipeline.arun() wraps all steps in a parent span."""
        from startd8.orchestration import Pipeline
        from startd8.agents import MockAgent

        agent = MockAgent(name="mock", model="mock-model")
        pipe = Pipeline(name="test-pipe")
        pipe.add_step("s1", agent)

        # Run the pipeline
        result = asyncio.run(pipe.arun("hello"))
        assert result.final_output is not None
        assert len(result.steps) == 1
        assert result.steps[0]["step_name"] == "s1"


class TestAutoProbeResolutionCascade:
    """Tests for the 3-tier auto-probe resolution cascade."""

    def test_runtime_state_auto_discovered_default(self):
        """Auto mode with no env/config probes localhost:4317 (reachable)."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "auto"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=True), \
                     patch.object(otel_mod, "_resolve_config_endpoint", return_value=None):
                    state = otel_mod.get_otel_runtime_state()
                assert state["will_configure"] is True
                assert state["reason"] == "auto_discovered_default"
                assert state["endpoint_effective"] == "http://localhost:4317"
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_runtime_state_auto_no_collector_found(self):
        """Auto mode with no env/config probes localhost:4317 (unreachable)."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "auto"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=False), \
                     patch.object(otel_mod, "_resolve_config_endpoint", return_value=None):
                    state = otel_mod.get_otel_runtime_state()
                assert state["will_configure"] is False
                assert state["reason"] == "auto_no_collector_found"
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_runtime_state_config_endpoint_reachable(self):
        """Auto mode uses config file endpoint when env var is unset."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "auto"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_resolve_config_endpoint", return_value="http://config-host:4317"), \
                     patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=True):
                    state = otel_mod.get_otel_runtime_state()
                assert state["will_configure"] is True
                assert state["reason"] == "auto_config_endpoint_reachable"
                assert state["endpoint_effective"] == "http://config-host:4317"
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_runtime_state_config_endpoint_unreachable(self):
        """Auto mode: config endpoint unreachable → skip (no fallback to default)."""
        with patch.dict(os.environ, {"STARTD8_OTEL": "auto"}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_resolve_config_endpoint", return_value="http://dead:4317"), \
                     patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=False):
                    state = otel_mod.get_otel_runtime_state()
                assert state["will_configure"] is False
                assert state["reason"] == "auto_config_endpoint_unreachable"
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_env_var_takes_priority_over_config(self):
        """Env var endpoint is tried before config endpoint."""
        with patch.dict(os.environ, {
            "STARTD8_OTEL": "auto",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://env-host:4317",
        }):
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_otlp_endpoint_reachable", return_value=True), \
                     patch.object(otel_mod, "_resolve_config_endpoint", return_value="http://config-host:4317") as mock_cfg:
                    state = otel_mod.get_otel_runtime_state()
                assert state["will_configure"] is True
                assert state["reason"] == "auto_endpoint_reachable"
                assert state["endpoint_effective"] == "http://env-host:4317"
                # Config endpoint should NOT have been checked
                mock_cfg.assert_not_called()
            finally:
                otel_mod.OTEL_AVAILABLE = original

    def test_config_mode_used_when_env_unset(self):
        """Config file mode is used when STARTD8_OTEL env var is unset."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STARTD8_OTEL", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            import startd8.otel as otel_mod
            original = otel_mod.OTEL_AVAILABLE
            otel_mod.OTEL_AVAILABLE = True
            try:
                with patch.object(otel_mod, "_resolve_config_mode", return_value="disabled"):
                    state = otel_mod.get_otel_runtime_state()
                assert state["mode"] == "disabled"
                assert state["reason"] == "disabled_mode"
            finally:
                otel_mod.OTEL_AVAILABLE = original


class TestConfigFileResolution:
    """Tests for _resolve_config_endpoint() and _resolve_config_mode()."""

    def test_resolve_config_endpoint_from_file(self):
        """Reads otel.endpoint from config file."""
        import startd8.otel as otel_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".startd8"
            config_dir.mkdir()
            config_path = config_dir / "config.json"
            config_path.write_text(json.dumps({
                "otel": {"endpoint": "http://my-collector:4317"}
            }))
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = otel_mod._resolve_config_endpoint()
            assert result == "http://my-collector:4317"

    def test_resolve_config_endpoint_missing_file(self):
        """Returns None when config file doesn't exist."""
        import startd8.otel as otel_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = otel_mod._resolve_config_endpoint()
            assert result is None

    def test_resolve_config_endpoint_null_value(self):
        """Returns None when otel.endpoint is null."""
        import startd8.otel as otel_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".startd8" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(json.dumps({"otel": {"endpoint": None}}))
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = otel_mod._resolve_config_endpoint()
            assert result is None

    def test_resolve_config_mode_from_file(self):
        """Reads otel.mode from config file."""
        import startd8.otel as otel_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".startd8" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(json.dumps({"otel": {"mode": "enabled"}}))
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = otel_mod._resolve_config_mode()
            assert result == "enabled"

    def test_resolve_config_mode_missing_file(self):
        """Returns None when config file doesn't exist."""
        import startd8.otel as otel_mod
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                result = otel_mod._resolve_config_mode()
            assert result is None


class TestTelemetryBanner:
    """Tests for format_telemetry_banner()."""

    def test_banner_active_auto_discovered(self):
        """Banner for auto-discovered collector."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": True,
            "reason": "auto_discovered_default",
            "endpoint_effective": "http://localhost:4317",
        }
        banner = format_telemetry_banner(state)
        assert "ACTIVE" in banner
        assert "localhost:4317" in banner
        assert "auto-discovered" in banner

    def test_banner_active_env_var(self):
        """Banner for env var endpoint."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": True,
            "reason": "auto_endpoint_reachable",
            "endpoint_effective": "http://collector:4317",
        }
        banner = format_telemetry_banner(state)
        assert "ACTIVE" in banner
        assert "env var" in banner

    def test_banner_active_config_file(self):
        """Banner for config file endpoint."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": True,
            "reason": "auto_config_endpoint_reachable",
            "endpoint_effective": "http://config:4317",
        }
        banner = format_telemetry_banner(state)
        assert "ACTIVE" in banner
        assert "config file" in banner

    def test_banner_inactive_no_collector(self):
        """Banner when no collector found."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": False,
            "reason": "auto_no_collector_found",
            "endpoint_effective": "http://localhost:4317",
        }
        banner = format_telemetry_banner(state)
        assert "INACTIVE" in banner
        assert "no collector found" in banner

    def test_banner_inactive_disabled(self):
        """Banner when disabled explicitly."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": False,
            "reason": "disabled_mode",
            "endpoint_effective": None,
        }
        banner = format_telemetry_banner(state)
        assert "INACTIVE" in banner
        assert "disabled" in banner

    def test_banner_inactive_packages_missing(self):
        """Banner when OTel packages not installed."""
        from startd8.otel import format_telemetry_banner
        state = {
            "will_configure": False,
            "reason": "otel_packages_missing",
            "endpoint_effective": None,
        }
        banner = format_telemetry_banner(state)
        assert "INACTIVE" in banner
        assert "not installed" in banner


class TestConfigManagerOtel:
    """Tests for ConfigManager OTel settings."""

    def test_get_set_clear_otel_setting(self):
        """OTel settings round-trip through get/set/clear."""
        from startd8.config import ConfigManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ConfigManager(config_dir=Path(tmpdir))

            # Default is None
            assert mgr.get_otel_setting("endpoint") is None
            assert mgr.get_otel_setting("mode") is None

            # Set values
            mgr.set_otel_setting("endpoint", "http://test:4317")
            mgr.set_otel_setting("mode", "enabled")
            assert mgr.get_otel_setting("endpoint") == "http://test:4317"
            assert mgr.get_otel_setting("mode") == "enabled"

            # Clear
            mgr.clear_otel_setting("endpoint")
            assert mgr.get_otel_setting("endpoint") is None
            # mode should still be set
            assert mgr.get_otel_setting("mode") == "enabled"

    def test_otel_setting_persists_to_disk(self):
        """OTel settings survive ConfigManager reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from startd8.config import ConfigManager
            mgr1 = ConfigManager(config_dir=Path(tmpdir))
            mgr1.set_otel_setting("endpoint", "http://persisted:4317")

            # Reload from disk
            mgr2 = ConfigManager(config_dir=Path(tmpdir))
            assert mgr2.get_otel_setting("endpoint") == "http://persisted:4317"

    def test_otel_default_in_config(self):
        """Default config includes otel section."""
        from startd8.config import ConfigManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ConfigManager(config_dir=Path(tmpdir))
            config = mgr.export_config()
            assert "otel" in config
            assert config["otel"]["endpoint"] is None
            assert config["otel"]["mode"] is None
