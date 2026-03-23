# Prompt: Validate C# MicroPrime Behavior

> Use this prompt to diagnose MicroPrime's element-level behavior on a C# Prime Contractor run. Answers: why did elements classify at each tier? Did templates fire? What cost savings resulted?

---

## Inputs

```
Run directory:  {run_dir}/plan-ingestion/
Project root:   {project_root}
```

## Files to Read

| File | What to Check |
|------|--------------|
| `kaizen-metrics.json` | `route` field, `micro_prime_analysis` |
| `prime-postmortem-report.json` | Per-feature `generation_strategy`, `template_used`, `template_name` |
| `prime-context-seed-enriched.json` | Per-task `estimated_loc`, `target_files` |
| `.startd8/state/generation_cache/*.json` | Per-element `metadata.micro_prime`, `metadata.tier` |
| Run logs (Loki or stderr) | Filter for `TRIVIAL dispatch:` and `SIMPLE dispatch:` entries |

---

## Step 1: Determine Activation State

Read `kaizen-metrics.json` → check for `micro_prime_analysis` in `prime-postmortem-report.json`.

Classify into exactly ONE state:

### State A: Not Enabled
- `micro_prime_analysis` is `null` or absent
- No `TRIVIAL dispatch:` or `SIMPLE dispatch:` in logs
- **Cause:** `--micro-prime` flag not passed. Check `pipeline.env` for `PRIME_CONTRACTOR_EXTRA_ARGS`
- **Grade: F** — configuration issue, not a code issue

### State B: Enabled, All COMPLEX
- Log shows `Tier distribution: complex=N (total=N)` where complex == total
- `micro_prime_analysis` may exist but show 0 local elements
- **Cause:** Feature-level classification put everything in COMPLEX tier. Check:
  - `estimated_loc` per task in seed — are any under 500 (`loc_complex_min`)?
  - `blast_radius`, `has_cross_file_edges`, `security_sensitive` signals
  - If estimated_loc < 500 but still COMPLEX: other signals (blast_radius > 3, security_sensitive=True) may have triggered COMPLEX
- **Grade: D** — MicroPrime enabled but unable to help

### State C: Enabled, Elements Processed
- Log shows `TRIVIAL dispatch: element=X ... match=template_name` entries
- Some features have `template_used: true` or `generation_strategy: "template"`
- **Grade: A-C** based on local generation percentage (see thresholds in EVALUATE_CSHARP_RUN.md)

---

## Step 2: Classification Diagnosis (State B only)

For each feature in the seed, simulate classification:

| Feature | Est. LOC | Extension | Security Sensitive | Expected Tier | Actual Tier |
|---------|----------|-----------|-------------------|---------------|-------------|
| ? | ? | ? | ? | ? | ? |

**C# tier classification rules** (from `complexity/classifier.py`):
- `.cs` IS a registered language → full signal analysis (not LOC-only)
- `security_sensitive=True` → minimum MODERATE (Anzen floor)
- `estimated_loc > 500` → COMPLEX
- `blast_radius > 3` → COMPLEX
- `has_cross_file_edges` + multi-file → COMPLEX
- SIMPLE requires: `manifest_coverage="full"` + `blast_radius=0` + `edit_mode="create"` + `estimated_loc < loc_simple_max`
- Relaxed SIMPLE: `blast_radius ≤ 2` + `edit_mode="create"` (from Kaizen run-017)

**Common reasons for unexpected COMPLEX:**
1. `estimated_loc` inflated by long task descriptions (not actual code LOC)
2. `blast_radius > 0` because existing files import the target
3. `security_sensitive=True` forces minimum MODERATE (cannot be TRIVIAL/SIMPLE)
4. `manifest_coverage="none"` (no forward manifest → can't verify SIMPLE conditions)

---

## Step 3: Template Effectiveness (State C only)

### Available C# Templates (8 total)

| Template | Match Condition | Typical Element |
|----------|----------------|-----------------|
| `csharp_di_constructor` | name == parent_class + interface params (`I` prefix) | `CartService(ICartStore, ILogger<T>)` |
| `csharp_constructor` | name == parent_class or `.ctor` | `CartStore(IDistributedCache)` |
| `csharp_property` | getter/setter property pattern | `public string Name { get; set; }` |
| `csharp_equals` | `Equals` method override | `bool Equals(object obj)` |
| `csharp_gethashcode` | `GetHashCode` override | `int GetHashCode()` |
| `csharp_tostring` | `ToString` override | `string ToString()` |
| `csharp_dispose` | `Dispose` method (IDisposable) | `void Dispose()` |
| `csharp_async_method` | async Task return type | `Task DoWorkAsync()` |

### Template Gap Analysis

For each TRIVIAL/SIMPLE element that did NOT match a template:
- What was the element name, kind, and parent_class?
- Which template SHOULD have matched? Why didn't it?
- Common mismatches:
  - `parent_class` not set → constructor templates require it
  - `kind=FUNCTION` instead of `kind=METHOD` → class method templates require METHOD
  - Element name doesn't follow the expected pattern (e.g., `Initialize` instead of class name for constructor)

---

## Step 4: Splicer Chain (if Ollama generated C# code)

If any SIMPLE C# elements reached Ollama (not templates):
1. Did `_splice_csharp_dispatch` fire? (Log: "csharp_splicer")
2. Was `splice_csharp_bodies()` called with the method name?
3. Did it return `SpliceResult.code` (success) or `None` (failure)?
4. Was the spliced output valid? (`validate_syntax()` pass/fail)

If splicer returned `None`:
- The stub pattern in the skeleton may not match C#'s `throw new NotImplementedException()`
- The method name in the generated body may not match the skeleton's method signature

---

## Step 5: Cost Assessment

| Category | Count | Est. Cost Each | Total |
|----------|-------|---------------|-------|
| Template matches (TRIVIAL) | ? | $0.00 | $0.00 |
| Local Ollama (SIMPLE) | ? | ~$0.01–0.05 | ? |
| Cloud escalation (COMPLEX) | ? | ~$0.10–0.20 | ? |
| **Total** | ? | | ? |
| **All-cloud baseline** | ? | ~$0.12/feature | ? |
| **Savings** | | | ? |

---

## Output

```
MicroPrime State: [A / B / C]
Grade: [A / B / C / D / F]
Template hit rate: X/Y (Z%)
Local generation rate: X/Y (Z%)
Estimated savings: $X.XX
Top recommendation: [fix classification / add templates / tune thresholds]
```
