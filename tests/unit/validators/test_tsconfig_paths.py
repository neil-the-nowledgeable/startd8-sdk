"""Inc-2: tsconfig path-alias existence (REQ-CKG-630) — real paths/extends parsing."""

from __future__ import annotations

import json

from startd8.validators.tsconfig_paths import scan


def _write(tmp_path, tsconfig: str, name: str = "tsconfig.json"):
    (tmp_path / name).write_text(tsconfig)
    return tmp_path


def _aliases(tmp_path):
    return {v.specifier for v in scan(tmp_path)}


def test_alias_to_nonexistent_src_flagged(tmp_path):  # #5
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}))
    assert _aliases(tmp_path) == {"@/*"}


def test_root_wildcard_alias_clean(tmp_path):
    # strtd8's real config: "@/*" -> "./*" (root exists) -> valid.
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@/*": ["./*"]}}}))
    assert _aliases(tmp_path) == set()


def test_src_alias_clean_when_src_exists(tmp_path):
    (tmp_path / "src").mkdir()
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}))
    assert _aliases(tmp_path) == set()


def test_non_wildcard_target_resolves_with_extension(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.ts").write_text("export {};")
    # target given without extension must resolve to app/index.ts
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@app": ["./app/index"]}}}))
    assert _aliases(tmp_path) == set()


def test_non_wildcard_missing_target_flagged(tmp_path):
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@app": ["./missing.ts"]}}}))
    assert _aliases(tmp_path) == {"@app"}


def test_multiple_targets_one_resolves_is_clean(tmp_path):
    (tmp_path / "lib").mkdir()
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@x/*": ["./nope/*", "./lib/*"]}}}))
    assert _aliases(tmp_path) == set()  # second target resolves -> not broken


def test_baseurl_is_honored(tmp_path):
    (tmp_path / "src").mkdir()
    # baseUrl=./src, target "./*" -> resolves under src (exists) -> clean
    _write(tmp_path, json.dumps({"compilerOptions": {"baseUrl": "./src", "paths": {"@/*": ["./*"]}}}))
    assert _aliases(tmp_path) == set()


def test_jsonc_comments_and_trailing_commas_tolerated(tmp_path):
    _write(tmp_path,
           '{\n  // next-style config\n  "compilerOptions": {\n'
           '    "strict": true,\n    "paths": { "@/*": ["./src/*"], },\n  },\n  /* end */\n}\n')
    assert _aliases(tmp_path) == {"@/*"}  # still parsed; src absent -> flagged


def test_extends_chain_merges_paths(tmp_path):
    # base defines the (broken) alias; child extends it and adds nothing -> still flagged.
    _write(tmp_path, json.dumps({"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}), name="tsconfig.base.json")
    _write(tmp_path, json.dumps({"extends": "./tsconfig.base.json", "compilerOptions": {"strict": True}}))
    assert _aliases(tmp_path) == {"@/*"}


def test_no_tsconfig_returns_empty(tmp_path):
    assert scan(tmp_path) == []


def test_no_paths_returns_empty(tmp_path):
    _write(tmp_path, json.dumps({"compilerOptions": {"strict": True}}))
    assert scan(tmp_path) == []
