# Generic Exception Handlers to Fix

**Created:** December 23, 2025
**Total Remaining:** 165 instances
**Status:** Organized into batches of 15 for systematic fixing
**Priority:** 🔴 Critical (CRITICAL-4 from code review)

---

## Overview

This document lists all remaining generic exception handlers (`except Exception` or `except:`) that need to be improved with specific exception types and better error logging. Handlers are grouped into batches of 15 for systematic addressing.

**Already Fixed:**
- ✅ `job_queue.py` - 18 handlers fixed
- ✅ `iterative_workflow.py` - 3 handlers fixed
- ✅ `orchestration.py` - 1 handler fixed
- ✅ `providers/anthropic.py` - 2 handlers fixed
- ✅ `providers/openai.py` - 2 handlers fixed
- ✅ `providers/gemini.py` - 2 handlers fixed
- ✅ `providers/registry.py` - 3 handlers fixed

**Remaining:** 165 handlers across 32 files

---

## Batch 1: __init__.py & agents.py (15 handlers)

**Priority:** 🔴 High (affects core functionality)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 1 | `__init__.py` | 142 | TBD | Needs review |
| 2 | `__init__.py` | 153 | TBD | Needs review |
| 3 | `__init__.py` | 171 | TBD | Needs review |
| 4 | `agents.py` | 185 | TBD | Needs review |
| 5 | `agents.py` | 576 | TBD | Needs review |
| 6 | `agents.py` | 607 | TBD | Needs review |
| 7 | `agents.py` | 623 | TBD | Needs review |
| 8 | `agents.py` | 731 | TBD | Needs review |
| 9 | `agents.py` | 976 | TBD | Needs review |
| 10 | `agents.py` | 1090 | TBD | Needs review |
| 11 | `agents.py` | 1227 | TBD | Needs review |
| 12 | `agents.py` | 1244 | TBD | Needs review |
| 13 | `agents.py` | 1285 | TBD | Needs review |
| 14 | `benchmark.py` | 97 | TBD | Needs review |
| 15 | `cli.py` | 261 | TBD | Needs review |

---

## Batch 2: cli.py & config.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 16 | `cli.py` | 466 | TBD | Needs review |
| 17 | `cli.py` | 506 | TBD | Needs review |
| 18 | `cli.py` | 517 | TBD | Needs review |
| 19 | `config.py` | 47 | TBD | Needs review |
| 20 | `costs/pricing.py` | 165 | TBD | Needs review |
| 21 | `costs/store.py` | 248 | TBD | Needs review |
| 22 | `costs/store.py` | 310 | TBD | Needs review |
| 23 | `costs/store.py` | 568 | TBD | Needs review |
| 24 | `costs/store.py` | 609 | TBD | Needs review |
| 25 | `display_config.py` | 130 | TBD | Needs review |
| 26 | `display_config.py` | 154 | TBD | Needs review |
| 27 | `document_enhancement.py` | 163 | TBD | Needs review |
| 28 | `document_enhancement.py` | 187 | TBD | Needs review |
| 29 | `document_enhancement.py` | 238 | TBD | Needs review |
| 30 | `document_enhancement.py` | 433 | TBD | Needs review |

---

## Batch 3: document_enhancement.py & document_updater.py (15 handlers)

**Priority:** 🔴 High (affects core functionality)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 31 | `document_enhancement.py` | 662 | TBD | Needs review |
| 32 | `document_updater.py` | 285 | TBD | Needs review |
| 33 | `document_updater.py` | 668 | TBD | Needs review |
| 34 | `document_updater.py` | 1136 | TBD | Needs review |
| 35 | `error_analysis.py` | 152 | TBD | Needs review |
| 36 | `events/bus.py` | 151 | TBD | Needs review |
| 37 | `events/bus.py` | 163 | TBD | Needs review |
| 38 | `framework.py` | 162 | TBD | Needs review |
| 39 | `framework.py` | 275 | TBD | Needs review |
| 40 | `mcp/gateway.py` | 481 | TBD | Needs review |
| 41 | `mcp/gateway.py` | 585 | TBD | Needs review |
| 42 | `mcp/gateway.py` | 613 | TBD | Needs review |
| 43 | `model_discovery.py` | 103 | TBD | Needs review |
| 44 | `model_discovery.py` | 148 | TBD | Needs review |
| 45 | `model_discovery.py` | 191 | TBD | Needs review |

---

## Batch 4: models.py & prompt_builder/context.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 46 | `models.py` | 56 | TBD | Needs review |
| 47 | `prompt_builder/context.py` | 176 | TBD | Needs review |
| 48 | `prompt_builder/context.py` | 189 | TBD | Needs review |
| 49 | `prompt_builder/loader.py` | 51 | TBD | Needs review |
| 50 | `prompt_builder/loader.py` | 68 | TBD | Needs review |
| 51 | `prompt_builder/loader.py` | 89 | TBD | Needs review |
| 52 | `prompt_enhancer.py` | 413 | TBD | Needs review |
| 53 | `providers/anthropic.py` | 44 | TBD | Needs review |
| 54 | `providers/anthropic.py` | 133 | TBD | Needs review |
| 55 | `providers/gemini.py` | 44 | TBD | Needs review |
| 56 | `providers/gemini.py` | 125 | TBD | Needs review |
| 57 | `providers/openai.py` | 46 | TBD | Needs review |
| 58 | `providers/openai.py` | 128 | TBD | Needs review |
| 59 | `providers/registry.py` | 170 | TBD | Needs review |
| 60 | `providers/registry.py` | 187 | TBD | Needs review |

---

## Batch 5: providers/registry.py & security.py (15 handlers)

**Priority:** 🔴 High (affects user experience)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 61 | `providers/registry.py` | 381 | TBD | Needs review |
| 62 | `security.py` | 224 | TBD | Needs review |
| 63 | `security.py` | 265 | TBD | Needs review |
| 64 | `security.py` | 445 | TBD | Needs review |
| 65 | `skills/agent.py` | 436 | TBD | Needs review |
| 66 | `storage/backend.py` | 139 | TBD | Needs review |
| 67 | `storage/backend.py` | 157 | TBD | Needs review |
| 68 | `storage/base.py` | 35 | TBD | Needs review |
| 69 | `storage/base.py` | 101 | TBD | Needs review |
| 70 | `storage/base.py` | 153 | TBD | Needs review |
| 71 | `tui_improved.py` | 290 | TBD | Needs review |
| 72 | `tui_improved.py` | 356 | TBD | Needs review |
| 73 | `tui_improved.py` | 619 | TBD | Needs review |
| 74 | `tui_improved.py` | 701 | TBD | Needs review |
| 75 | `tui_improved.py` | 734 | TBD | Needs review |

---

## Batch 6: tui_improved.py (15 handlers)

**Priority:** 🔴 High (affects user experience)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 76 | `tui_improved.py` | 776 | TBD | Needs review |
| 77 | `tui_improved.py` | 785 | TBD | Needs review |
| 78 | `tui_improved.py` | 802 | TBD | Needs review |
| 79 | `tui_improved.py` | 809 | TBD | Needs review |
| 80 | `tui_improved.py` | 816 | TBD | Needs review |
| 81 | `tui_improved.py` | 823 | TBD | Needs review |
| 82 | `tui_improved.py` | 830 | TBD | Needs review |
| 83 | `tui_improved.py` | 927 | TBD | Needs review |
| 84 | `tui_improved.py` | 946 | TBD | Needs review |
| 85 | `tui_improved.py` | 967 | TBD | Needs review |
| 86 | `tui_improved.py` | 986 | TBD | Needs review |
| 87 | `tui_improved.py` | 994 | TBD | Needs review |
| 88 | `tui_improved.py` | 1012 | TBD | Needs review |
| 89 | `tui_improved.py` | 1031 | TBD | Needs review |
| 90 | `tui_improved.py` | 1135 | TBD | Needs review |

---

## Batch 7: tui_improved.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 91 | `tui_improved.py` | 1545 | TBD | Needs review |
| 92 | `tui_improved.py` | 1591 | TBD | Needs review |
| 93 | `tui_improved.py` | 1827 | TBD | Needs review |
| 94 | `tui_improved.py` | 2429 | TBD | Needs review |
| 95 | `tui_improved.py` | 2738 | TBD | Needs review |
| 96 | `tui_improved.py` | 2805 | TBD | Needs review |
| 97 | `tui_improved.py` | 2922 | TBD | Needs review |
| 98 | `tui_improved.py` | 3039 | TBD | Needs review |
| 99 | `tui_improved.py` | 3058 | TBD | Needs review |
| 100 | `tui_improved.py` | 3353 | TBD | Needs review |
| 101 | `tui_improved.py` | 3358 | TBD | Needs review |
| 102 | `tui_improved.py` | 3366 | TBD | Needs review |
| 103 | `tui_improved.py` | 3406 | TBD | Needs review |
| 104 | `tui_improved.py` | 3411 | TBD | Needs review |
| 105 | `tui_improved.py` | 3428 | TBD | Needs review |

---

## Batch 8: tui_improved.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 106 | `tui_improved.py` | 3519 | TBD | Needs review |
| 107 | `tui_improved.py` | 3537 | TBD | Needs review |
| 108 | `tui_improved.py` | 3642 | TBD | Needs review |
| 109 | `tui_improved.py` | 3645 | TBD | Needs review |
| 110 | `tui_improved.py` | 3767 | TBD | Needs review |
| 111 | `tui_improved.py` | 3772 | TBD | Needs review |
| 112 | `tui_improved.py` | 3925 | TBD | Needs review |
| 113 | `tui_improved.py` | 3942 | TBD | Needs review |
| 114 | `tui_improved.py` | 3948 | TBD | Needs review |
| 115 | `tui_improved.py` | 3980 | TBD | Needs review |
| 116 | `tui_improved.py` | 4123 | TBD | Needs review |
| 117 | `tui_improved.py` | 4175 | TBD | Needs review |
| 118 | `tui_improved.py` | 4183 | TBD | Needs review |
| 119 | `tui_improved.py` | 4197 | TBD | Needs review |
| 120 | `tui_improved.py` | 4222 | TBD | Needs review |

---

## Batch 9: tui_improved.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 121 | `tui_improved.py` | 4478 | TBD | Needs review |
| 122 | `tui_improved.py` | 4703 | TBD | Needs review |
| 123 | `tui_improved.py` | 5117 | TBD | Needs review |
| 124 | `tui_improved.py` | 5366 | TBD | Needs review |
| 125 | `tui_improved.py` | 5551 | TBD | Needs review |
| 126 | `tui_improved.py` | 5573 | TBD | Needs review |
| 127 | `tui_improved.py` | 5611 | TBD | Needs review |
| 128 | `tui_improved.py` | 5631 | TBD | Needs review |
| 129 | `tui_improved.py` | 5661 | TBD | Needs review |
| 130 | `tui_improved.py` | 5808 | TBD | Needs review |
| 131 | `tui_improved.py` | 6146 | TBD | Needs review |
| 132 | `tui_improved.py` | 6263 | TBD | Needs review |
| 133 | `tui_improved.py` | 6415 | TBD | Needs review |
| 134 | `tui_improved.py` | 6512 | TBD | Needs review |
| 135 | `tui_improved.py` | 6607 | TBD | Needs review |

---

## Batch 10: tui_improved.py (15 handlers)

**Priority:** 🟠 Medium (affects specific features)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 136 | `tui_improved.py` | 6837 | TBD | Needs review |
| 137 | `tui_improved.py` | 6840 | TBD | Needs review |
| 138 | `tui_improved.py` | 7247 | TBD | Needs review |
| 139 | `tui_improved.py` | 7391 | TBD | Needs review |
| 140 | `tui_improved.py` | 7684 | TBD | Needs review |
| 141 | `tui_improved.py` | 7810 | TBD | Needs review |
| 142 | `tui_improved.py` | 7826 | TBD | Needs review |
| 143 | `tui_improved.py` | 7842 | TBD | Needs review |
| 144 | `tui_improved.py` | 8002 | TBD | Needs review |
| 145 | `tui_improved.py` | 8255 | TBD | Needs review |
| 146 | `tui_improved.py` | 8274 | TBD | Needs review |
| 147 | `tui_improved.py` | 8295 | TBD | Needs review |
| 148 | `tui_improved.py` | 8329 | TBD | Needs review |
| 149 | `tui_improved.py` | 8689 | TBD | Needs review |
| 150 | `tui_improved.py` | 8766 | TBD | Needs review |

---

## Batch 11: tui_improved.py & utils/file_operations.py (15 handlers)

**Priority:** 🔴 High (affects data persistence)

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| 151 | `tui_improved.py` | 8827 | TBD | Needs review |
| 152 | `tui_improved.py` | 9041 | TBD | Needs review |
| 153 | `tui_improved.py` | 9061 | TBD | Needs review |
| 154 | `tui_improved.py` | 9064 | TBD | Needs review |
| 155 | `tui_improved.py` | 9097 | TBD | Needs review |
| 156 | `tui_improved.py` | 9221 | TBD | Needs review |
| 157 | `utils/file_operations.py` | 52 | TBD | Needs review |
| 158 | `utils/file_operations.py` | 106 | TBD | Needs review |
| 159 | `utils/file_operations.py` | 111 | TBD | Needs review |
| 160 | `utils/file_operations.py` | 123 | TBD | Needs review |
| 161 | `utils/file_operations.py` | 144 | TBD | Needs review |
| 162 | `utils/file_operations.py` | 219 | TBD | Needs review |
| 163 | `utils/file_operations.py` | 223 | TBD | Needs review |
| 164 | `utils/file_operations.py` | 255 | TBD | Needs review |
| 165 | `utils/file_operations.py` | 261 | TBD | Needs review |

---

## Implementation Guidelines

### For Each Handler:

1. **Identify Specific Exception Types:**
   - `AgentError`, `APIError`, `ConfigurationError` for agent/API issues
   - `OSError`, `PermissionError`, `FileNotFoundError` for file operations
   - `ValueError`, `TypeError`, `KeyError` for validation errors
   - `ImportError`, `AttributeError` for import/attribute issues
   - `json.JSONDecodeError` for JSON parsing errors

2. **Add Structured Logging:**
   ```python
   except (SpecificError1, SpecificError2) as e:
       logger.error(
           f"Operation failed: {e}",
           exc_info=True,
           extra={
               "operation": "operation_name",
               "context": "relevant_context",
               "error_type": type(e).__name__
           }
       )
       # Handle or re-raise
   except Exception as e:
       logger.error(
           f"Unexpected error: {e}",
           exc_info=True,
           extra={
               "operation": "operation_name",
               "error_type": type(e).__name__
           }
       )
       # Wrap or re-raise
   ```

3. **Preserve Exception Context:**
   - Use `raise ... from e` to preserve original exception
   - Re-raise known exceptions to allow upstream handling
   - Wrap unexpected errors in appropriate exception type

4. **Add Context to Logs:**
   - Include operation name
   - Include relevant IDs (job_id, agent_name, etc.)
   - Include error type
   - Use `exc_info=True` for tracebacks

5. **Handle Bare `except:` Clauses:**
   - Replace `except:` with `except Exception as e:`
   - Add proper logging and context
   - Never use bare except clauses

---

## Progress Tracking

- [ ] Batch 1: 15 handlers
- [ ] Batch 2: 15 handlers
- [ ] Batch 3: 15 handlers
- [ ] Batch 4: 15 handlers
- [ ] Batch 5: 15 handlers
- [ ] Batch 6: 15 handlers
- [ ] Batch 7: 15 handlers
- [ ] Batch 8: 15 handlers
- [ ] Batch 9: 15 handlers
- [ ] Batch 10: 15 handlers
- [ ] Batch 11: 15 handlers

**Total:** 165 handlers across 11 batches

---

## File Distribution Summary

| File | Count | Priority |
|------|-------|----------|
| `tui_improved.py` | 86 | 🔴 High |
| `agents.py` | 10 | 🔴 High |
| `utils/file_operations.py` | 9 | 🔴 High |
| `document_enhancement.py` | 5 | 🟠 Medium |
| `cli.py` | 4 | 🟠 Medium |
| `costs/store.py` | 4 | 🟠 Medium |
| `__init__.py` | 3 | 🟠 Medium |
| `document_updater.py` | 3 | 🟠 Medium |
| `mcp/gateway.py` | 3 | 🟠 Medium |
| `model_discovery.py` | 3 | 🟠 Medium |
| `prompt_builder/loader.py` | 3 | 🟠 Medium |
| `providers/registry.py` | 3 | 🟠 Medium |
| `security.py` | 3 | 🟠 Medium |
| `storage/base.py` | 3 | 🔴 High |
| `display_config.py` | 2 | 🟠 Medium |
| `events/bus.py` | 2 | 🟠 Medium |
| `framework.py` | 2 | 🔴 High |
| `prompt_builder/context.py` | 2 | 🟠 Medium |
| `providers/anthropic.py` | 2 | 🟠 Medium |
| `providers/gemini.py` | 2 | 🟠 Medium |
| `providers/openai.py` | 2 | 🟠 Medium |
| `storage/backend.py` | 2 | 🔴 High |
| `benchmark.py` | 1 | 🟠 Medium |
| `config.py` | 1 | 🟠 Medium |
| `costs/pricing.py` | 1 | 🟠 Medium |
| `error_analysis.py` | 1 | 🟠 Medium |
| `models.py` | 1 | 🟠 Medium |
| `prompt_enhancer.py` | 1 | 🟠 Medium |
| `skills/agent.py` | 1 | 🟠 Medium |

---

## Notes

- Line numbers are exact from current codebase
- Priority is based on impact on core functionality
- TUI handlers are prioritized due to user-facing impact
- Core framework handlers are critical for system stability
- File operation handlers are important for data integrity
- Bare `except:` clauses should be replaced first