"""
Tests for session tracking functionality.
"""

import pytest
import time
from datetime import datetime, timezone

from startd8.session_tracking import (
    SessionTracker,
    SessionMetrics,
    SessionState,
    ContextUsage,
    get_session_tracker,
)


class TestContextUsage:
    """Tests for ContextUsage dataclass"""

    def test_context_usage_properties(self):
        """Test basic context usage calculations"""
        usage = ContextUsage(
            model="claude-sonnet-4-20250514",
            context_window=200000,
            input_tokens=50000,
            output_tokens=10000,
        )

        assert usage.total_tokens == 60000
        assert usage.capacity_used == 0.3  # 60000/200000
        assert usage.capacity_remaining == 140000
        assert not usage.is_near_capacity

    def test_near_capacity_detection(self):
        """Test detection of near-capacity context"""
        usage = ContextUsage(
            model="test-model",
            context_window=100000,
            input_tokens=70000,
            output_tokens=15000,
        )

        assert usage.capacity_used == 0.85
        assert usage.is_near_capacity

    def test_zero_context_window(self):
        """Test handling of zero context window"""
        usage = ContextUsage(
            model="test-model",
            context_window=0,
            input_tokens=100,
            output_tokens=50,
        )

        assert usage.capacity_used == 0.0
        assert usage.capacity_remaining == 0


class TestSessionMetrics:
    """Tests for SessionMetrics dataclass"""

    def test_session_metrics_defaults(self):
        """Test default values for session metrics"""
        metrics = SessionMetrics(
            session_id="test-123",
            created_at=datetime.now(timezone.utc),
        )

        assert metrics.state == SessionState.ACTIVE
        assert metrics.request_count == 0
        assert metrics.total_input_tokens == 0
        assert metrics.total_cost == 0.0
        assert metrics.truncation_count == 0

    def test_average_response_time(self):
        """Test average response time calculation"""
        metrics = SessionMetrics(
            session_id="test-123",
            created_at=datetime.now(timezone.utc),
            request_count=5,
            total_response_time_ms=10000,
        )

        assert metrics.average_response_time_ms == 2000.0

    def test_success_rate(self):
        """Test success rate calculation"""
        metrics = SessionMetrics(
            session_id="test-123",
            created_at=datetime.now(timezone.utc),
            request_count=10,
            successful_requests=8,
            failed_requests=2,
        )

        assert metrics.success_rate == 0.8

    def test_tokens_per_request(self):
        """Test tokens per request calculation"""
        metrics = SessionMetrics(
            session_id="test-123",
            created_at=datetime.now(timezone.utc),
            request_count=4,
            total_input_tokens=1000,
            total_output_tokens=2000,
        )

        assert metrics.tokens_per_request == 750.0

    def test_to_dict(self):
        """Test serialization to dictionary"""
        context = ContextUsage(
            model="claude-sonnet-4-20250514",
            context_window=200000,
            input_tokens=1000,
            output_tokens=500,
        )
        metrics = SessionMetrics(
            session_id="test-123",
            created_at=datetime.now(timezone.utc),
            context_usage=context,
            agent_name="claude",
            model="claude-sonnet-4-20250514",
            request_count=1,
        )

        data = metrics.to_dict()

        assert data["session_id"] == "test-123"
        assert data["agent_name"] == "claude"
        assert data["context_usage"]["context_window"] == 200000
        assert data["context_usage"]["capacity_used"] == 0.0075


class TestSessionTracker:
    """Tests for SessionTracker class"""

    def test_start_session(self):
        """Test starting a new session"""
        tracker = SessionTracker()

        session_id = tracker.start_session(
            agent_name="claude",
            model="claude-sonnet-4-20250514",
            tags=["test"],
        )

        assert session_id is not None
        assert session_id.startswith("session-")

        metrics = tracker.get_session(session_id)
        assert metrics is not None
        assert metrics.agent_name == "claude"
        assert metrics.model == "claude-sonnet-4-20250514"
        assert metrics.state == SessionState.ACTIVE
        assert "test" in metrics.tags

    def test_record_request(self):
        """Test recording a request in a session"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="claude", model="claude-sonnet-4-20250514")

        tracker.record_request(
            session_id=session_id,
            input_tokens=1000,
            output_tokens=500,
            response_time_ms=1234,
            cost=0.05,
            success=True,
        )

        metrics = tracker.get_session(session_id)
        assert metrics.request_count == 1
        assert metrics.successful_requests == 1
        assert metrics.total_input_tokens == 1000
        assert metrics.total_output_tokens == 500
        assert metrics.total_response_time_ms == 1234
        assert metrics.total_cost == 0.05
        assert metrics.context_usage.input_tokens == 1000
        assert metrics.context_usage.output_tokens == 500

    def test_record_multiple_requests(self):
        """Test recording multiple requests"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="gpt4", model="gpt-4o")

        for i in range(3):
            tracker.record_request(
                session_id=session_id,
                input_tokens=100,
                output_tokens=50,
                response_time_ms=500,
                cost=0.01,
            )

        metrics = tracker.get_session(session_id)
        assert metrics.request_count == 3
        assert metrics.total_input_tokens == 300
        assert metrics.total_output_tokens == 150
        assert metrics.total_response_time_ms == 1500
        assert metrics.total_cost == 0.03

    def test_record_failed_request(self):
        """Test recording a failed request"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="claude")

        tracker.record_request(
            session_id=session_id,
            input_tokens=100,
            output_tokens=0,
            response_time_ms=100,
            success=False,
        )

        metrics = tracker.get_session(session_id)
        assert metrics.request_count == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1

    def test_record_truncated_request(self):
        """Test recording a truncated request"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="claude")

        tracker.record_request(
            session_id=session_id,
            input_tokens=100,
            output_tokens=4096,
            response_time_ms=1000,
            truncated=True,
        )

        metrics = tracker.get_session(session_id)
        assert metrics.truncation_count == 1

    def test_end_session(self):
        """Test ending a session"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="claude")

        tracker.end_session(session_id)

        metrics = tracker.get_session(session_id)
        assert metrics.state == SessionState.COMPLETED

    def test_end_session_with_error(self):
        """Test ending a session with error state"""
        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="claude")

        tracker.end_session(session_id, state=SessionState.ERROR)

        metrics = tracker.get_session(session_id)
        assert metrics.state == SessionState.ERROR

    def test_get_active_sessions(self):
        """Test getting active sessions"""
        tracker = SessionTracker()

        session1 = tracker.start_session(agent_name="claude")
        session2 = tracker.start_session(agent_name="gpt4")
        session3 = tracker.start_session(agent_name="gemini")

        tracker.end_session(session2)

        active = tracker.get_active_sessions()
        assert len(active) == 2
        assert all(s.state == SessionState.ACTIVE for s in active)

    def test_get_summary(self):
        """Test getting session summary"""
        tracker = SessionTracker()

        session1 = tracker.start_session(agent_name="claude", model="claude-sonnet-4-20250514")
        session2 = tracker.start_session(agent_name="gpt4", model="gpt-4o")

        tracker.record_request(session1, 1000, 500, 1000, cost=0.05)
        tracker.record_request(session2, 500, 250, 800, cost=0.02)

        tracker.end_session(session1)

        summary = tracker.get_summary()

        assert summary["active_sessions"] == 1
        assert summary["completed_sessions"] == 1
        assert summary["total_sessions"] == 2
        assert summary["total_requests"] == 2
        assert summary["total_tokens"] == 2250
        assert summary["total_cost"] == 0.07

    def test_clear_completed(self):
        """Test clearing completed sessions"""
        tracker = SessionTracker()

        session1 = tracker.start_session(agent_name="claude")
        session2 = tracker.start_session(agent_name="gpt4")
        session3 = tracker.start_session(agent_name="gemini")

        tracker.end_session(session1)
        tracker.end_session(session2, state=SessionState.ERROR)

        removed = tracker.clear_completed()

        assert removed == 2
        assert len(tracker.get_all_sessions()) == 1
        assert tracker.get_session(session3) is not None

    def test_context_window_detection_claude(self):
        """Test automatic context window detection for Claude"""
        tracker = SessionTracker()
        session_id = tracker.start_session(
            agent_name="claude",
            model="claude-sonnet-4-20250514"
        )

        metrics = tracker.get_session(session_id)
        # Should detect Anthropic default context window
        assert metrics.context_usage.context_window == 200000

    def test_context_window_detection_openai(self):
        """Test automatic context window detection for OpenAI"""
        tracker = SessionTracker()
        session_id = tracker.start_session(
            agent_name="gpt4",
            model="gpt-4o"
        )

        metrics = tracker.get_session(session_id)
        # Should detect OpenAI default context window
        assert metrics.context_usage.context_window == 128000

    def test_summary_by_agent(self):
        """Test summary grouped by agent"""
        tracker = SessionTracker()

        s1 = tracker.start_session(agent_name="claude")
        s2 = tracker.start_session(agent_name="claude")
        s3 = tracker.start_session(agent_name="gpt4")

        tracker.record_request(s1, 100, 50, 500, cost=0.01)
        tracker.record_request(s2, 100, 50, 500, cost=0.01)
        tracker.record_request(s3, 200, 100, 1000, cost=0.03)

        summary = tracker.get_summary()

        assert "claude" in summary["by_agent"]
        assert "gpt4" in summary["by_agent"]
        assert summary["by_agent"]["claude"]["sessions"] == 2
        assert summary["by_agent"]["claude"]["tokens"] == 300
        assert summary["by_agent"]["gpt4"]["sessions"] == 1


class TestGlobalSessionTracker:
    """Tests for global session tracker singleton"""

    def test_get_session_tracker(self):
        """Test getting global session tracker"""
        tracker1 = get_session_tracker()
        tracker2 = get_session_tracker()

        # Should return same instance
        assert tracker1 is tracker2

    def test_global_tracker_is_usable(self):
        """Test that global tracker works"""
        tracker = get_session_tracker()

        session_id = tracker.start_session(agent_name="test")
        assert session_id is not None

        tracker.record_request(session_id, 100, 50, 500)
        metrics = tracker.get_session(session_id)
        assert metrics.request_count == 1

        tracker.end_session(session_id)


class TestSessionTrackerThreadSafety:
    """Tests for thread safety of session tracker"""

    def test_concurrent_session_start(self):
        """Test concurrent session creation"""
        import threading

        tracker = SessionTracker()
        sessions = []
        errors = []

        def start_session():
            try:
                session_id = tracker.start_session(agent_name="test")
                sessions.append(session_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=start_session) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(sessions) == 10
        assert len(set(sessions)) == 10  # All unique

    def test_concurrent_request_recording(self):
        """Test concurrent request recording"""
        import threading

        tracker = SessionTracker()
        session_id = tracker.start_session(agent_name="test")
        errors = []

        def record():
            try:
                tracker.record_request(session_id, 100, 50, 500)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        metrics = tracker.get_session(session_id)
        assert metrics.request_count == 100
        assert metrics.total_input_tokens == 10000
