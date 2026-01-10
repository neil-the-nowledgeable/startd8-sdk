# FG03 — Skills and Resources (Discovery, Caching, Determinism)

## Goal

Improve skill discovery and `skill://` resources to be:

- deterministic (stable ordering)
- fast (avoid repeated disk scans)
- more helpful (best-match suggestions)

---

## Current pain points

- `_find_skills()` rescans directories on each call.
- Skill matching is “first partial match wins” which can be surprising.
- Errors often provide only a flat list, not ranked suggestions.

---

## Design: Skill index with caching

Introduce `SkillIndex` in `startd8_mcp_server/skills/discovery.py`.

### Cache policy

- Cache entries per base directory.
- Refresh when:
  - TTL expired (e.g. 2–5 seconds), OR
  - base directory mtime changes (best-effort), OR
  - explicit `STARTD8_SKILL_CACHE=0` disables caching.

### Example code (illustrative)

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SkillRecord:
    name: str
    description: str
    directory: str
    file_path: str
    metadata: dict


class SkillIndex:
    def __init__(self, ttl_s: float = 3.0):
        self.ttl_s = ttl_s
        self._cache: Dict[str, dict] = {}

    def list(self, roots: List[Path]) -> List[SkillRecord]:
        key = "|".join(str(p.resolve()) for p in roots)
        now = perf_counter()
        entry = self._cache.get(key)
        if entry and (now - entry["ts"]) < self.ttl_s:
            return entry["skills"]

        skills = self._scan(roots)
        skills.sort(key=lambda s: s.name.lower())
        self._cache[key] = {"ts": now, "skills": skills}
        return skills

    def _scan(self, roots: List[Path]) -> List[SkillRecord]:
        # implement rglob("SKILL.md"), YAML parse, etc.
        return []
```

---

## Design: matching + suggestions

### Matching behavior

- Exact match on `name`
- Exact match on directory name
- Otherwise return “not found” with **ranked suggestions**

### Scoring

Use a simple deterministic score:

- exact: 1.0
- prefix: 0.9
- substring: 0.7
- similarity (SequenceMatcher): 0.0–0.6

### Example suggestion payload

```json
{
  "error": "not_found",
  "message": "Skill 'skill-tset-1' not found",
  "data": {
    "query": "skill-tset-1",
    "suggestions": [
      {"name": "skill-test-1", "score": 0.92},
      {"name": "skill-test-2", "score": 0.74}
    ]
  }
}
```

---

## Resources

`skill://{skill_name}` should:

- use the same index/matching logic
- return a canonical JSON envelope (FG02), optionally with `view.content` containing the raw SKILL.md

---

## Worktree boundaries

Expected files changed (post-FG01 module split):

- `startd8_mcp_server/skills/discovery.py`
- `startd8_mcp_server/skills/resources.py`
- tests covering cache + ordering

---

## Acceptance criteria

- Listing skills is deterministic (stable ordering).
- Repeated list/info calls do not rescan disk each time (cache proven by test).
- Skill-not-found responses include ranked suggestions.
- `skill://` resource uses the same discovery/matching logic.
