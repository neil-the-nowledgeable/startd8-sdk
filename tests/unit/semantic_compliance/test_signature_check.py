"""FR-17 — deterministic missing-required-symbol backstop (run-029 calibration fix)."""

from startd8.semantic_compliance.signature_check import (
    missing_required_symbols,
    required_symbol_names,
)


API_SIGS = [
    "def job_workspace(request, id: int) -> Response",
    "def jobs_dashboard(request) -> Response",
    "def resolve_matches(session, jd_id: int) -> list",
]


def test_extract_symbol_names():
    assert required_symbol_names(API_SIGS) == ["job_workspace", "jobs_dashboard", "resolve_matches"]
    assert required_symbol_names(["class JobsRouter", "router = APIRouter()"]) == ["JobsRouter", "router"]
    assert required_symbol_names([]) == []


def test_run029_shape_missing_handlers_detected():
    # The actual run-029 defect: only the helper exists; the two handlers are absent.
    code = "import logging\nlogger = logging.getLogger(__name__)\n\ndef resolve_matches(session, jd_id):\n    return []\n"
    missing = missing_required_symbols(code, API_SIGS)
    assert missing == ["job_workspace", "jobs_dashboard"]


def test_all_present_none_missing():
    code = (
        "def job_workspace(request, id):\n    ...\n"
        "def jobs_dashboard(request):\n    ...\n"
        "def resolve_matches(session, jd_id):\n    return []\n"
    )
    assert missing_required_symbols(code, API_SIGS) == []


def test_reexported_import_counts_as_present():
    code = "from app.helpers import resolve_matches\n\ndef job_workspace(r, id):\n    ...\ndef jobs_dashboard(r):\n    ...\n"
    assert missing_required_symbols(code, API_SIGS) == []


def test_no_api_signatures_is_noop():
    assert missing_required_symbols("def anything(): ...", []) == []


def test_unparseable_code_skips_backstop():
    # Don't false-fail on syntactically broken code — that's the repair pipeline's job.
    assert missing_required_symbols("def broken( syntax error", API_SIGS) == []
