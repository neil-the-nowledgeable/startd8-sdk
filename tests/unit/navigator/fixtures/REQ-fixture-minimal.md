# Fixture REQ — minimal det-req for navigator FR-6

**Project:** startd8-sdk-test   **Criticality:** low
**Version:** 0.1   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Inherits standards:** det-req-kit

## Overview

Fixture for SDK navigator requirements source tests.

## Objectives

- O-1: Exercise Lives parse — target: fixture only

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Fixture only | Keep minimal | low |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Strong lives.** A done claim with a commit-anchored locator is grounded. Touches: fixture. Lives: code git:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:src/startd8/navigator/models.py. Verify (already true): models.py exists.
- **FR-2 — Done without lives.** A done claim without Lives stays unknown. Touches: fixture. Verify (already true): no locator yet.
- **FR-3 — Spec only.** An open Verify is not a done claim. Touches: fixture. Verify: unit test will assert status_key is spec.

## Non-goals

- NR-1: Full V-1..V-5 parity.

## Owned fields

Only humans enter: none.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** SCHEMA.md §8

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| fixture | command | structure | test only |

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds
