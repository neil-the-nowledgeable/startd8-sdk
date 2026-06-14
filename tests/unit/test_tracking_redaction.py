"""Unit tests for tracking_redaction middleware (T0.1 / FR-19 / CRP R1-F2)."""

from startd8.integrations import tracking_redaction
from startd8.integrations.tracking_redaction import (
    redact_attrs,
    redact_evidence,
    redact_text,
)

FAKE_KEY = "sk-ant-" + "A" * 40
HOME_PATH = "/Users/someone/secrets/config.json"


class TestRedactText:
    def test_redacts_api_key(self):
        out = redact_text(f"the key is {FAKE_KEY} ok")
        assert FAKE_KEY not in out
        assert "REDACTED" in out

    def test_redacts_home_path(self):
        out = redact_text(f"wrote to {HOME_PATH}")
        assert "/Users/someone/" not in out
        assert "config.json" in out  # basename survives, username scrubbed

    def test_none_passes_through(self):
        assert redact_text(None) is None

    def test_clean_text_unchanged(self):
        assert redact_text("nothing secret here") == "nothing secret here"


class TestRedactAttrs:
    def test_redacts_string_values_recursively(self):
        out = redact_attrs({"a": FAKE_KEY, "nested": {"b": HOME_PATH}, "n": 5})
        assert FAKE_KEY not in out["a"]
        assert "/Users/someone/" not in out["nested"]["b"]
        assert out["n"] == 5  # non-strings pass through

    def test_empty(self):
        assert redact_attrs(None) == {}


class TestRedactEvidence:
    def test_redacts_ref_and_description_keeps_type(self):
        ev = [{"type": "doc", "ref": HOME_PATH, "description": f"see {FAKE_KEY}"}]
        out = redact_evidence(ev)
        assert out[0]["type"] == "doc"
        assert "/Users/someone/" not in out[0]["ref"]
        assert FAKE_KEY not in out[0]["description"]

    def test_skips_non_dicts(self):
        assert redact_evidence(["not-a-dict", {"type": "x", "ref": "y"}]) == [{"type": "x", "ref": "y"}]


class TestFailOpen:
    def test_redact_text_drops_field_on_exception(self, monkeypatch):
        """If the underlying redactor raises, the field is dropped, not raised (CRP R1-F2)."""
        def boom(_text):
            raise RuntimeError("redactor exploded")

        monkeypatch.setattr(tracking_redaction, "_redact_prose", boom)
        out = redact_text("anything")
        assert out == "«REDACTION-FAILED:dropped»"  # dropped, no exception propagated

    def test_redact_attrs_isolates_bad_field(self, monkeypatch):
        calls = {"n": 0}
        real = tracking_redaction._redact_prose

        def flaky(text):
            calls["n"] += 1
            if "BAD" in text:
                raise RuntimeError("boom")
            return real(text)

        monkeypatch.setattr(tracking_redaction, "_redact_prose", flaky)
        out = redact_attrs({"good": "fine", "bad": "BAD value"})
        assert out["good"] == "fine"
        assert out["bad"] == "«REDACTION-FAILED:dropped»"
