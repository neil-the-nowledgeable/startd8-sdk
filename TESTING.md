# Testing Guide

## Quick Start

### Install Test Dependencies

```bash
# Install all dev dependencies including pytest
pip install -r requirements-dev.txt

# Or install via pyproject.toml
pip install -e ".[dev]"
```

**Note:** `pytest-asyncio` is required for async tests. It's included in `requirements-dev.txt` and automatically configured in `pytest.ini` with `asyncio_mode = auto`.

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_mcp_gateway.py

# Run specific test class
pytest tests/test_mcp_gateway.py::TestMCPGateway

# Run specific test
pytest tests/test_mcp_gateway.py::TestMCPGateway::test_initialization

# Run with verbose output
pytest -v

# Run with coverage (requires pytest-cov)
pytest --cov=src/startd8 --cov-report=term-missing
```

## Coverage Reporting

### Enable Coverage

Coverage options are commented out in `pytest.ini` by default. To enable:

1. **Install pytest-cov:**
   ```bash
   pip install pytest-cov
   ```

2. **Uncomment coverage options in pytest.ini:**
   ```ini
   addopts = 
       -v
       --strict-markers
       --tb=short
       --cov=src/startd8
       --cov-report=term-missing
       --cov-report=html
       --cov-report=xml
       --cov-fail-under=80
   ```

3. **Or run with coverage flags directly:**
   ```bash
   pytest --cov=src/startd8 --cov-report=term-missing --cov-report=html
   ```

### View Coverage Reports

After running with coverage:
- **Terminal:** Coverage summary shown in terminal
- **HTML Report:** Open `htmlcov/index.html` in browser
- **XML Report:** `coverage.xml` for CI integration

## Test Markers

Tests are organized with markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests  
- `@pytest.mark.slow` - Slow running tests

Run specific marker:
```bash
pytest -m unit
pytest -m integration
pytest -m "not slow"  # Skip slow tests
```

## Troubleshooting

### Error: "unrecognized arguments: --cov"

**Solution:** Coverage options are commented out in `pytest.ini`. Either:
1. Install pytest-cov: `pip install pytest-cov`
2. Or run without coverage: `pytest` (coverage options are commented out)

### Error: "No module named pytest"

**Solution:** Install test dependencies:
```bash
pip install -r requirements-dev.txt
```

### Error: "ModuleNotFoundError: No module named 'startd8'"

**Solution:** Install package in development mode:
```bash
pip install -e .
```

## CI/CD

In CI environments, coverage is typically enabled. The `pytest.ini` can be overridden:

```bash
# Enable coverage in CI
pytest --cov=src/startd8 --cov-report=xml --cov-fail-under=80

# Or uncomment coverage options in pytest.ini for CI
```
