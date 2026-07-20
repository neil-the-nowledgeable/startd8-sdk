"""EC-4: the FR-J delivery-role kits for the wireframe audience axis.

An application of the Audience-Keyed Content Pattern (AR-2): the two authored *base voices* are
``end_user`` (plain, for the owner) and ``architect`` (technical, for the builder). Every other
FR-J delivery role is a **kit** — an overlay that declares which base voice it speaks (plain vs
technical) plus a one-line *lens* (what that role should focus on in the preview). Until per-section
overrides are authored, a kit renders its base voice + its lens, so **a new delivery role is a config
away, not a rebuild** — exactly the pattern's promise.

The role SET + meanings are owned by ``docs/design/HITM_ROLE_MODEL_REQUIREMENTS.md`` §3 (FR-J1) — we
key on the stable kebab-case role ids there and add only the wireframe-view overlay here (Mottainai:
we cite the roles, we don't restate their definitions). ``architect`` is itself a base voice, so it is
not a kit; ``end_user`` is the plain base (closest to the customer/PO).
"""

from __future__ import annotations

# The two authored base voices (the fully-authored, coverage-gated ends of the role axis).
PLAIN = "end_user"
TECHNICAL = "architect"
BASE_VOICES = (TECHNICAL, PLAIN)

# The FR-J delivery-role kits: role id → (label, base voice it overlays, lens). Ordered roughly
# customer → delivery. ``architect`` is intentionally absent (it *is* the technical base voice).
KITS: dict[str, dict] = {
    "customer-po": {"label": "Customer / Product Owner", "base": PLAIN,
                    "lens": "Is this the app you asked for? Check every capability you need is planned."},
    "ba": {"label": "Business Analyst", "base": PLAIN,
           "lens": "Do the tracked things and their forms capture every fact the business needs?"},
    "pm": {"label": "Project Manager", "base": PLAIN,
           "lens": "What's still unfinished? Scan “What's left” and “Content needed” for the gaps to schedule."},
    "qa": {"label": "QA", "base": PLAIN,
           "lens": "Walk each screen and form as a user would — is anything missing, confusing, or unclear?"},
    "backend-dev": {"label": "Backend Developer", "base": TECHNICAL,
                    "lens": "Check the data model and the read/write boundaries before the cascade builds them."},
    "frontend-dev": {"label": "Frontend Developer", "base": TECHNICAL,
                     "lens": "Check the screens, forms, and overviews — the surfaces you'll style and wire up."},
    "dba": {"label": "Database Admin", "base": TECHNICAL,
            "lens": "Check the entities, relations, and any orphaned tables — the schema you'll own."},
    "ops": {"label": "Ops / Network Admin", "base": TECHNICAL,
            "lens": "Check where it runs: persistence, bind address, secrets, and observability posture."},
    "test-engineer": {"label": "Test Engineer", "base": TECHNICAL,
                      "lens": "Every form and view is a test surface — check the fields and boundaries to cover."},
    "security": {"label": "Security", "base": TECHNICAL,
                 "lens": "Check the write boundaries, withheld fields, the auth seam, and secrets handling."},
}


# The fluency depths the audience layer authors (mirrors descriptive.yaml's variants + the HTML toggle).
FLUENCIES = ("beginner", "intermediate", "advanced")


def known_roles() -> tuple:
    """Every valid ``--audience`` value: the two base voices + every delivery-role kit (FR-AUD/EC-4)."""
    return BASE_VOICES + tuple(KITS)


def is_kit(role: str) -> bool:
    """True if *role* is an FR-J delivery-role kit (an overlay on a base voice)."""
    return role in KITS


def base_voice(role: str) -> str | None:
    """The base voice a kit overlays (``end_user``/``architect``), or ``None`` for a base voice itself.

    A base voice returning ``None`` is what keeps the resolver's default ``(architect, ·)`` /
    ``(end_user, ·)`` behavior byte-identical — only kits get the overlay fallback (FR-AUD-1)."""
    kit = KITS.get(role)
    return kit["base"] if kit else None


def effective_voice(role: str) -> str:
    """The voice a role *renders* as: a kit renders as its base voice (plain vs technical); a base
    voice renders as itself. Drives the plain/technical presentation decisions in ``compose`` so a
    plain-base kit (PM/BA/QA) gets the plain layout and a technical kit (backend-dev/DBA) the technical one."""
    return base_voice(role) or role


def lens_for(role: str) -> str:
    """The kit's one-line focus lens (shown as a banner), or ``""`` for a base voice."""
    kit = KITS.get(role)
    return kit["lens"] if kit else ""


def label_for(role: str) -> str:
    """A human label for the role (kit label, or a title-cased base-voice name)."""
    kit = KITS.get(role)
    if kit:
        return kit["label"]
    return {"end_user": "Plain (for the owner)", "architect": "Technical (for the builder)"}.get(role, role)
