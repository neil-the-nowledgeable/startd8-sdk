# Layer 2 — Skeleton-First Prompting (REQ-MP-2xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **Depends on:** DeterministicFileAssembler ([DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md))

---

## Overview

This layer transforms how the local model is prompted. Instead of asking the model to generate a complete function (signature + body), the pipeline gives it the rendered skeleton — which already has perfect structure — and asks it to generate only the body lines. The body is then spliced into the skeleton at the correct indentation level.

This eliminates the dominant failure mode from Round 1: 53% of attempts failed due to indentation mangling of structure the pipeline already knew was correct.

## Key Insight

The `DeterministicFileAssembler` produces files like:

```python
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        raise NotImplementedError   # ← only this line needs replacing
```

Everything except `raise NotImplementedError` is deterministic and known-correct. Asking the model to regenerate the `def` line, docstring, and class wrapper is unnecessary work that introduces errors.

## Requirements

### REQ-MP-200: Skeleton as Prompt Context

**Status:** planned
**Priority:** P0
**Depends on:** DeterministicFileAssembler FR-001 through FR-008

The prompt builder SHALL use `DeterministicFileAssembler.render_file()` output as the structural context for local model prompts. The rendered element — including decorators, class wrapper (if method), full signature with type hints, and docstring — SHALL be included in the prompt verbatim.

**What changes from the current approach:**

| Aspect | Current (`_build_ollama_prompt`) | Proposed |
|--------|--------------------------------|----------|
| Signature source | Reconstructed from `ForwardElementSpec` fields | Extracted from rendered skeleton |
| Class context | Sibling signatures listed separately | Full class definition from skeleton |
| Imports | Rendered from `ForwardImportSpec` list | Extracted from skeleton's import block |
| Docstring | From `docstring_hint` field | From skeleton's rendered docstring |

**Acceptance criteria:**
- Prompt includes the verbatim rendered element from the skeleton
- The `raise NotImplementedError` line is visible as the replacement target
- No structural information is reconstructed from raw manifest fields when the skeleton provides it

---

### REQ-MP-201: Body-Only Generation

**Status:** planned
**Priority:** P0

The prompt SHALL instruct the model to generate ONLY the function body lines — not the `def` line, class definition, decorators, or docstring.

**Prompt format:**

```
# Context: This function exists in a file with these imports:
import logging
import json
from collections import OrderedDict

# The function signature and class context are fixed — do not change them.
# Replace the placeholder body with a working implementation.
# Return ONLY the body lines, indented with {N} spaces.
# Do not include the def line, class line, or docstring.

{rendered element from skeleton with raise NotImplementedError marked}
```

**Indentation specification:**
- Top-level function body: "indented with 4 spaces"
- Class method body: "indented with 8 spaces"
- Nested class method body: "indented with 12 spaces"

The indent depth is computed as `4 * nesting_depth` where nesting is derived from `ForwardElementSpec.parent_class`.

**Acceptance criteria:**
- Model output does not contain `def ` or `class ` lines when following the instruction
- Prompt specifies the exact indent depth in spaces
- Prompt includes binding constraints from `InterfaceContract` entries

---

### REQ-MP-202: Body Splicing

**Status:** planned
**Priority:** P0
**Depends on:** REQ-MP-200

The pipeline SHALL splice generated body lines into the skeleton by replacing the `raise NotImplementedError` stub.

**Algorithm:**

```
1. Parse skeleton via ast.parse()
2. Walk AST to find the target element by FQN
3. Locate the Raise node (NotImplementedError) in the element's body
4. Record the Raise node's column offset → this is the target indent
5. textwrap.dedent() the generated body
6. textwrap.indent() with the target indent string
7. Replace the source lines of the Raise node with the re-indented body
8. Validate the result via ast.parse()
```

**Edge cases:**

| Case | Handling |
|------|----------|
| Element has multi-line stub (docstring + raise) | Replace only the `raise` line, preserve docstring |
| Generated body is empty | Keep `raise NotImplementedError` (element stays as stub) |
| Generated body has multiple return paths | Accept as-is after indent normalization |
| Multiple elements in same file | Splice each independently; validate full file after all splices |

**Acceptance criteria:**
- A correctly-generated body produces a syntactically valid file after splicing
- An incorrectly-indented body is normalized to the skeleton's indent level
- The skeleton's imports, `__all__`, and other elements are preserved unchanged
- `ast.parse()` passes on the full file after splicing

---

### REQ-MP-203: Element Extraction from Skeleton

**Status:** planned
**Priority:** P1

The prompt builder SHALL extract the target element's rendered source from the skeleton to include in the prompt.

**Extraction SHALL include:**
- All decorator lines (`@property`, `@staticmethod`, etc.)
- The class definition line and bases (if the element is a method)
- The `def` line with full signature and return annotation
- The docstring (if `docstring_hint` was set)
- The `raise NotImplementedError` stub line
- Sibling method signatures (signature only, no bodies) for class context

**Extraction SHALL NOT include:**
- Other top-level elements in the file
- Import block (provided separately in the prompt)
- `__all__` list

**Acceptance criteria:**
- Extracted context matches the exact rendered text from `render_file()`
- Sibling methods provide enough context for the model to understand the class's interface
- Extraction works for both top-level functions and nested methods

---

### REQ-MP-204: Graceful Degradation on Body-Included Output

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-400 (repair pipeline)

When the model ignores the body-only instruction and returns output that includes the `def` line, the repair pipeline SHALL handle it gracefully rather than failing.

**Detection strategy:**
1. Parse the output via `ast.parse()`
2. If a `FunctionDef`/`AsyncFunctionDef` node with `name == target.name` exists, extract only its body statements
3. Re-render the body statements as source text
4. Pass through to body splicing (REQ-MP-202)

**If the output is unparseable:**
- Fall through to indentation normalization (REQ-MP-402)
- Then attempt to detect and strip the `def` line via regex as a last resort

**Acceptance criteria:**
- Model output containing `def format(self, record):` followed by body is handled without error
- The extracted body is spliced as if the model had followed the body-only instruction
- This degradation path is tracked in metrics (REQ-MP-601)

---

### REQ-MP-205: Few-Shot Body Examples

**Status:** planned
**Priority:** P2

When other elements in the same file have been successfully generated (by template, local model, or prior cloud model), the prompt builder SHALL include 1-2 completed bodies as few-shot examples.

**Example selection criteria:**
- Same `ForwardFileSpec` (same file, same import context)
- Prefer elements of similar complexity (SIMPLE tier)
- Prefer elements that share structural patterns with the target (e.g., both are methods of the same class)

**Example format in prompt:**

```
# Example (completed body for a similar method in this class):
# def getJSONLogger(name: str) -> logging.Logger:
#     body:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        return logger
```

**Constraints:**
- Maximum 2 examples per prompt
- Examples show only body lines at the correct indentation level
- Total prompt size (context + examples + target) SHALL NOT exceed 2048 tokens

**Acceptance criteria:**
- Examples are drawn from successfully generated elements in the same file
- Prompt token count stays within budget
- Elements with examples show higher Sonnet pass rate than those without (measured in experiment)

---

## Implementation Notes

### Prompt Builder Location

The current `_build_ollama_prompt()` in `scripts/experiment_local_model_routing.py` will be modified for experiment Rounds 2a-2d. For production integration, the prompt builder logic moves to `LLMChunkExecutor._build_prompt()` or a dedicated `MicroPrimePromptBuilder` class.

### Skeleton Availability

The skeleton must be rendered before the prompt is built. Two options:
1. **SCAFFOLD phase extension** — render skeletons during SCAFFOLD, write to disk, read during IMPLEMENT
2. **In-memory rendering** — call `DeterministicFileAssembler.render_file()` in the prompt builder

Option 1 is preferred because it aligns with the existing phase pipeline and makes skeletons available for `--stop-after scaffold` inspection.

### Body Splicing Location

`splice_body_into_skeleton()` is a natural addition to `utils/file_assembler.py`, alongside the existing `render_file()` and `materialize()` methods.
