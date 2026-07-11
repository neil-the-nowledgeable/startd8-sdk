# Code Review: Input Validation

**Review Date**: December 2025  
**Priority**: 🔴 Critical  
**Status**: In Progress  
**Estimated Effort**: 6 hours

---

## Executive Summary

This review examines input validation across the startd8 SDK codebase to identify security vulnerabilities, data corruption risks, and potential crashes from invalid input. The review found **23 validation issues** across 5 categories that need immediate attention.

### Findings Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|---------|-----|-------|
| **Prompt Content** | 2 | 1 | 1 | 0 | 4 |
| **File Paths** | 3 | 2 | 1 | 0 | 6 |
| **URLs/Endpoints** | 2 | 2 | 1 | 0 | 5 |
| **Numeric Inputs** | 1 | 2 | 1 | 0 | 4 |
| **Model/Agent Names** | 1 | 1 | 2 | 0 | 4 |
| **Total** | **9** | **8** | **6** | **0** | **23** |

---

## 1. Prompt Content Validation

### 1.1 🔴 CRITICAL: No Length Limits in TUI Input

**Location**: `tui_improved.py` - Multiple locations  
**Risk**: Denial of Service (DoS) via extremely long prompts

**Issue**:
```python
# Line 4948-4955: No length validation
content_lines = []
try:
    while True:
        line = input()
        if line == "":
            break
        content_lines.append(line)
except EOFError:
    pass

content = "\n".join(content_lines)
# No validation of content length!
```

**Impact**:
- User can input unlimited content
- Can cause memory exhaustion
- Can cause API call failures (most APIs have limits)
- Can crash the application

**Recommendation**:
```python
MAX_PROMPT_LENGTH = 1_000_000  # 1MB limit (matches Prompt model)

content = "\n".join(content_lines)
if len(content) > MAX_PROMPT_LENGTH:
    self.console.print(
        f"[red]Error: Prompt exceeds maximum length of {MAX_PROMPT_LENGTH:,} characters[/red]"
    )
    return None

# Also validate at model level (already exists in Prompt model)
```

**Files Affected**:
- `tui_improved.py:4948-4955` - Job file creation
- `tui_improved.py:5100-5198` - `_get_text_or_file_input()` method
- `tui_improved.py:5200+` - Iterative workflow input
- `tui_prompt_builder.py` - Template variable input

---

### 1.2 🔴 CRITICAL: Empty Content Allowed

**Location**: `tui_improved.py:4957-4960`  
**Risk**: Invalid data, API errors

**Issue**:
```python
if not content.strip():
    self.console.print("[yellow]No content provided. Cancelled.[/yellow]")
    questionary.press_any_key_to_continue().ask()
    return
```

**Problem**: Only checks after user completes input. Should validate earlier.

**Recommendation**:
```python
# Validate as user types (if possible) or immediately after input
if not content or not content.strip():
    raise ValidationError("Prompt content cannot be empty", field="content")
```

**Files Affected**:
- `tui_improved.py:4957` - Job file creation
- `framework.py:83` - Prompt creation (has validation but not enforced in TUI)

---

### 1.3 🟠 HIGH: No Content Sanitization

**Location**: All prompt input locations  
**Risk**: Injection attacks, encoding issues

**Issue**: No sanitization of prompt content before storage or API calls.

**Recommendation**:
```python
def sanitize_prompt_content(content: str) -> str:
    """Sanitize prompt content"""
    # Remove null bytes
    content = content.replace('\x00', '')
    
    # Normalize whitespace (but preserve intentional formatting)
    # Don't strip all whitespace - prompts may need it
    
    # Validate encoding
    try:
        content.encode('utf-8')
    except UnicodeEncodeError:
        raise ValidationError("Prompt contains invalid UTF-8 characters")
    
    return content
```

---

### 1.4 🟡 MEDIUM: No Validation in File Loading

**Location**: `tui_improved.py:_get_text_or_file_input()`  
**Risk**: Loading malicious or corrupted files

**Issue**: When loading from file, no validation of file content.

**Recommendation**:
```python
def _load_file_content(self, file_path: Path) -> str:
    """Load and validate file content"""
    # Check file size
    if file_path.stat().st_size > MAX_PROMPT_LENGTH:
        raise ValidationError(f"File too large (max {MAX_PROMPT_LENGTH:,} bytes)")
    
    # Read with encoding validation
    try:
        content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        raise ValidationError("File contains invalid UTF-8 encoding")
    
    # Validate content length
    if len(content) > MAX_PROMPT_LENGTH:
        raise ValidationError(f"File content exceeds maximum length")
    
    return content
```

---

## 2. File Path Validation

### 2.1 🔴 CRITICAL: Directory Traversal Vulnerabilities

**Location**: Multiple files  
**Risk**: Access to unauthorized files/directories

**Issue**: Many file path operations use `Path().expanduser().resolve()` without checking for directory traversal.

**Examples**:
```python
# tui_improved.py:1441 - No validation
output_dir = str(Path(output_dir).expanduser().resolve())

# tui_improved.py:5182 - No validation
directory = Path(directory_path).expanduser().resolve()

# tui_improved.py:3812 - No validation
directory = Path(directory_path).expanduser().resolve()
```

**Problem**: `resolve()` normalizes paths but doesn't prevent access outside intended directories.

**Recommendation**: Use existing `sanitize_path()` function:
```python
from .security import sanitize_path

# For user-specified output directories
output_dir = sanitize_path(
    output_dir,
    base_dir=Path.home() / "startd8-workspace"  # Restrict to workspace
)

# For file operations
file_path = sanitize_path(
    user_input_path,
    base_dir=Path.cwd()  # Restrict to current directory
)
```

**Files Affected**:
- `tui_improved.py:1441` - Agent output directory
- `tui_improved.py:5182` - Document processing directory
- `tui_improved.py:3812` - Single folder processor
- `tui_improved.py:2002` - Import path
- `tui_improved.py:1913` - Export path
- `tui_prompt_builder.py:332` - Path input
- `cli.py:945` - Watch folder path

**Note**: `security.py` has `sanitize_path()` function but it's **not being used** in most places!

---

### 2.2 🔴 CRITICAL: No Base Directory Restriction

**Location**: Most file path operations  
**Risk**: Access to system files, user's entire home directory

**Issue**: Paths resolved without restricting to a base directory.

**Example**:
```python
# tui_improved.py:5182
directory = Path(directory_path).expanduser().resolve()
# User could specify: ~/../../etc/passwd
```

**Recommendation**:
```python
# Always restrict to a base directory
ALLOWED_BASE_DIRS = [
    Path.home() / "startd8-workspace",
    Path.cwd(),
]

def validate_path_with_base(path_str: str, allowed_bases: List[Path]) -> Path:
    """Validate path is within allowed base directories"""
    path = Path(path_str).expanduser().resolve()
    
    for base in allowed_bases:
        base_resolved = base.resolve()
        try:
            path.relative_to(base_resolved)
            return path  # Path is within this base
        except ValueError:
            continue
    
    raise ValidationError(
        f"Path {path} is not within allowed directories",
        field="path"
    )
```

---

### 2.3 🔴 CRITICAL: Path Validation Bug in `sanitize_path()`

**Location**: `security.py:45`  
**Risk**: False negatives - allows some traversal attempts

**Issue**:
```python
# security.py:45 - Current implementation
if '..' in str(path):
    raise ValidationError(...)
```

**Problem**: This checks the **resolved** path, not the **original** input. After `resolve()`, `..` is normalized away, so this check may not catch all cases.

**Example**:
```python
# Input: "../../etc/passwd"
path = Path("../../etc/passwd").resolve()  # Resolves to /etc/passwd
str(path)  # "/etc/passwd" - no ".." in string!
# Check passes incorrectly!
```

**Recommendation**:
```python
def sanitize_path(file_path: Union[str, Path], base_dir: Optional[Path] = None) -> Path:
    """Sanitize and validate a file path"""
    # Check original input FIRST, before resolve()
    path_str = str(file_path)
    if '..' in path_str or path_str.startswith('/') and not path_str.startswith(str(Path.home())):
        raise ValidationError(
            "Path contains directory traversal attempt",
            field="file_path",
            value=path_str
        )
    
    # Then resolve and check base directory
    path = Path(file_path).resolve()
    
    if base_dir:
        base_dir = Path(base_dir).resolve()
        try:
            path.relative_to(base_dir)
        except ValueError:
            raise ValidationError(
                f"Path {path} is outside allowed directory {base_dir}",
                field="file_path",
                value=str(file_path)
            )
    
    return path
```

---

### 2.4 🟠 HIGH: No File Extension Validation

**Location**: File loading operations  
**Risk**: Loading executable files, binary files

**Issue**: No validation of file extensions when loading files.

**Recommendation**:
```python
ALLOWED_FILE_EXTENSIONS = {
    '.txt', '.md', '.json', '.yaml', '.yml',
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.html', '.css', '.xml', '.csv'
}

def validate_file_extension(file_path: Path) -> None:
    """Validate file has allowed extension"""
    if file_path.suffix.lower() not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(
            f"File extension '{file_path.suffix}' not allowed",
            field="file_path"
        )
```

---

### 2.5 🟠 HIGH: No File Size Validation

**Location**: File loading operations  
**Risk**: Memory exhaustion, DoS

**Issue**: Files loaded without size checks.

**Recommendation**:
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_file_size(file_path: Path) -> None:
    """Validate file size"""
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValidationError(
            f"File too large ({size:,} bytes, max {MAX_FILE_SIZE:,})",
            field="file_path"
        )
```

---

### 2.6 🟡 MEDIUM: No File Existence Validation

**Location**: Some file operations  
**Risk**: Confusing error messages, crashes

**Issue**: Some operations don't check if file exists before use.

**Recommendation**: Add existence checks with clear error messages.

---

## 3. URL/Endpoint Validation

### 3.1 🔴 CRITICAL: No URL Validation for API Endpoints

**Location**: `tui_improved.py:1412`  
**Risk**: SSRF (Server-Side Request Forgery) attacks

**Issue**:
```python
# tui_improved.py:1412 - No validation
base_url = questionary.text("Base URL:", style=custom_style).ask()
if not base_url:
    return None

# Directly used in agent configuration
config["base_url"] = base_url
```

**Problem**: User can specify any URL, including:
- `http://localhost:8080` (internal services)
- `file:///etc/passwd` (local file access)
- `http://169.254.169.254/` (cloud metadata services)

**Recommendation**:
```python
from urllib.parse import urlparse
from ipaddress import ip_address, AddressValueError

def validate_api_endpoint(url: str) -> str:
    """Validate API endpoint URL"""
    if not url:
        raise ValidationError("Base URL cannot be empty", field="base_url")
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {e}", field="base_url")
    
    # Must be http or https
    if parsed.scheme not in ('http', 'https'):
        raise ValidationError(
            f"URL scheme must be http or https, got: {parsed.scheme}",
            field="base_url"
        )
    
    # Block localhost/internal IPs (unless explicitly allowed)
    hostname = parsed.hostname
    if hostname:
        # Check for localhost
        if hostname.lower() in ('localhost', '127.0.0.1', '::1'):
            # Allow localhost only for development
            import os
            if os.getenv('STARTD8_ALLOW_LOCALHOST') != 'true':
                raise ValidationError(
                    "Localhost URLs are not allowed for security reasons. "
                    "Set STARTD8_ALLOW_LOCALHOST=true to allow.",
                    field="base_url"
                )
        
        # Check for private/internal IPs
        try:
            ip = ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                if os.getenv('STARTD8_ALLOW_LOCALHOST') != 'true':
                    raise ValidationError(
                        "Private/internal IP addresses are not allowed",
                        field="base_url"
                    )
        except (ValueError, AddressValueError):
            # Not an IP, check hostname
            pass
    
    # Must have hostname
    if not parsed.hostname:
        raise ValidationError("URL must include a hostname", field="base_url")
    
    return url
```

**Files Affected**:
- `tui_improved.py:1412` - Custom endpoint base_url
- `tui_improved.py:1501` - Edit agent base_url
- `agents.py:841` - ComposerAgent default URL (already fixed)

---

### 3.2 🔴 CRITICAL: No URL Format Validation

**Location**: URL input locations  
**Risk**: Invalid URLs causing connection errors, crashes

**Issue**: URLs accepted without format validation.

**Recommendation**: Use `urlparse` to validate format before use.

---

### 3.3 🟠 HIGH: No Protocol Validation

**Location**: URL input locations  
**Risk**: Allowing dangerous protocols (file://, ftp://, etc.)

**Issue**: No check that URL uses http/https only.

**Recommendation**: See 3.1 above.

---

### 3.4 🟠 HIGH: No Hostname Validation

**Location**: URL input locations  
**Risk**: Invalid hostnames, typos leading to wrong endpoints

**Issue**: No validation of hostname format.

**Recommendation**: Validate hostname format (RFC 1123).

---

### 3.5 🟡 MEDIUM: No Port Validation

**Location**: URL input locations  
**Risk**: Invalid ports causing connection failures

**Issue**: Port numbers not validated (should be 1-65535).

**Recommendation**: Validate port range if specified.

---

## 4. Numeric Input Validation

### 4.1 🔴 CRITICAL: No Bounds Checking for max_tokens

**Location**: `tui_improved.py:1425-1433`  
**Risk**: Integer overflow, API errors, excessive costs

**Issue**:
```python
# tui_improved.py:1425-1433
max_tokens_str = questionary.text("Max tokens:", default="4096", style=custom_style).ask()
try:
    max_tokens = int(max_tokens_str) if max_tokens_str else 4096
except ValueError:
    max_tokens = 4096  # Silent failure - uses default
```

**Problems**:
1. No maximum limit (user could enter 999999999)
2. No minimum limit (user could enter 0 or negative)
3. Silent failure on invalid input
4. No validation that value is reasonable

**Recommendation**:
```python
MIN_MAX_TOKENS = 1
MAX_MAX_TOKENS = 1_000_000  # Reasonable upper limit

def validate_max_tokens(value_str: str) -> int:
    """Validate and convert max_tokens input"""
    if not value_str:
        return 4096  # Default
    
    try:
        value = int(value_str)
    except ValueError:
        raise ValidationError(
            f"Max tokens must be a number, got: {value_str}",
            field="max_tokens"
        )
    
    if value < MIN_MAX_TOKENS:
        raise ValidationError(
            f"Max tokens must be at least {MIN_MAX_TOKENS}",
            field="max_tokens"
        )
    
    if value > MAX_MAX_TOKENS:
        raise ValidationError(
            f"Max tokens cannot exceed {MAX_MAX_TOKENS:,}",
            field="max_tokens"
        )
    
    return value
```

**Files Affected**:
- `tui_improved.py:1425` - Custom agent max_tokens
- `tui_improved.py:1605` - Edit agent max_tokens
- `tui_improved.py:1364` - Provider agent max_tokens

---

### 4.2 🟠 HIGH: No Validation for Priority Values

**Location**: `tui_improved.py:4972+` (job file creation)  
**Risk**: Invalid priority values

**Issue**: Priority input not validated.

**Recommendation**: Validate priority is within allowed range (e.g., 1-10).

---

### 4.3 🟠 HIGH: No Validation for Timeout Values

**Location**: Various timeout inputs  
**Risk**: Invalid timeouts causing hangs or immediate failures

**Issue**: Timeout values not validated.

**Recommendation**: Validate timeout is positive and reasonable (e.g., 1-3600 seconds).

---

### 4.4 🟡 MEDIUM: No Validation for Version Numbers

**Location**: Version input (if any)  
**Risk**: Invalid version formats

**Issue**: While `Prompt` model validates semver format, TUI may not enforce it.

**Recommendation**: Use same validation in TUI as in model.

---

## 5. Model/Agent Name Validation

### 5.1 🔴 CRITICAL: No Injection Prevention in Model Names

**Location**: `tui_improved.py:1416, 1339, 1347`  
**Risk**: Command injection, path injection

**Issue**:
```python
# tui_improved.py:1416 - No validation
model = questionary.text("Model name:", style=custom_style).ask()
if not model:
    return None

# Directly used in config
config["model"] = model
```

**Problem**: Model name could contain:
- Special characters that break API calls
- Path separators (`/`, `\`)
- Shell metacharacters
- SQL injection attempts (if stored in DB later)

**Recommendation**:
```python
import re

MODEL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
MAX_MODEL_NAME_LENGTH = 100

def validate_model_name(name: str) -> str:
    """Validate model name format"""
    if not name:
        raise ValidationError("Model name cannot be empty", field="model")
    
    if len(name) > MAX_MODEL_NAME_LENGTH:
        raise ValidationError(
            f"Model name too long (max {MAX_MODEL_NAME_LENGTH} chars)",
            field="model"
        )
    
    if not MODEL_NAME_PATTERN.match(name):
        raise ValidationError(
            "Model name can only contain letters, numbers, dots, underscores, and hyphens",
            field="model"
        )
    
    return name
```

**Files Affected**:
- `tui_improved.py:1416` - Custom agent model
- `tui_improved.py:1339` - Provider agent model
- `tui_improved.py:1347` - Custom model input
- `tui_improved.py:1506` - Edit agent model

---

### 5.2 🟠 HIGH: No Validation for Agent Names

**Location**: `tui_improved.py:1408, 1355`  
**Risk**: Invalid names, conflicts, filesystem issues

**Issue**: Agent names not validated for format or conflicts.

**Recommendation**:
```python
AGENT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_AGENT_NAME_LENGTH = 50

def validate_agent_name(name: str, existing_names: List[str]) -> str:
    """Validate agent name"""
    if not name:
        raise ValidationError("Agent name cannot be empty", field="name")
    
    if len(name) > MAX_AGENT_NAME_LENGTH:
        raise ValidationError(
            f"Agent name too long (max {MAX_AGENT_NAME_LENGTH} chars)",
            field="name"
        )
    
    if not AGENT_NAME_PATTERN.match(name):
        raise ValidationError(
            "Agent name can only contain letters, numbers, underscores, and hyphens",
            field="name"
        )
    
    if name in existing_names:
        raise ValidationError(
            f"Agent name '{name}' already exists",
            field="name"
        )
    
    return name
```

---

### 5.3 🟡 MEDIUM: No Validation for Environment Variable Names

**Location**: `tui_improved.py:1420`  
**Risk**: Invalid env var names, injection

**Issue**: Environment variable names not validated.

**Recommendation**: Validate env var name format (uppercase, underscores, no spaces).

---

### 5.4 🟡 MEDIUM: No Validation for Tag Names

**Location**: Tag input locations  
**Risk**: Invalid tags, special characters

**Issue**: Tags not validated for format.

**Recommendation**: Validate tag format (alphanumeric, hyphens, underscores).

---

## 6. Additional Validation Issues

### 6.1 Missing Input Validation in CLI

**Location**: `cli.py`  
**Risk**: Command-line arguments not validated

**Issues**:
- File paths from CLI args not validated
- Template IDs not validated
- Project paths not validated

**Recommendation**: Add validation to all CLI argument handlers.

---

### 6.2 Missing Validation in Prompt Builder

**Location**: `tui_prompt_builder.py`  
**Risk**: Invalid template variables, paths

**Issues**:
- Template variable values not validated
- Path inputs not using `sanitize_path()`
- No validation of template structure

**Recommendation**: Add comprehensive validation to prompt builder wizard.

---

## Implementation Recommendations

### Phase 1: Critical Fixes (Immediate)

1. **Fix `sanitize_path()` bug** (security.py:45)
   - Check original input before resolve()
   - Add comprehensive tests

2. **Add URL validation** (tui_improved.py:1412)
   - Implement `validate_api_endpoint()` function
   - Use in all URL input locations

3. **Add prompt length limits** (tui_improved.py:4948)
   - Enforce 1MB limit in TUI
   - Add progress indicator for long inputs

4. **Add max_tokens bounds checking** (tui_improved.py:1425)
   - Implement `validate_max_tokens()` function
   - Use in all max_tokens inputs

5. **Use `sanitize_path()` everywhere** (all file path operations)
   - Replace direct `Path().resolve()` calls
   - Add base directory restrictions

### Phase 2: High Priority Fixes (Week 1)

6. **Add model/agent name validation**
   - Implement `validate_model_name()` and `validate_agent_name()`
   - Use in all name inputs

7. **Add file extension validation**
   - Implement `validate_file_extension()`
   - Use in file loading operations

8. **Add file size validation**
   - Implement `validate_file_size()`
   - Use in file loading operations

9. **Add content sanitization**
   - Implement `sanitize_prompt_content()`
   - Use before storing/using prompts

### Phase 3: Medium Priority Fixes (Week 2)

10. **Add comprehensive CLI validation**
11. **Add prompt builder validation**
12. **Add tag validation**
13. **Add environment variable name validation**

---

## Testing Recommendations

### Unit Tests Needed

```python
# test_input_validation.py

def test_sanitize_path_traversal():
    """Test directory traversal prevention"""
    with pytest.raises(ValidationError):
        sanitize_path("../../../etc/passwd")

def test_validate_api_endpoint_ssrf():
    """Test SSRF prevention"""
    with pytest.raises(ValidationError):
        validate_api_endpoint("http://localhost:8080")

def test_validate_max_tokens_bounds():
    """Test max_tokens bounds"""
    assert validate_max_tokens("4096") == 4096
    with pytest.raises(ValidationError):
        validate_max_tokens("999999999")
    with pytest.raises(ValidationError):
        validate_max_tokens("-1")

def test_validate_model_name_injection():
    """Test model name injection prevention"""
    with pytest.raises(ValidationError):
        validate_model_name("model/../../etc")
    with pytest.raises(ValidationError):
        validate_model_name("model; rm -rf /")
```

### Integration Tests Needed

- Test file loading with various invalid inputs
- Test URL input with SSRF attempts
- Test prompt creation with edge cases
- Test agent creation with invalid names/URLs

---

## Security Impact Assessment

### Critical Risks Mitigated

1. **Directory Traversal**: Fixed by proper path validation
2. **SSRF Attacks**: Fixed by URL validation
3. **DoS via Large Inputs**: Fixed by length limits
4. **Command Injection**: Fixed by name validation
5. **Memory Exhaustion**: Fixed by size limits

### Compliance Impact

- **OWASP Top 10**: Addresses A03:2021 (Injection), A04:2021 (Insecure Design)
- **CWE**: Addresses CWE-22 (Path Traversal), CWE-918 (SSRF), CWE-400 (DoS)

---

## Files Requiring Changes

### Critical Priority
1. `src/startd8/security.py` - Fix `sanitize_path()` bug
2. `src/startd8/tui_improved.py` - Add validation to ~15 locations
3. `src/startd8/framework.py` - Enforce Prompt model validation

### High Priority
4. `src/startd8/tui_prompt_builder.py` - Add path/content validation
5. `src/startd8/cli.py` - Add CLI argument validation

### Medium Priority
6. `src/startd8/models.py` - Enhance existing validators
7. Create `src/startd8/validation.py` - Centralized validation utilities

---

## Next Steps

1. ✅ Review complete - issues identified
2. ⬜ Create validation utility module
3. ⬜ Fix critical issues (Phase 1)
4. ⬜ Add comprehensive tests
5. ⬜ Update documentation
6. ⬜ Code review of fixes
7. ⬜ Deploy fixes

---

**Reviewer**: AI Code Reviewer  
**Status**: Ready for Implementation  
**Priority**: 🔴 Critical - Start Immediately
