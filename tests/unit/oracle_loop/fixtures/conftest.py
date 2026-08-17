"""Keep pytest from collecting the fixture apps' own test files as harness tests.

The fixtures under here are hand-authored generated apps + their ``Verify:`` test files; the oracle
runner executes them (via the sandbox), the harness must NOT import them directly (they assume an
app-relative ``app`` import root the harness does not provide).
"""

collect_ignore_glob = ["*_app/*", "*/tests/*"]
