# 🧪 Startd8 MCP Server - Comprehensive Test Plan

**Created:** December 8, 2025 (Evening)  
**Status:** Test Plan Draft - Ready for Implementation  
**Next Step:** Build out tests tomorrow morning

---

## Test Plan Overview

This test plan ensures the Startd8 MCP server is production-ready for Cursor integration and real-world usage. Tests are organized by phase, from basic functionality to complex integration scenarios.

---

## Phase 1: Basic Functionality Tests

### 1.1 Syntax and Import Validation

**Objective:** Verify code is syntactically correct and all dependencies available

**Tests:**
- [ ] **T1.1.1** - Python syntax validation (`py_compile`)
- [ ] **T1.1.2** - All imports resolve successfully
- [ ] **T1.1.3** - FastMCP server initializes without errors
- [ ] **T1.1.4** - Pydantic models validate correctly
- [ ] **T1.1.5** - YAML parser (PyYAML) works

**Implementation Stub:**
```python
# tests/test_01_basic.py
def test_syntax_validation():
    """Verify Python syntax is valid."""
    # Use py_compile to check syntax
    pass

def test_imports():
    """Verify all imports work."""
    # Try importing main modules
    # Check for ImportError
    pass

def test_server_initialization():
    """Verify FastMCP server initializes."""
    # Import and initialize mcp
    # Check server name, tools list
    pass
```

---

### 1.2 Skill Discovery Tests

**Objective:** Verify skill discovery works across different configurations

**Tests:**
- [ ] **T1.2.1** - Discover skills in default directories
- [ ] **T1.2.2** - Discover skills via `STARTD8_SKILL_PATH` env var
- [ ] **T1.2.3** - Handle missing skill directories gracefully
- [ ] **T1.2.4** - Parse YAML frontmatter correctly
- [ ] **T1.2.5** - Handle malformed SKILL.md files
- [ ] **T1.2.6** - Fallback to directory name when YAML missing
- [ ] **T1.2.7** - Skip directories without SKILL.md

**Implementation Stub:**
```python
# tests/test_02_skill_discovery.py
def test_default_directory_discovery():
    """Test skill discovery in default paths."""
    # Mock filesystem with test skills
    # Call _find_skills()
    # Assert correct skills found
    pass

def test_env_var_skill_path():
    """Test STARTD8_SKILL_PATH environment variable."""
    # Set env var to test directory
    # Verify skills discovered from custom path
    pass

def test_yaml_parsing():
    """Test YAML frontmatter parsing."""
    # Create test SKILL.md with frontmatter
    # Parse and verify metadata extracted
    pass
```

---

## Phase 2: Tool Functionality Tests

### 2.1 `startd8_list_skills` Tests

**Objective:** Verify skill listing works in all formats and scenarios

**Tests:**
- [ ] **T2.1.1** - List skills in Markdown format (default)
- [ ] **T2.1.2** - List skills in JSON format
- [ ] **T2.1.3** - List with `include_details=True`
- [ ] **T2.1.4** - List with `include_details=False`
- [ ] **T2.1.5** - Handle empty skill directories
- [ ] **T2.1.6** - Character limit truncation
- [ ] **T2.1.7** - Return helpful message when no skills found

**Implementation Stub:**
```python
# tests/test_03_list_skills.py
async def test_list_skills_markdown():
    """Test listing skills in markdown format."""
    # Create test input
    # Call startd8_list_skills
    # Assert markdown formatting
    # Verify all skills present
    pass

async def test_list_skills_json():
    """Test listing skills in JSON format."""
    # Create test input with JSON format
    # Call tool
    # Parse JSON response
    # Verify structure
    pass

async def test_character_limit_truncation():
    """Test truncation when output exceeds CHARACTER_LIMIT."""
    # Create many test skills
    # Call tool
    # Verify truncation message
    # Verify partial results returned
    pass
```

---

### 2.2 `startd8_get_skill_info` Tests

**Objective:** Verify skill detail retrieval works correctly

**Tests:**
- [ ] **T2.2.1** - Get skill info by exact name
- [ ] **T2.2.2** - Get skill info by directory name
- [ ] **T2.2.3** - Get skill info by partial name (fuzzy match)
- [ ] **T2.2.4** - Handle non-existent skill gracefully
- [ ] **T2.2.5** - Return full SKILL.md content
- [ ] **T2.2.6** - Format in Markdown correctly
- [ ] **T2.2.7** - Format in JSON correctly
- [ ] **T2.2.8** - Handle very large SKILL.md files (truncation)

**Implementation Stub:**
```python
# tests/test_04_get_skill_info.py
async def test_get_skill_by_exact_name():
    """Test retrieving skill by exact name."""
    # Setup test skill
    # Call tool with exact skill name
    # Verify correct skill returned
    pass

async def test_fuzzy_skill_matching():
    """Test partial name matching."""
    # Setup skill "html5-game-designer-pro"
    # Search for "html5"
    # Verify skill found
    pass

async def test_skill_not_found():
    """Test error handling for missing skill."""
    # Call with non-existent name
    # Verify error message
    # Verify suggestions provided
    pass
```

---

### 2.3 `startd8_use_skill` Tests

**Objective:** Verify skill-based generation works correctly

**Tests:**
- [ ] **T2.3.1** - Generate with valid skill and API key
- [ ] **T2.3.2** - Handle missing API key gracefully
- [ ] **T2.3.3** - Handle missing Anthropic SDK gracefully
- [ ] **T2.3.4** - Remove YAML frontmatter from instructions
- [ ] **T2.3.5** - Use correct Claude model
- [ ] **T2.3.6** - Respect max_tokens parameter
- [ ] **T2.3.7** - Format response with metadata
- [ ] **T2.3.8** - Handle API errors (rate limit, invalid key)
- [ ] **T2.3.9** - Handle skill not found

**Implementation Stub:**
```python
# tests/test_05_use_skill.py
@pytest.mark.integration
async def test_use_skill_success():
    """Test successful skill-based generation."""
    # Requires ANTHROPIC_API_KEY
    # Call with test skill and prompt
    # Verify response format
    # Verify token usage reported
    pass

async def test_missing_api_key():
    """Test error when API key not set."""
    # Unset ANTHROPIC_API_KEY
    # Call tool
    # Verify helpful error message
    pass

async def test_yaml_frontmatter_removal():
    """Test YAML frontmatter removed from instructions."""
    # Create skill with frontmatter
    # Mock API call to capture system prompt
    # Verify no '---' in system prompt
    pass
```

---

### 2.4 Input Validation Tests

**Objective:** Verify Pydantic models validate inputs correctly

**Tests:**
- [ ] **T2.4.1** - Reject empty skill names
- [ ] **T2.4.2** - Reject empty prompts
- [ ] **T2.4.3** - Enforce min/max length constraints
- [ ] **T2.4.4** - Enforce min/max value constraints (tokens)
- [ ] **T2.4.5** - Strip whitespace from string inputs
- [ ] **T2.4.6** - Validate enum values (ResponseFormat)
- [ ] **T2.4.7** - Reject extra fields (Pydantic strict mode)
- [ ] **T2.4.8** - Validate list constraints (min_items, max_items)

**Implementation Stub:**
```python
# tests/test_06_input_validation.py
def test_empty_skill_name_rejected():
    """Test empty skill name raises ValidationError."""
    # Try creating GetSkillInput with empty name
    # Assert ValidationError raised
    pass

def test_token_constraints():
    """Test max_tokens constraints."""
    # Try values < 1 and > 200000
    # Verify validation errors
    pass

def test_whitespace_stripping():
    """Test whitespace automatically stripped."""
    # Create input with leading/trailing spaces
    # Verify stripped in validated model
    pass
```

---

## Phase 3: MCP Protocol Tests

### 3.1 Tool Registration Tests

**Objective:** Verify tools are properly registered with MCP

**Tests:**
- [ ] **T3.1.1** - All 4 tools registered
- [ ] **T3.1.2** - Tool names correct (`startd8_*`)
- [ ] **T3.1.3** - Tool annotations present and correct
- [ ] **T3.1.4** - Tool descriptions comprehensive
- [ ] **T3.1.5** - Input schemas properly defined
- [ ] **T3.1.6** - Tools callable via MCP protocol

**Implementation Stub:**
```python
# tests/test_07_mcp_protocol.py
def test_all_tools_registered():
    """Verify all expected tools are registered."""
    # Get list of registered tools from mcp
    # Assert 4 tools present
    # Verify names
    pass

def test_tool_annotations():
    """Verify tool annotations are correct."""
    # Get tool metadata
    # Check readOnlyHint, destructiveHint, etc.
    pass
```

---

### 3.2 Resource Registration Tests

**Objective:** Verify resources are properly exposed

**Tests:**
- [ ] **T3.2.1** - `skill://{name}` resource registered
- [ ] **T3.2.2** - Resource returns skill content
- [ ] **T3.2.3** - Resource handles missing skills
- [ ] **T3.2.4** - Resource URI template works correctly

**Implementation Stub:**
```python
# tests/test_08_resources.py
async def test_skill_resource():
    """Test skill:// resource access."""
    # Call resource with skill name
    # Verify SKILL.md content returned
    pass

async def test_missing_skill_resource():
    """Test resource error handling."""
    # Call with non-existent skill
    # Verify error message
    pass
```

---

## Phase 4: Integration Tests

### 4.1 MCP Inspector Tests

**Objective:** Verify server works with MCP Inspector

**Tests:**
- [ ] **T4.1.1** - Server starts via MCP Inspector
- [ ] **T4.1.2** - All tools visible in Inspector UI
- [ ] **T4.1.3** - Tool inputs can be filled in UI
- [ ] **T4.1.4** - Tools execute successfully from UI
- [ ] **T4.1.5** - Resources browsable in UI
- [ ] **T4.1.6** - Server handles Inspector connection lifecycle

**Implementation Stub:**
```bash
# tests/manual_04_mcp_inspector.sh
#!/bin/bash
# Manual test with MCP Inspector

echo "Starting MCP Inspector..."
npx @modelcontextprotocol/inspector python3 startd8_mcp.py

# Follow manual test checklist:
# 1. Verify server connects
# 2. Check all tools listed
# 3. Test each tool
# 4. Browse resources
# 5. Verify error handling
```

---

### 4.2 Cursor Integration Tests

**Objective:** Verify server works with Cursor

**Tests:**
- [ ] **T4.2.1** - Server connects to Cursor
- [ ] **T4.2.2** - Cursor can list skills
- [ ] **T4.2.3** - Cursor can get skill info
- [ ] **T4.2.4** - Cursor can use skills for generation
- [ ] **T4.2.5** - Environment variables passed correctly
- [ ] **T4.2.6** - Server handles Cursor disconnection
- [ ] **T4.2.7** - Multiple requests work correctly

**Implementation Stub:**
```bash
# tests/manual_05_cursor_integration.sh
#!/bin/bash
# Manual test with Cursor

# Setup
cp cursor-mcp-config.json ~/.cursor/mcp.json

# Test checklist (manual):
# 1. Restart Cursor
# 2. Open chat
# 3. Ask: "What skills are available?"
# 4. Ask: "Show me the mcp-builder skill"
# 5. Ask: "Use html5-game-designer-pro to create a game"
# 6. Verify responses
# 7. Check for errors in Cursor logs
```

---

## Phase 5: Error Handling Tests

### 5.1 Graceful Degradation Tests

**Objective:** Verify server handles errors gracefully

**Tests:**
- [ ] **T5.1.1** - Missing dependencies handled
- [ ] **T5.1.2** - File system errors handled
- [ ] **T5.1.3** - API errors handled (Anthropic)
- [ ] **T5.1.4** - Invalid YAML handled
- [ ] **T5.1.5** - Permission errors handled
- [ ] **T5.1.6** - Network errors handled
- [ ] **T5.1.7** - All errors return helpful messages

**Implementation Stub:**
```python
# tests/test_09_error_handling.py
async def test_missing_anthropic_sdk():
    """Test error when anthropic package missing."""
    # Mock ImportError
    # Call startd8_use_skill
    # Verify helpful error message with install instructions
    pass

async def test_file_permission_error():
    """Test error when SKILL.md not readable."""
    # Mock permission error
    # Call get_skill_info
    # Verify graceful error handling
    pass

async def test_api_rate_limit():
    """Test API rate limit error handling."""
    # Mock rate limit error from Anthropic
    # Verify error message is actionable
    pass
```

---

## Phase 6: Performance Tests

### 6.1 Response Time Tests

**Objective:** Verify reasonable performance

**Tests:**
- [ ] **T6.1.1** - Skill discovery completes in <500ms
- [ ] **T6.1.2** - List skills completes in <1s
- [ ] **T6.1.3** - Get skill info completes in <200ms
- [ ] **T6.1.4** - Character limit check efficient
- [ ] **T6.1.5** - No blocking operations

**Implementation Stub:**
```python
# tests/test_10_performance.py
async def test_skill_discovery_performance():
    """Test skill discovery is fast enough."""
    import time
    start = time.time()
    skills = _find_skills()
    elapsed = time.time() - start
    assert elapsed < 0.5, f"Discovery took {elapsed}s"
    pass
```

---

### 6.2 Memory Tests

**Objective:** Verify no memory leaks or excessive usage

**Tests:**
- [ ] **T6.2.1** - Large SKILL.md files don't cause memory issues
- [ ] **T6.2.2** - Many skills don't exhaust memory
- [ ] **T6.2.3** - Character limit prevents memory overflow
- [ ] **T6.2.4** - Resource cleanup after errors

**Implementation Stub:**
```python
# tests/test_11_memory.py
async def test_large_skill_file_memory():
    """Test memory usage with very large SKILL.md."""
    # Create 10MB SKILL.md file
    # Load skill info
    # Verify memory usage reasonable
    # Verify truncation works
    pass
```

---

## Phase 7: Real-World Scenario Tests

### 7.1 End-to-End Workflow Tests

**Objective:** Test complete user workflows

**Tests:**
- [ ] **T7.1.1** - Discover → Info → Use workflow
- [ ] **T7.1.2** - Multiple skill usage in sequence
- [ ] **T7.1.3** - Skill not found → correction workflow
- [ ] **T7.1.4** - API key missing → setup workflow
- [ ] **T7.1.5** - Complex prompt with skill

**Implementation Stub:**
```python
# tests/test_12_workflows.py
async def test_full_skill_usage_workflow():
    """Test complete workflow from discovery to usage."""
    # 1. List skills
    # 2. Get specific skill info
    # 3. Use that skill with prompt
    # 4. Verify all steps work
    pass

async def test_skill_correction_workflow():
    """Test workflow when user specifies wrong skill name."""
    # 1. Try to get non-existent skill
    # 2. See suggestions in error
    # 3. Use correct name
    # 4. Verify works
    pass
```

---

## Test Data Setup

### Test Fixtures Needed

```python
# tests/fixtures.py

@pytest.fixture
def test_skills_directory(tmp_path):
    """Create temporary directory with test skills."""
    # Create skill-test-1/SKILL.md
    # Create skill-test-2/SKILL.md (with frontmatter)
    # Create skill-test-3/SKILL.md (without frontmatter)
    # Create skill-test-4/SKILL.md (malformed YAML)
    # Return tmp_path
    pass

@pytest.fixture
def mock_anthropic_api():
    """Mock Anthropic API responses."""
    # Mock successful response
    # Mock rate limit error
    # Mock invalid key error
    pass

@pytest.fixture
def test_env_vars():
    """Set up test environment variables."""
    # Set STARTD8_SKILL_PATH
    # Set ANTHROPIC_API_KEY (if available)
    # Clean up after test
    pass
```

---

## Test Organization

```
tests/
├── __init__.py
├── conftest.py                    # pytest configuration
├── fixtures.py                    # Shared test fixtures
├── test_01_basic.py               # Basic functionality
├── test_02_skill_discovery.py     # Skill discovery
├── test_03_list_skills.py         # List skills tool
├── test_04_get_skill_info.py      # Get skill info tool
├── test_05_use_skill.py           # Use skill tool
├── test_06_input_validation.py    # Pydantic validation
├── test_07_mcp_protocol.py        # MCP protocol compliance
├── test_08_resources.py           # MCP resources
├── test_09_error_handling.py      # Error scenarios
├── test_10_performance.py         # Performance tests
├── test_11_memory.py              # Memory tests
├── test_12_workflows.py           # E2E workflows
├── manual_04_mcp_inspector.sh     # Manual MCP Inspector test
└── manual_05_cursor_integration.sh # Manual Cursor test
```

---

## Test Execution Plan

### Quick Smoke Test (5 min)
```bash
python3 test_server.py
```

### Unit Tests (15 min)
```bash
pytest tests/test_01*.py tests/test_02*.py tests/test_03*.py
pytest tests/test_04*.py tests/test_05*.py tests/test_06*.py
```

### Integration Tests (30 min)
```bash
pytest tests/test_07*.py tests/test_08*.py tests/test_09*.py
pytest tests/test_10*.py tests/test_11*.py tests/test_12*.py -v
```

### Manual Tests (20 min)
```bash
./tests/manual_04_mcp_inspector.sh
./tests/manual_05_cursor_integration.sh
```

### Full Test Suite
```bash
pytest tests/ -v --cov=startd8_mcp --cov-report=html
```

---

## Success Criteria

- [ ] All unit tests pass (100%)
- [ ] All integration tests pass (100%)
- [ ] Manual MCP Inspector test successful
- [ ] Manual Cursor integration test successful
- [ ] Code coverage >80%
- [ ] No critical errors in error handling tests
- [ ] Performance tests meet targets
- [ ] Memory tests show no leaks

---

## Notes for Tomorrow Morning

1. **Start with:** Quick smoke test (`test_server.py`)
2. **Then build:** Unit tests (tests 01-06)
3. **Then try:** MCP Inspector integration
4. **Finally:** Cursor integration test
5. **Document:** Any issues found
6. **Iterate:** Fix and retest

---

## Implementation Priority

### High Priority (Do First)
- Phase 1: Basic Functionality Tests
- Phase 2: Tool Functionality Tests
- Phase 4.2: Cursor Integration (manual)

### Medium Priority (Do Second)
- Phase 3: MCP Protocol Tests
- Phase 4.1: MCP Inspector (manual)
- Phase 5: Error Handling Tests

### Low Priority (Nice to Have)
- Phase 6: Performance Tests
- Phase 7: Real-World Scenarios
- Memory tests

---

**Test plan saved and ready for implementation tomorrow morning! 🌙**
