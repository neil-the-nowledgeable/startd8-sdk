"""Authoring Phases 1–4: the in-app page-authoring UI generator.

Covers the generated-owned validator/IO (`app/pages_io.py`) behavior by importing it against a temp
project, the route/template shapes, the pyyaml-only-when-authoring requirement, drift, and the
assembler/main.py wiring.
"""

from __future__ import annotations

import importlib.util

import pytest

from startd8.backend_codegen import render_authoring, render_backend
from startd8.backend_codegen.derived import render_requirements
from startd8.backend_codegen.drift import (
    check_drift,
    embedded_artifact_kind,
    is_owned_generated_file,
)
from startd8.backend_codegen.pages_authoring import (
    render_pages_admin,
    render_pages_admin_template,
    render_pages_io,
)

pytestmark = pytest.mark.unit

SCHEMA = "model Profile {\n  id   String @id\n  name String\n}\n"

PAGES_YAML = """\
# the content manifest (with comments + an explicit nav)
pages:
  - slug: "/"
    title: "Home"
    nav_label: "Home"
    content: pages/home.md

nav:
  - { label: "Home", href: "/" }
"""


def _load_pages_io(tmp_path):
    """Write the generated app/pages_io.py into a temp project and import it standalone."""
    app = tmp_path / "app"
    (app / "pages").mkdir(parents=True)
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "pages.yaml").write_text(PAGES_YAML, encoding="utf-8")
    (app / "pages" / "home.md").write_text("# Home\n", encoding="utf-8")
    io_path = app / "pages_io.py"
    io_path.write_text(render_pages_io(SCHEMA), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_pages_io", io_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, tmp_path


# --------------------------------------------------------------------------- #
# Generated code is valid + drift-recognized
# --------------------------------------------------------------------------- #

def test_generated_modules_compile_and_are_owned():
    io = render_pages_io(SCHEMA)
    admin = render_pages_admin(SCHEMA)
    compile(io, "<pages_io>", "exec")
    compile(admin, "<pages_admin>", "exec")
    assert embedded_artifact_kind(io) == "pages-io"
    assert embedded_artifact_kind(admin) == "pages-admin"
    assert is_owned_generated_file(io) and is_owned_generated_file(admin)


def test_authoring_template_parses_if_jinja_available():
    tmpl = render_pages_admin_template(SCHEMA)
    assert embedded_artifact_kind(tmpl) == "pages-admin-tmpl"
    try:
        import jinja2
    except ImportError:
        pytest.skip("jinja2 is a generated-app dep")
    jinja2.Environment().parse(tmpl)


def test_authoring_artifacts_drift_schema_only():
    for owned in (render_pages_io(SCHEMA), render_pages_admin(SCHEMA), render_pages_admin_template(SCHEMA)):
        assert check_drift(SCHEMA, owned).status == "in_sync"
        tampered = owned.replace("\n", "\n ", 1) if owned.endswith("\n") else owned + " "
        assert check_drift(SCHEMA, tampered).status == "tampered"


# --------------------------------------------------------------------------- #
# requirements.txt: pyyaml only with authoring (distinct kind so drift stays clean)
# --------------------------------------------------------------------------- #

def test_requirements_pyyaml_only_when_authoring():
    base = render_requirements(SCHEMA)
    auth = render_requirements(SCHEMA, authoring=True)
    assert "pyyaml" not in base
    assert "pyyaml" in auth
    assert embedded_artifact_kind(base) == "python-requirements"
    assert embedded_artifact_kind(auth) == "python-requirements-authoring"
    # both re-render in-sync under drift (the kind routes to the right variant)
    assert check_drift(SCHEMA, base).status == "in_sync"
    assert check_drift(SCHEMA, auth).status == "in_sync"


# --------------------------------------------------------------------------- #
# Assembler / main.py wiring
# --------------------------------------------------------------------------- #

def test_render_backend_authoring_emits_and_mounts(tmp_path):
    app = tmp_path / "app"
    (app / "pages").mkdir(parents=True)
    (app / "pages" / "home.md").write_text("# Home\n", encoding="utf-8")
    arts = dict(render_backend(SCHEMA, pages_text=PAGES_YAML, pages_app_dir=app, authoring=True))
    assert "app/pages_io.py" in arts
    assert "app/pages_admin.py" in arts
    assert "app/templates/pages/_authoring.html" in arts
    assert "from .pages_admin import pages_admin_router" in arts["app/main.py"]
    assert "pyyaml" in arts["requirements.txt"]


def test_render_backend_pages_without_authoring_excludes_admin(tmp_path):
    app = tmp_path / "app"
    (app / "pages").mkdir(parents=True)
    (app / "pages" / "home.md").write_text("# Home\n", encoding="utf-8")
    arts = dict(render_backend(SCHEMA, pages_text=PAGES_YAML, pages_app_dir=app))
    assert "app/pages_admin.py" not in arts
    assert "pyyaml" not in arts["requirements.txt"]


# --------------------------------------------------------------------------- #
# Generated IO behavior (Phases 1–4)
# --------------------------------------------------------------------------- #

def test_io_slugify_and_content_path(tmp_path):
    io, _ = _load_pages_io(tmp_path)
    assert io.slugify("/") == "home"
    assert io.slugify("/how-it-works") == "how_it_works"
    assert io.content_path_for("/about") == "pages/about.md"


def test_io_append_preserves_comments_and_nav(tmp_path):
    io, root = _load_pages_io(tmp_path)
    entry = io.append_page("/about", "About us", "About")
    assert entry == {"slug": "/about", "title": "About us", "content": "pages/about.md", "nav_label": "About"}
    text = (root / "prisma" / "pages.yaml").read_text(encoding="utf-8")
    assert "# the content manifest" in text  # comment preserved
    assert "nav:" in text and 'label: "Home"' in text  # explicit nav preserved
    # the new entry parses and is present
    import yaml
    pages = yaml.safe_load(text)["pages"]
    assert {p["slug"] for p in pages} == {"/", "/about"}


def test_io_rejects_duplicate_and_bad_slug(tmp_path):
    io, _ = _load_pages_io(tmp_path)
    with pytest.raises(io.PageError):
        io.append_page("/", "dupe", None)  # slug already exists
    with pytest.raises(io.PageError):
        io.append_page("about", "no slash", None)  # must start with /


_VALIDATOR_CORPUS = [
    ('pages:\n  - {slug: "/", title: H, content: pages/home.md}\n', True),
    ('pages:\n  - {slug: "/", title: H, content: c, extra: x}\n', False),       # unknown key
    ('pages:\n  - {slug: "/", content: c}\n', False),                            # missing title
    ('pages:\n  - {slug: home, title: H, content: c}\n', False),                 # non-"/" slug
    ('pages:\n  - {slug: "/", title: A, content: c}\n  - {slug: "/", title: B, content: d}\n', False),  # dup slug
    ('pages:\n  - {slug: "/a-b", title: A, content: c}\n  - {slug: "/a_b", title: B, content: d}\n', False),  # name collision
    ('pages:\n  - {slug: "/", title: H, content: c}\nnav:\n  - {label: Home, href: "/"}\n', True),     # good nav
    ('pages:\n  - {slug: "/", title: H, content: c}\nnav:\n  - {label: Home}\n', False),               # nav missing href
    ('pages:\n  - {slug: "/", title: H, content: c}\nnav:\n  - {label: Home, href: "/", x: 1}\n', False),  # nav unknown key
]


def test_validator_matches_parse_pages(tmp_path):
    """CRP R1-F4/S4: the generated-owned `_validate_all` must accept/reject the same manifests as the
    SDK `parse_pages`, so the UI never commits a manifest the next `generate backend` would reject."""
    import yaml

    from startd8.backend_codegen.pages_generator import parse_pages

    io, _ = _load_pages_io(tmp_path)

    def parse_ok(text):
        try:
            parse_pages(text)
            return True
        except ValueError:
            return False

    def validate_ok(text):
        try:
            io._validate_all(yaml.safe_load(text) or {})
            return True
        except io.PageError:
            return False

    for text, expected in _VALIDATOR_CORPUS:
        assert parse_ok(text) is expected, ("parse_pages", text)
        assert validate_ok(text) is expected, ("_validate_all", text)


def test_authoring_artifacts_unaffected_by_pages_change():
    """CRP R1-S8: authoring artifacts are schema-hashed — a pages.yaml change never marks them stale
    (documents the deliberate seam vs the pages-hashed content artifacts, which DO go stale)."""
    from startd8.backend_codegen.pages_generator import render_page_shell

    io = render_pages_io(SCHEMA)
    assert check_drift(SCHEMA, io).status == "in_sync"  # schema-only; no pages_text consulted

    shell = render_page_shell(SCHEMA, PAGES_YAML, "prisma/schema.prisma", "home")
    edited = PAGES_YAML.replace("Home", "Start")
    assert check_drift(SCHEMA, shell, pages_text=edited).status == "stale"


def test_io_odd_indent_manifest_fails_friendly_without_corrupting(tmp_path):
    # An existing manifest the text-insert can't safely extend must raise a friendly PageError
    # (not a raw yaml error that would bypass the route's handler) and leave the file untouched.
    io, root = _load_pages_io(tmp_path)
    yml = root / "prisma" / "pages.yaml"
    yml.write_text('pages:\n- slug: "/"\n  title: H\n  content: pages/home.md\n', encoding="utf-8")
    before = yml.read_text(encoding="utf-8")
    with pytest.raises(io.PageError):
        io.append_page("/x", "X")
    assert yml.read_text(encoding="utf-8") == before  # never left corrupted


def test_io_prose_roundtrip_and_path_safety(tmp_path):
    io, root = _load_pages_io(tmp_path)
    io.write_prose("/about", "# About\n\nhello")
    assert (root / "app" / "pages" / "about.md").read_text(encoding="utf-8") == "# About\n\nhello"
    assert io.read_prose("/about") == "# About\n\nhello"
    # slugify neutralizes traversal attempts (no escape from app/pages/)
    io.write_prose("/../../etc/passwd", "x")
    assert not (root.parent / "etc" / "passwd").exists()
