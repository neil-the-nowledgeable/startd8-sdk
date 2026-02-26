---
description: Refactor Python code for clarity, idiomaticity, and maintainability
---

# Python Code Refactor Workflow

Refactor the identified Python code or recent changes using the following steps.

// turbo-all

1. Identify the Python files to refactor. If the user said "your changes", look at recent git commits or staged/unstaged changes with `git diff HEAD~1 --name-only` to get the list of changed Python files.

2. For each file that has non-trivial changes, review the code for:
   - **Type annotations**: ensure all public functions/methods have complete type annotations
   - **Docstrings**: ensure all public functions/methods have docstrings with Args/Returns when non-trivial
   - **Naming**: rename variables/functions that are ambiguous or don't follow PEP 8
   - **Logic simplification**: collapse redundant conditionals, unnecessary intermediate variables, or repeated patterns into helpers
   - **Guard clauses / early returns**: prefer early returns over deep nesting
   - **Exception specificity**: avoid bare `except:` — catch specific exception types where known
   - **Magic numbers / strings**: extract constants for repeated literals
   - **Dead code**: remove unreachable code, unused imports, or obsolete comments

3. Make targeted, surgical edits — do NOT rewrite entire files. Change only what genuinely improves the code without altering observable behaviour.

4. Run `python3 -m py_compile <file>` on each modified file to confirm no syntax errors were introduced.

5. If tests exist for the modified files, run them with `python3 -m pytest <test_file> -q --tb=short` to confirm no regressions.

6. Summarise the changes made: which files were touched, what was improved, and why.
