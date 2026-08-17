from app.main import health


def test_health_ok():
    assert health() == {"status": "ok"}
