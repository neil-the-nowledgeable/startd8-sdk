# Developer Guide: Using File Input Abstraction

**Quick Reference for Adding File Input to TUI Workflows**

---

## Overview

The `_get_text_or_file_input()` method provides a reusable way to get multiline text input from users with the option to load from files. This guide shows how to integrate it into your TUI workflows.

---

## Quick Start

### Basic Usage

```python
def your_menu_method(self):
    """Your workflow menu"""
    
    # Get input with file support
    content = self._get_text_or_file_input(
        title="Your Title Here",
        prompt_text="Your prompt:",
        description="Instructions for the user.",
        example="Example input",
        allow_empty=False
    )
    
    # Handle cancellation
    if not content:
        return
    
    # Use the content
    self._process_content(content)
```

---

## Method Signature

```python
def _get_text_or_file_input(
    self,
    title: str,                     # Required: Display title
    prompt_text: str,                # Required: Input prompt label
    description: Optional[str] = None,  # Optional: Help text
    example: Optional[str] = None,      # Optional: Example to show
    allow_empty: bool = False           # Optional: Allow empty input?
) -> Optional[str]:
    """Returns content string or None if cancelled"""
```

---

## Parameters Explained

### `title` (Required)
The header shown at the top.

**Examples:**
- `"Task Description"`
- `"Project Requirements"`
- `"Code Review Context"`
- `"Custom Prompt Template"`

### `prompt_text` (Required)
The label for the text input field.

**Examples:**
- `"Task:"`
- `"Requirements:"`
- `"Code:"`
- `"Prompt:"`

### `description` (Optional)
Help text explaining what the user should enter.

**Examples:**
- `"Describe what you want the developer agent to implement."`
- `"Enter project requirements or load from a file."`
- `"Paste code or load from file for review."`

### `example` (Optional)
A short example to guide the user.

**Examples:**
- `"Implement a function to validate email addresses with regex"`
- `"1. User authentication\n2. Dashboard with analytics"`
- `"def my_function():\n    pass"`

### `allow_empty` (Optional, default=False)
Whether to accept empty input.

**Use cases:**
- `False` (default) - Required input (task descriptions, prompts)
- `True` - Optional input (additional context, notes)

---

## Return Value

- **Returns**: `Optional[str]`
  - `str` - The content (from text input or file)
  - `None` - User cancelled or validation failed

**Always check for `None`:**
```python
content = self._get_text_or_file_input(...)
if not content:
    return  # User cancelled
```

---

## Real-World Examples

### Example 1: Task Description (Already Implemented)

```python
def _get_task_description(self) -> Optional[str]:
    """Get task description from user"""
    return self._get_text_or_file_input(
        title="Task Description",
        prompt_text="Task:",
        description="Describe what you want the developer agent to implement.",
        example="Implement a function to validate email addresses with regex",
        allow_empty=False
    )
```

### Example 2: Project Requirements

```python
def _get_project_requirements(self) -> Optional[str]:
    """Get project requirements from user or file"""
    return self._get_text_or_file_input(
        title="Project Requirements",
        prompt_text="Requirements:",
        description="Enter detailed project requirements.",
        example="1. User login system\n2. Dashboard with charts\n3. REST API",
        allow_empty=False
    )
```

### Example 3: Optional Context

```python
def _get_additional_context(self) -> Optional[str]:
    """Get optional additional context"""
    return self._get_text_or_file_input(
        title="Additional Context (Optional)",
        prompt_text="Context:",
        description="Provide any additional context or constraints.",
        example="Use Python 3.11+, follow PEP-8 style guide",
        allow_empty=True  # Optional!
    )
```

### Example 4: Code Input

```python
def _get_code_for_review(self) -> Optional[str]:
    """Get code to review"""
    return self._get_text_or_file_input(
        title="Code to Review",
        prompt_text="Code:",
        description="Paste code or load from a source file.",
        example="def calculate_total(items):\n    return sum(items)",
        allow_empty=False
    )
```

### Example 5: Custom Prompt Template

```python
def _get_custom_prompt_template(self) -> Optional[str]:
    """Get custom prompt template with placeholders"""
    return self._get_text_or_file_input(
        title="Custom Prompt Template",
        prompt_text="Template:",
        description="Enter a prompt template with {placeholder} syntax.",
        example="You are a {role}. Please {action} using {technology}.",
        allow_empty=False
    )
```

---

## Integration Checklist

When adding file input to a workflow:

- [ ] Identify where multiline text input is needed
- [ ] Replace `questionary.text()` with `_get_text_or_file_input()`
- [ ] Choose appropriate `title` and `prompt_text`
- [ ] Add helpful `description` and `example`
- [ ] Set `allow_empty` based on whether input is required
- [ ] Handle `None` return (user cancelled)
- [ ] Test both input methods (text and file)
- [ ] Update documentation

---

## Before and After

### Before (Old Way)

```python
def _get_some_input(self) -> Optional[str]:
    """Get input from user"""
    self.console.print("\n[bold]Enter Information:[/bold]\n")
    self.console.print("[dim]Provide the required information.[/dim]\n")
    
    content = questionary.text(
        "Input:",
        multiline=True,
        style=custom_style
    ).ask()
    
    if not content or not content.strip():
        self.console.print("[yellow]No content provided. Cancelled.[/yellow]")
        questionary.press_any_key_to_continue().ask()
        return None
    
    return content.strip()
```

**Problems:**
- ❌ No file loading support
- ❌ Manual validation logic
- ❌ Repetitive code
- ❌ Inconsistent UX

### After (New Way)

```python
def _get_some_input(self) -> Optional[str]:
    """Get input from user"""
    return self._get_text_or_file_input(
        title="Enter Information",
        prompt_text="Input:",
        description="Provide the required information.",
        example="Example input here",
        allow_empty=False
    )
```

**Benefits:**
- ✅ File loading included
- ✅ Built-in validation
- ✅ 80% less code
- ✅ Consistent UX
- ✅ Error handling included

---

## User Experience

### What Users See

1. **Choice Menu**
   ```
   Choose input method:
   > ✏️  Enter text directly
     📁 Load from file
     ← Cancel
   ```

2. **File Loading**
   - File browser with auto-completion
   - Content preview before confirming
   - Character count display

3. **Validation**
   - Empty input detection
   - File existence checks
   - UTF-8 encoding validation

---

## Error Handling

The method handles all common errors:

- ✅ File not found
- ✅ Not a regular file (is a directory)
- ✅ Unicode decode errors (binary files)
- ✅ Empty content validation
- ✅ User cancellation

**You don't need to add error handling** - it's all built in!

---

## Testing Your Integration

### Manual Test

1. Run your workflow in the TUI
2. When prompted, test both methods:
   - Enter text directly
   - Load from a test file
3. Try cancelling at different points
4. Try invalid file paths
5. Try empty input

### Test File

Create a test file:
```bash
echo "Test content for my workflow" > test_input.txt
```

Then load it in your workflow to verify it works.

---

## Common Patterns

### Pattern 1: Required Input

```python
content = self._get_text_or_file_input(
    title="Required Field",
    prompt_text="Input:",
    allow_empty=False  # Required
)

if not content:
    return  # User cancelled

# Use content
process(content)
```

### Pattern 2: Optional Input

```python
content = self._get_text_or_file_input(
    title="Optional Field",
    prompt_text="Input:",
    allow_empty=True  # Optional
)

# content might be None or empty string
if content:
    process(content)
else:
    # Continue without it
    use_defaults()
```

### Pattern 3: Multiple Inputs

```python
# Get first input
task = self._get_text_or_file_input(
    title="Task", 
    prompt_text="Task:",
    allow_empty=False
)
if not task:
    return

# Get second input
requirements = self._get_text_or_file_input(
    title="Requirements",
    prompt_text="Requirements:",
    allow_empty=True  # Optional
)

# Continue with both (requirements might be None)
process(task, requirements)
```

---

## Where to Use This

### ✅ Good Use Cases

- Task descriptions
- Project requirements
- Code snippets for review
- Prompt templates
- Configuration content
- Documentation text
- Test cases
- Instructions
- Any multiline text input

### ❌ Not Suitable For

- Single-line inputs (use `questionary.text()`)
- Numeric inputs (use custom validation)
- Multiple file selection (extend the method)
- Binary file content (only text files supported)
- Structured data (use JSON/YAML specific methods)

---

## Advanced: Customizing for Specific Needs

If you need file type filtering or other customizations, you can create a wrapper:

```python
def _get_python_code(self) -> Optional[str]:
    """Get Python code with .py file preference"""
    content = self._get_text_or_file_input(
        title="Python Code",
        prompt_text="Code:",
        description="Enter Python code or load from .py file.",
        example="def hello():\n    print('Hello')",
        allow_empty=False
    )
    
    # Optional: Add Python syntax validation
    if content:
        try:
            compile(content, '<string>', 'exec')
        except SyntaxError as e:
            self.console.print(f"[yellow]Warning: Syntax error: {e}[/yellow]")
            # Continue anyway or return None
    
    return content
```

---

## FAQ

### Q: Can users edit file content after loading?

**A:** Not currently, but you could add this by:
1. Loading the file content
2. Passing it as `default=content` to `questionary.text()`
3. Allowing user to edit before accepting

### Q: Can I load multiple files?

**A:** Not directly. You would need to:
1. Call the method multiple times
2. Concatenate the results

### Q: What file types are supported?

**A:** Any UTF-8 text file:
- `.txt`, `.md` (documentation)
- `.py`, `.js`, `.java` (code)
- `.json`, `.yaml`, `.xml` (config)
- Any text-based format

### Q: Is there a file size limit?

**A:** No hard limit in the method, but consider:
- LLM context limits (typically 100K-200K tokens)
- User experience with very long previews
- Memory constraints

### Q: Can I customize the preview length?

**A:** Currently 300 chars. To change, modify the method:
```python
preview = content[:500]  # Change 300 to 500
```

---

## Summary

The `_get_text_or_file_input()` abstraction provides:

✅ **Easy integration** - One method call  
✅ **Consistent UX** - Same experience across workflows  
✅ **File support** - Load from files automatically  
✅ **Error handling** - All edge cases covered  
✅ **Validation** - Empty input checks built-in  
✅ **Flexible** - Works for any text input need  

**Start using it in your workflows today!**

---

## Need Help?

See full documentation:
- `FILE_INPUT_FEATURE.md` - Complete feature documentation
- `src/startd8/tui_improved.py` - Implementation source code
- `test_task_example.txt` - Example input file

---

**Last Updated**: December 9, 2025  
**Implementation Status**: Production-ready
