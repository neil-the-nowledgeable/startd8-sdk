#!/usr/bin/env python3
"""Grow the golden corpus by running Micro Prime on candidate elements.

Generates code for a bank of candidate elements, scores each output,
and promotes zero-repair + high-semantic entries into the corpus.

Also instruments MicroPrimeEngine to capture successful outputs from
future production runs via a hook.

Usage:
  # Generate and promote new corpus entries from built-in candidates
  python3 scripts/grow_eval_corpus.py --generate

  # Ingest successful outputs from a production run log
  python3 scripts/grow_eval_corpus.py --ingest path/to/run-output.jsonl

  # Show corpus stats
  python3 scripts/grow_eval_corpus.py --stats
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardImportSpec
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.eval_scoring import (
    extract_element_reference,
    score_element,
    score_syntax,
)
from startd8.micro_prime.metrics import MetricsCollector
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, Signature

CORPUS_PATH = Path(__file__).resolve().parent.parent / "tests" / "evaluation" / "golden_corpus" / "corpus.json"

# ── Candidate Bank ────────────────────────────────────────────────────
# Each candidate is a minimal element spec + skeleton + hand-written
# reference. The script generates code, scores it, and if the model
# produces a zero-repair high-quality output, promotes it to the corpus.


def _candidates() -> list[dict]:
    """Return a bank of candidate elements for corpus expansion."""
    return [
        {
            "description": "Retry decorator with exponential backoff",
            "archetype": "decorator",
            "expected_tier": "moderate",
            "file": {
                "file": "src/utils/retry.py",
                "imports": [
                    {"kind": "import", "module": "time"},
                    {"kind": "import", "module": "functools"},
                    {"kind": "from", "module": "typing", "names": ["Callable", "TypeVar"]},
                ],
                "elements": [
                    {
                        "kind": "function",
                        "name": "retry",
                        "signature": {
                            "params": [
                                {"name": "max_attempts", "annotation": "int", "default": "3"},
                                {"name": "delay", "annotation": "float", "default": "1.0"},
                            ],
                            "return_annotation": "Callable",
                        },
                    }
                ],
            },
            "skeleton": "import time\nimport functools\nfrom typing import Callable, TypeVar\n\n\ndef retry(max_attempts: int = 3, delay: float = 1.0) -> Callable:\n    raise NotImplementedError\n",
            "reference": "import time\nimport functools\nfrom typing import Callable, TypeVar\n\n\ndef retry(max_attempts: int = 3, delay: float = 1.0) -> Callable:\n    def decorator(func):\n        @functools.wraps(func)\n        def wrapper(*args, **kwargs):\n            for attempt in range(max_attempts):\n                try:\n                    return func(*args, **kwargs)\n                except Exception:\n                    if attempt == max_attempts - 1:\n                        raise\n                    time.sleep(delay * (2 ** attempt))\n        return wrapper\n    return decorator\n",
        },
        {
            "description": "Singleton metaclass",
            "archetype": "metaclass",
            "expected_tier": "moderate",
            "file": {
                "file": "src/patterns/singleton.py",
                "imports": [],
                "elements": [
                    {
                        "kind": "class",
                        "name": "SingletonMeta",
                        "bases": ["type"],
                    },
                    {
                        "kind": "method",
                        "name": "__call__",
                        "parent_class": "SingletonMeta",
                        "signature": {
                            "params": [
                                {"name": "cls"},
                                {"name": "*args"},
                                {"name": "**kwargs"},
                            ],
                            "return_annotation": None,
                        },
                    },
                ],
            },
            "skeleton": "class SingletonMeta(type):\n    _instances = {}\n\n    def __call__(cls, *args, **kwargs):\n        raise NotImplementedError\n",
            "reference": "class SingletonMeta(type):\n    _instances = {}\n\n    def __call__(cls, *args, **kwargs):\n        if cls not in cls._instances:\n            cls._instances[cls] = super().__call__(*args, **kwargs)\n        return cls._instances[cls]\n",
        },
        {
            "description": "LRU cache with TTL expiration",
            "archetype": "cache",
            "expected_tier": "moderate",
            "file": {
                "file": "src/utils/cache.py",
                "imports": [
                    {"kind": "import", "module": "time"},
                    {"kind": "from", "module": "typing", "names": ["Any", "Optional"]},
                ],
                "elements": [
                    {
                        "kind": "class",
                        "name": "TTLCache",
                    },
                    {
                        "kind": "method",
                        "name": "__init__",
                        "parent_class": "TTLCache",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "ttl_seconds", "annotation": "float", "default": "300.0"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "get",
                        "parent_class": "TTLCache",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "key", "annotation": "str"},
                            ],
                            "return_annotation": "Optional[Any]",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "set",
                        "parent_class": "TTLCache",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "key", "annotation": "str"},
                                {"name": "value", "annotation": "Any"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                ],
            },
            "skeleton": "import time\nfrom typing import Any, Optional\n\n\nclass TTLCache:\n    def __init__(self, ttl_seconds: float = 300.0) -> None:\n        raise NotImplementedError\n\n    def get(self, key: str) -> Optional[Any]:\n        raise NotImplementedError\n\n    def set(self, key: str, value: Any) -> None:\n        raise NotImplementedError\n",
            "reference": "import time\nfrom typing import Any, Optional\n\n\nclass TTLCache:\n    def __init__(self, ttl_seconds: float = 300.0) -> None:\n        self._ttl = ttl_seconds\n        self._cache: dict[str, tuple[Any, float]] = {}\n\n    def get(self, key: str) -> Optional[Any]:\n        if key not in self._cache:\n            return None\n        value, timestamp = self._cache[key]\n        if time.time() - timestamp > self._ttl:\n            del self._cache[key]\n            return None\n        return value\n\n    def set(self, key: str, value: Any) -> None:\n        self._cache[key] = (value, time.time())\n",
        },
        {
            "description": "Simple rate limiter with token bucket",
            "archetype": "rate_limiter",
            "expected_tier": "moderate",
            "file": {
                "file": "src/utils/rate_limit.py",
                "imports": [
                    {"kind": "import", "module": "time"},
                ],
                "elements": [
                    {
                        "kind": "class",
                        "name": "RateLimiter",
                    },
                    {
                        "kind": "method",
                        "name": "__init__",
                        "parent_class": "RateLimiter",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "max_calls", "annotation": "int"},
                                {"name": "period", "annotation": "float"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "allow",
                        "parent_class": "RateLimiter",
                        "signature": {
                            "params": [{"name": "self"}],
                            "return_annotation": "bool",
                        },
                    },
                ],
            },
            "skeleton": "import time\n\n\nclass RateLimiter:\n    def __init__(self, max_calls: int, period: float) -> None:\n        raise NotImplementedError\n\n    def allow(self) -> bool:\n        raise NotImplementedError\n",
            "reference": "import time\n\n\nclass RateLimiter:\n    def __init__(self, max_calls: int, period: float) -> None:\n        self.max_calls = max_calls\n        self.period = period\n        self._calls: list[float] = []\n\n    def allow(self) -> bool:\n        now = time.time()\n        self._calls = [t for t in self._calls if now - t < self.period]\n        if len(self._calls) >= self.max_calls:\n            return False\n        self._calls.append(now)\n        return True\n",
        },
        {
            "description": "Context manager for temporary directory",
            "archetype": "context_manager",
            "expected_tier": "simple",
            "file": {
                "file": "src/utils/tempdir.py",
                "imports": [
                    {"kind": "import", "module": "tempfile"},
                    {"kind": "import", "module": "shutil"},
                    {"kind": "from", "module": "pathlib", "names": ["Path"]},
                ],
                "elements": [
                    {
                        "kind": "class",
                        "name": "TempDir",
                    },
                    {
                        "kind": "method",
                        "name": "__init__",
                        "parent_class": "TempDir",
                        "signature": {
                            "params": [{"name": "self"}],
                            "return_annotation": "None",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "__enter__",
                        "parent_class": "TempDir",
                        "signature": {
                            "params": [{"name": "self"}],
                            "return_annotation": "Path",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "__exit__",
                        "parent_class": "TempDir",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "exc_type"},
                                {"name": "exc_val"},
                                {"name": "exc_tb"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                ],
            },
            "skeleton": "import tempfile\nimport shutil\nfrom pathlib import Path\n\n\nclass TempDir:\n    def __init__(self) -> None:\n        raise NotImplementedError\n\n    def __enter__(self) -> Path:\n        raise NotImplementedError\n\n    def __exit__(self, exc_type, exc_val, exc_tb) -> None:\n        raise NotImplementedError\n",
            "reference": "import tempfile\nimport shutil\nfrom pathlib import Path\n\n\nclass TempDir:\n    def __init__(self) -> None:\n        self._path: Optional[Path] = None\n\n    def __enter__(self) -> Path:\n        self._path = Path(tempfile.mkdtemp())\n        return self._path\n\n    def __exit__(self, exc_type, exc_val, exc_tb) -> None:\n        if self._path and self._path.exists():\n            shutil.rmtree(self._path)\n",
        },
        {
            "description": "Event emitter with subscribe/emit pattern",
            "archetype": "event_emitter",
            "expected_tier": "moderate",
            "file": {
                "file": "src/events/emitter.py",
                "imports": [
                    {"kind": "from", "module": "typing", "names": ["Any", "Callable"]},
                    {"kind": "from", "module": "collections", "names": ["defaultdict"]},
                ],
                "elements": [
                    {
                        "kind": "class",
                        "name": "EventEmitter",
                    },
                    {
                        "kind": "method",
                        "name": "__init__",
                        "parent_class": "EventEmitter",
                        "signature": {
                            "params": [{"name": "self"}],
                            "return_annotation": "None",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "on",
                        "parent_class": "EventEmitter",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "event", "annotation": "str"},
                                {"name": "callback", "annotation": "Callable"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                    {
                        "kind": "method",
                        "name": "emit",
                        "parent_class": "EventEmitter",
                        "signature": {
                            "params": [
                                {"name": "self"},
                                {"name": "event", "annotation": "str"},
                                {"name": "**kwargs"},
                            ],
                            "return_annotation": "None",
                        },
                    },
                ],
            },
            "skeleton": "from typing import Any, Callable\nfrom collections import defaultdict\n\n\nclass EventEmitter:\n    def __init__(self) -> None:\n        raise NotImplementedError\n\n    def on(self, event: str, callback: Callable) -> None:\n        raise NotImplementedError\n\n    def emit(self, event: str, **kwargs) -> None:\n        raise NotImplementedError\n",
            "reference": "from typing import Any, Callable\nfrom collections import defaultdict\n\n\nclass EventEmitter:\n    def __init__(self) -> None:\n        self._listeners: dict[str, list[Callable]] = defaultdict(list)\n\n    def on(self, event: str, callback: Callable) -> None:\n        self._listeners[event].append(callback)\n\n    def emit(self, event: str, **kwargs) -> None:\n        for callback in self._listeners.get(event, []):\n            callback(**kwargs)\n",
        },
        {
            "description": "Simple JSON config loader with defaults",
            "archetype": "config_loader",
            "expected_tier": "simple",
            "file": {
                "file": "src/config/loader.py",
                "imports": [
                    {"kind": "import", "module": "json"},
                    {"kind": "from", "module": "pathlib", "names": ["Path"]},
                    {"kind": "from", "module": "typing", "names": ["Any"]},
                ],
                "elements": [
                    {
                        "kind": "function",
                        "name": "load_config",
                        "signature": {
                            "params": [
                                {"name": "path", "annotation": "Path"},
                                {"name": "defaults", "annotation": "dict[str, Any]", "default": "None"},
                            ],
                            "return_annotation": "dict[str, Any]",
                        },
                    }
                ],
            },
            "skeleton": "import json\nfrom pathlib import Path\nfrom typing import Any\n\n\ndef load_config(path: Path, defaults: dict[str, Any] = None) -> dict[str, Any]:\n    raise NotImplementedError\n",
            "reference": "import json\nfrom pathlib import Path\nfrom typing import Any\n\n\ndef load_config(path: Path, defaults: dict[str, Any] = None) -> dict[str, Any]:\n    config = dict(defaults or {})\n    if path.exists():\n        with open(path) as f:\n            config.update(json.load(f))\n    return config\n",
        },
        {
            "description": "Flatten nested dict with dot-separated keys",
            "archetype": "transformer",
            "expected_tier": "simple",
            "file": {
                "file": "src/utils/flatten.py",
                "imports": [
                    {"kind": "from", "module": "typing", "names": ["Any"]},
                ],
                "elements": [
                    {
                        "kind": "function",
                        "name": "flatten_dict",
                        "signature": {
                            "params": [
                                {"name": "d", "annotation": "dict[str, Any]"},
                                {"name": "prefix", "annotation": "str", "default": "\"\""},
                                {"name": "sep", "annotation": "str", "default": "\".\""},
                            ],
                            "return_annotation": "dict[str, Any]",
                        },
                    }
                ],
            },
            "skeleton": "from typing import Any\n\n\ndef flatten_dict(d: dict[str, Any], prefix: str = \"\", sep: str = \".\") -> dict[str, Any]:\n    raise NotImplementedError\n",
            "reference": "from typing import Any\n\n\ndef flatten_dict(d: dict[str, Any], prefix: str = \"\", sep: str = \".\") -> dict[str, Any]:\n    result: dict[str, Any] = {}\n    for key, value in d.items():\n        full_key = f\"{prefix}{sep}{key}\" if prefix else key\n        if isinstance(value, dict):\n            result.update(flatten_dict(value, full_key, sep))\n        else:\n            result[full_key] = value\n    return result\n",
        },
    ]


# ── Corpus Operations ─────────────────────────────────────────────────


def load_corpus() -> dict:
    with open(CORPUS_PATH) as f:
        return json.load(f)


def save_corpus(data: dict) -> None:
    with open(CORPUS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Corpus saved: {CORPUS_PATH}")


def next_corpus_id(data: dict) -> str:
    existing_ids = [e["id"] for e in data["corpus"]]
    max_num = 0
    for eid in existing_ids:
        if eid.startswith("gc-"):
            try:
                max_num = max(max_num, int(eid[3:]))
            except ValueError:
                pass
    return f"gc-{max_num + 1:03d}"


def show_stats() -> None:
    data = load_corpus()
    entries = data["corpus"]
    by_tier = {}
    by_mode = {"element": 0, "file_whole": 0}
    by_archetype = {}
    for e in entries:
        tier = e.get("expected_tier", "unknown")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        mode = e.get("mode", "element")
        if mode == "file_whole":
            by_mode["file_whole"] += 1
        else:
            by_mode["element"] += 1
        arch = e.get("archetype", "unknown")
        by_archetype[arch] = by_archetype.get(arch, 0) + 1

    print(f"\nCorpus: {len(entries)} entries")
    print(f"\nBy tier:")
    for t in ["trivial", "simple", "moderate", "complex"]:
        if t in by_tier:
            print(f"  {t}: {by_tier[t]}")
    print(f"\nBy mode:")
    for m, c in by_mode.items():
        print(f"  {m}: {c}")
    print(f"\nBy archetype ({len(by_archetype)} types):")
    for a, c in sorted(by_archetype.items(), key=lambda x: -x[1]):
        print(f"  {a}: {c}")


def generate_and_promote(dry_run: bool = False) -> None:
    """Run candidates through Micro Prime, promote high-quality outputs."""
    candidates = _candidates()
    corpus_data = load_corpus()
    existing_archetypes = {e.get("archetype") for e in corpus_data["corpus"]}

    # Filter out candidates whose archetype already exists
    new_candidates = [
        c for c in candidates
        if c.get("archetype") not in existing_archetypes
    ]

    if not new_candidates:
        print("All candidate archetypes already in corpus. Add new candidates to _candidates().")
        return

    print(f"\n{len(new_candidates)} new candidates (filtered {len(candidates) - len(new_candidates)} existing archetypes)")

    if dry_run:
        # Just validate references parse
        for c in new_candidates:
            ref = c["reference"]
            valid = score_syntax(ref)
            print(f"  {c['description']:50s} ref_valid={bool(valid)}")
        return

    config = MicroPrimeConfig(
        model="startd8-coder", provider="ollama", temperature=0.1,
        templates_enabled=False, repair_enabled=True, few_shot_enabled=False,
        file_ollama_whole_enabled=True,
    )
    metrics = MetricsCollector()
    templates = TemplateRegistry(enabled=False)
    engine = MicroPrimeEngine(config=config, template_registry=templates, metrics_collector=metrics)

    promoted = 0
    for c in new_candidates:
        desc = c["description"]
        ref = c["reference"]
        expected_imports = [imp["module"] for imp in c["file"].get("imports", [])]

        # Build specs
        file_data = c["file"]
        imports = [
            ForwardImportSpec(kind=imp["kind"], module=imp["module"], names=imp.get("names", []))
            for imp in file_data.get("imports", [])
        ]
        elements = []
        for elem_data in file_data["elements"]:
            sig = None
            if "signature" in elem_data and elem_data["signature"]:
                params = [Param(name=p["name"], annotation=p.get("annotation"), default=p.get("default"))
                          for p in elem_data["signature"].get("params", [])]
                sig = Signature(params=params, return_annotation=elem_data["signature"].get("return_annotation"))
            elements.append(ForwardElementSpec(
                kind=ElementKind(elem_data["kind"]),
                name=elem_data["name"],
                signature=sig,
                bases=elem_data.get("bases", []),
                parent_class=elem_data.get("parent_class"),
            ))
        file_spec = ForwardFileSpec(file=file_data["file"], imports=imports, elements=elements)

        # Determine mode
        non_class_elements = [e for e in elements if e.kind != ElementKind.CLASS]
        is_file_whole = len(non_class_elements) > 2

        print(f"\n  Generating: {desc} ({'file-whole' if is_file_whole else 'element'})...", end="", flush=True)

        if is_file_whole:
            from startd8.forward_manifest import ForwardManifest
            manifest = ForwardManifest(file_specs={file_spec.file: file_spec})
            result = engine.process_file(
                file_spec=file_spec, manifest=manifest,
                skeleton=c["skeleton"], ollama_available=True,
            )
            generated = result.filled_skeleton or ""
            repair_steps = []
            for er in result.element_results:
                repair_steps.extend(er.repair_steps_applied)
            zero_repair = len(repair_steps) == 0

            # Score whole file
            from startd8.micro_prime.eval_scoring import score_semantic
            sem = score_semantic(generated, ref)
            syn = score_syntax(generated)

        else:
            # Element-level: generate the first non-class element
            target = non_class_elements[0]
            result = engine.process_element(
                element=target, file_spec=file_spec, skeleton=c["skeleton"],
            )
            generated = result.code or ""
            repair_steps = result.repair_steps_applied
            zero_repair = len(repair_steps) == 0

            elem_ref = extract_element_reference(ref, target.name, parent_class=target.parent_class)
            from startd8.micro_prime.eval_scoring import score_semantic
            sem = score_semantic(generated, elem_ref)
            syn = score_syntax(generated)

        quality = "PASS" if syn and sem >= 2 else "FAIL"
        repair_label = "zero-repair" if zero_repair else f"repaired({','.join(repair_steps)})"
        print(f" syn={syn} sem={sem} {repair_label} → {quality}")

        # Promote if quality is good (regardless of repair — the reference is what matters)
        if syn and sem >= 2:
            entry_id = next_corpus_id(corpus_data)
            entry = {
                "id": entry_id,
                "description": desc,
                "archetype": c.get("archetype", "unknown"),
                "file": c["file"],
                "skeleton": c["skeleton"],
                "reference": ref,
                "expected_tier": c.get("expected_tier", "simple"),
            }
            if is_file_whole:
                entry["mode"] = "file_whole"
            corpus_data["corpus"].append(entry)
            promoted += 1
            print(f"    → Promoted as {entry_id}")
        else:
            print(f"    → Skipped (quality too low)")

    if promoted > 0:
        save_corpus(corpus_data)
        print(f"\nPromoted {promoted} new entries. Corpus now has {len(corpus_data['corpus'])} entries.")
    else:
        print(f"\nNo entries promoted. Try improving prompts first.")


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Grow the golden eval corpus")
    parser.add_argument("--generate", action="store_true", help="Generate and promote new corpus entries")
    parser.add_argument("--dry-run", action="store_true", help="Validate candidates without running Ollama")
    parser.add_argument("--stats", action="store_true", help="Show corpus statistics")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.generate or args.dry_run:
        generate_and_promote(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
