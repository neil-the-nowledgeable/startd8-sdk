# Feature: Prompt Builder - Design Document

**Feature Name:** Prompt Builder  
**Author:** Claude (Sonnet 4)  
**Date:** December 4, 2025  
**Status:** Ready for Implementation  
**Priority:** High  
**Estimated Effort:** 8-12 hours

---

## 📖 User Stories

1. **As a developer**, I want to use pre-built prompt templates so that I can generate high-quality prompts without remembering all the required components.

2. **As a power user**, I want to create and save my own prompt templates so that I can standardize prompts across my team.

3. **As a new user**, I want a guided wizard that walks me through filling out a template so that I don't miss important sections.

---

## ✅ Requirements

### Functional Requirements

- [ ] FR-1: Load templates from built-in library (Python package)
- [ ] FR-2: Load templates from user directory (`~/.startd8/templates/`)
- [ ] FR-3: Merge built-in and user templates (user overrides built-in if same name)
- [ ] FR-4: Parse template placeholders in format `{{VARIABLE_NAME}}`
- [ ] FR-5: Support default values: `{{VARIABLE|default="value"}}`
- [ ] FR-6: Interactive sequential wizard in TUI showing:
  - Completed entries (with values)
  - Current entry (active input)
  - Upcoming entries (preview)
- [ ] FR-7: Interactive form view in TUI (all fields visible)
- [ ] FR-8: Auto-populate variables from project directory structure
- [ ] FR-9: Preview generated prompt before finalizing
- [ ] FR-10: Include two initial templates:
  - `design_document` (full template)
  - `project_plan` (placeholder scaffold)

### Non-Functional Requirements

- [ ] NFR-1: Template parsing < 100ms
- [ ] NFR-2: Graceful handling of malformed templates
- [ ] NFR-3: Clear error messages for missing required variables
- [ ] NFR-4: Works without questionary (CLI fallback mode)

### Critical Business Logic

- **Template Priority:** User templates in `~/.startd8/templates/` override built-in templates with the same name
- **Required vs Optional:** Variables without defaults are required; variables with defaults are optional
- **Project Context:** Auto-fill only populates suggestions; user can override all values

---

## 📐 Data Structures

### PromptTemplate

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
from pathlib import Path

class TemplateVariable(BaseModel):
    """A variable placeholder in a template"""
    name: str = Field(description="Variable name (e.g., 'PROJECT_PATH')")
    description: str = Field(default="", description="Help text for user")
    default: Optional[str] = Field(default=None, description="Default value if not provided")
    required: bool = Field(default=True, description="Whether this variable must be filled")
    input_type: str = Field(default="text", description="Input type: text, path, select, multiline")
    options: List[str] = Field(default_factory=list, description="Options for 'select' type")
    order: int = Field(default=0, description="Display order in wizard")
    
    @property
    def is_optional(self) -> bool:
        return self.default is not None or not self.required


class TemplateSource(str, Enum):
    """Where the template came from"""
    BUILTIN = "builtin"
    USER = "user"


class PromptTemplate(BaseModel):
    """A reusable prompt template"""
    id: str = Field(description="Unique identifier (e.g., 'design_document')")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="What this template is for")
    category: str = Field(default="general", description="Template category")
    version: str = Field(default="1.0.0", description="Template version")
    content: str = Field(description="Template content with {{VARIABLE}} placeholders")
    variables: List[TemplateVariable] = Field(default_factory=list)
    source: TemplateSource = Field(default=TemplateSource.BUILTIN)
    file_path: Optional[Path] = Field(default=None, description="Path if loaded from file")
    
    class Config:
        use_enum_values = True


class TemplateContext(BaseModel):
    """Context for filling a template"""
    project_path: Optional[Path] = Field(default=None)
    project_structure: Dict[str, Any] = Field(default_factory=dict)
    variable_values: Dict[str, str] = Field(default_factory=dict)
    auto_filled: Dict[str, str] = Field(default_factory=dict, description="Variables auto-filled from context")


class GeneratedPrompt(BaseModel):
    """Result of filling a template"""
    template_id: str
    template_name: str
    content: str = Field(description="The final generated prompt text")
    variables_used: Dict[str, str] = Field(description="Variable name -> value mapping")
    generated_at: str = Field(description="ISO timestamp")
    word_count: int
    line_count: int
```

### Template File Format

```yaml
# ~/.startd8/templates/my_template.yaml
id: my_custom_template
name: My Custom Template
description: A template for my specific use case
category: custom
version: 1.0.0
variables:
  - name: PROJECT_NAME
    description: Name of the project
    required: true
    input_type: text
    order: 1
  - name: LANGUAGE
    description: Programming language
    input_type: select
    options: [Python, TypeScript, Go, Rust]
    default: Python
    order: 2
content: |
  ## Task: Create {{PROJECT_NAME}}
  
  Language: {{LANGUAGE}}
  
  ### Requirements
  ...
```

---

## ⚙️ Configuration

```python
# src/startd8/prompt_builder/config.py

from pathlib import Path
from typing import Dict, Any

PROMPT_BUILDER_CONFIG = {
    # Template locations
    "builtin_templates_dir": Path(__file__).parent / "templates",
    "user_templates_dir": Path.home() / ".startd8" / "templates",
    
    # Placeholder syntax
    "placeholder_pattern": r"\{\{(\w+)(?:\|default=\"([^\"]*)\")?\}\}",
    
    # Auto-fill settings
    "auto_fill_enabled": True,
    "max_dir_scan_depth": 3,
    
    # File patterns to detect project type
    "project_indicators": {
        "python": ["setup.py", "pyproject.toml", "requirements.txt"],
        "typescript": ["package.json", "tsconfig.json"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
    },
    
    # Display settings
    "wizard_show_future_steps": True,
    "wizard_show_completed_steps": True,
}
```

---

## 🏗️ Architecture

### Module Structure

```
src/startd8/
├── prompt_builder/
│   ├── __init__.py
│   ├── config.py           # Configuration constants
│   ├── models.py           # Data models (PromptTemplate, TemplateVariable, etc.)
│   ├── parser.py           # Template parsing and placeholder extraction
│   ├── loader.py           # Load templates from builtin + user directories
│   ├── context.py          # Project context detection and auto-fill
│   ├── generator.py        # Fill templates and generate prompts
│   └── templates/          # Built-in templates
│       ├── design_document.yaml
│       └── project_plan.yaml
├── tui_prompt_builder.py   # TUI integration (wizard + form views)
└── cli.py                  # CLI commands (add prompt-builder commands)
```

### Class Diagram

```
┌─────────────────────┐     ┌──────────────────────┐
│   TemplateLoader    │────▶│   PromptTemplate     │
│                     │     │   - id               │
│ + load_builtin()    │     │   - name             │
│ + load_user()       │     │   - content          │
│ + list_templates()  │     │   - variables[]      │
└─────────────────────┘     └──────────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────┐     ┌──────────────────────┐
│   TemplateParser    │     │  TemplateVariable    │
│                     │     │   - name             │
│ + extract_vars()    │     │   - default          │
│ + validate()        │     │   - required         │
└─────────────────────┘     │   - input_type       │
          │                 └──────────────────────┘
          ▼
┌─────────────────────┐     ┌──────────────────────┐
│  ProjectContext     │────▶│   TemplateContext    │
│                     │     │   - project_path     │
│ + scan_directory()  │     │   - project_structure│
│ + detect_type()     │     │   - variable_values  │
│ + suggest_values()  │     │   - auto_filled      │
└─────────────────────┘     └──────────────────────┘
          │
          ▼
┌─────────────────────┐     ┌──────────────────────┐
│  PromptGenerator    │────▶│   GeneratedPrompt    │
│                     │     │   - content          │
│ + fill_template()   │     │   - variables_used   │
│ + preview()         │     │   - word_count       │
└─────────────────────┘     └──────────────────────┘
```

---

## 💻 Implementation

### TemplateLoader

```python
# src/startd8/prompt_builder/loader.py

from pathlib import Path
from typing import List, Dict, Optional
import yaml
import json

from .models import PromptTemplate, TemplateVariable, TemplateSource
from .config import PROMPT_BUILDER_CONFIG


class TemplateLoader:
    """Load and manage prompt templates"""
    
    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None
    ):
        self.builtin_dir = builtin_dir or PROMPT_BUILDER_CONFIG["builtin_templates_dir"]
        self.user_dir = user_dir or PROMPT_BUILDER_CONFIG["user_templates_dir"]
        self._cache: Dict[str, PromptTemplate] = {}
    
    def load_builtin_templates(self) -> Dict[str, PromptTemplate]:
        """Load all built-in templates"""
        templates = {}
        
        if not self.builtin_dir.exists():
            return templates
        
        for file_path in self.builtin_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(file_path, TemplateSource.BUILTIN)
                templates[template.id] = template
            except Exception as e:
                # Log error but continue loading other templates
                print(f"Warning: Failed to load {file_path}: {e}")
        
        return templates
    
    def load_user_templates(self) -> Dict[str, PromptTemplate]:
        """Load all user-defined templates"""
        templates = {}
        
        if not self.user_dir.exists():
            return templates
        
        for file_path in self.user_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(file_path, TemplateSource.USER)
                templates[template.id] = template
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")
        
        return templates
    
    def list_templates(self, refresh: bool = False) -> List[PromptTemplate]:
        """
        List all available templates.
        User templates override builtin templates with same ID.
        """
        if refresh or not self._cache:
            # Load builtin first, then user (user overrides)
            self._cache = self.load_builtin_templates()
            user_templates = self.load_user_templates()
            self._cache.update(user_templates)
        
        return sorted(self._cache.values(), key=lambda t: (t.category, t.name))
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """Get a specific template by ID"""
        if not self._cache:
            self.list_templates()
        return self._cache.get(template_id)
    
    def _load_template_file(
        self, 
        file_path: Path, 
        source: TemplateSource
    ) -> PromptTemplate:
        """Load a single template from file"""
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Convert variable dicts to TemplateVariable objects
        variables = []
        for var_data in data.get('variables', []):
            variables.append(TemplateVariable(**var_data))
        
        return PromptTemplate(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            category=data.get('category', 'general'),
            version=data.get('version', '1.0.0'),
            content=data['content'],
            variables=variables,
            source=source,
            file_path=file_path
        )
```

### ProjectContext

```python
# src/startd8/prompt_builder/context.py

from pathlib import Path
from typing import Dict, Any, Optional, List
import os

from .config import PROMPT_BUILDER_CONFIG


class ProjectContext:
    """Detect project context and suggest variable values"""
    
    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._structure: Dict[str, Any] = {}
        self._project_type: Optional[str] = None
    
    def scan_directory(self, max_depth: int = None) -> Dict[str, Any]:
        """
        Scan project directory structure.
        Returns nested dict of directories and files.
        """
        if max_depth is None:
            max_depth = PROMPT_BUILDER_CONFIG["max_dir_scan_depth"]
        
        self._structure = self._scan_recursive(self.project_path, max_depth)
        return self._structure
    
    def _scan_recursive(self, path: Path, depth: int) -> Dict[str, Any]:
        """Recursively scan directory"""
        if depth <= 0 or not path.is_dir():
            return {}
        
        result = {
            "_type": "directory",
            "_files": [],
            "_dirs": []
        }
        
        try:
            for item in sorted(path.iterdir()):
                # Skip hidden files and common ignore patterns
                if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', 'venv', '.git']:
                    continue
                
                if item.is_file():
                    result["_files"].append(item.name)
                elif item.is_dir():
                    result["_dirs"].append(item.name)
                    result[item.name] = self._scan_recursive(item, depth - 1)
        except PermissionError:
            pass
        
        return result
    
    def detect_project_type(self) -> Optional[str]:
        """Detect project type based on indicator files"""
        if self._project_type:
            return self._project_type
        
        indicators = PROMPT_BUILDER_CONFIG["project_indicators"]
        
        for project_type, files in indicators.items():
            for indicator_file in files:
                if (self.project_path / indicator_file).exists():
                    self._project_type = project_type
                    return project_type
        
        return None
    
    def suggest_values(self) -> Dict[str, str]:
        """
        Generate suggested values for common template variables.
        Based on project directory analysis.
        """
        suggestions = {}
        
        # Always suggest project path
        suggestions["PROJECT_PATH"] = str(self.project_path)
        suggestions["PATH"] = str(self.project_path)
        
        # Project name from directory
        suggestions["PROJECT_NAME"] = self.project_path.name
        
        # Detect language/type
        project_type = self.detect_project_type()
        if project_type:
            suggestions["LANGUAGE"] = project_type.capitalize()
            suggestions["PROJECT_TYPE"] = project_type
        
        # Scan structure if not done
        if not self._structure:
            self.scan_directory()
        
        # Suggest source directory
        common_src_dirs = ['src', 'lib', 'app', 'source']
        for src_dir in common_src_dirs:
            if src_dir in self._structure.get("_dirs", []):
                suggestions["SOURCE_DIR"] = src_dir
                suggestions["SRC_DIR"] = src_dir
                break
        
        # Count files for context
        file_count = len(self._structure.get("_files", []))
        dir_count = len(self._structure.get("_dirs", []))
        suggestions["FILE_COUNT"] = str(file_count)
        suggestions["DIR_COUNT"] = str(dir_count)
        
        return suggestions
```

### PromptGenerator

```python
# src/startd8/prompt_builder/generator.py

import re
from datetime import datetime
from typing import Dict, Optional

from .models import PromptTemplate, TemplateContext, GeneratedPrompt
from .config import PROMPT_BUILDER_CONFIG


class PromptGenerator:
    """Fill templates and generate final prompts"""
    
    def __init__(self):
        self.placeholder_pattern = re.compile(
            PROMPT_BUILDER_CONFIG["placeholder_pattern"]
        )
    
    def extract_variables(self, template: PromptTemplate) -> Dict[str, Optional[str]]:
        """
        Extract all variables from template content.
        Returns dict of variable_name -> default_value (or None)
        """
        matches = self.placeholder_pattern.findall(template.content)
        
        variables = {}
        for match in matches:
            var_name = match[0]
            default_value = match[1] if len(match) > 1 and match[1] else None
            variables[var_name] = default_value
        
        return variables
    
    def validate_context(
        self, 
        template: PromptTemplate, 
        context: TemplateContext
    ) -> Dict[str, str]:
        """
        Validate that all required variables are provided.
        Returns dict of variable_name -> error_message for any issues.
        """
        errors = {}
        extracted = self.extract_variables(template)
        
        for var in template.variables:
            if var.required and var.name not in context.variable_values:
                # Check if there's a default
                if var.default is None and extracted.get(var.name) is None:
                    errors[var.name] = f"Required variable '{var.name}' is missing"
        
        return errors
    
    def fill_template(
        self, 
        template: PromptTemplate, 
        context: TemplateContext
    ) -> GeneratedPrompt:
        """
        Fill template with provided values.
        Uses defaults for any missing optional variables.
        """
        content = template.content
        variables_used = {}
        
        # Find all placeholders and replace
        def replace_placeholder(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) else ""
            
            # Priority: provided value > auto-filled > default
            if var_name in context.variable_values:
                value = context.variable_values[var_name]
            elif var_name in context.auto_filled:
                value = context.auto_filled[var_name]
            else:
                value = default_value
            
            variables_used[var_name] = value
            return value
        
        content = self.placeholder_pattern.sub(replace_placeholder, content)
        
        return GeneratedPrompt(
            template_id=template.id,
            template_name=template.name,
            content=content,
            variables_used=variables_used,
            generated_at=datetime.utcnow().isoformat(),
            word_count=len(content.split()),
            line_count=content.count('\n') + 1
        )
    
    def preview(
        self, 
        template: PromptTemplate, 
        context: TemplateContext,
        max_length: int = 500
    ) -> str:
        """Generate a preview of the filled template"""
        result = self.fill_template(template, context)
        
        if len(result.content) <= max_length:
            return result.content
        
        return result.content[:max_length] + f"\n\n... ({result.word_count} words total)"
```

---

## 🎨 TUI Integration

### Sequential Wizard View

```python
# src/startd8/tui_prompt_builder.py (partial)

class PromptBuilderWizard:
    """Sequential wizard for filling prompt templates"""
    
    def __init__(self, template: PromptTemplate, context: TemplateContext):
        self.template = template
        self.context = context
        self.current_step = 0
        self.values: Dict[str, str] = {}
        
        # Sort variables by order
        self.variables = sorted(
            template.variables,
            key=lambda v: v.order
        )
    
    def render_progress(self) -> str:
        """
        Render progress indicator showing:
        - Completed steps (with values)
        - Current step (highlighted)
        - Future steps (dimmed)
        """
        lines = []
        total = len(self.variables)
        
        for i, var in enumerate(self.variables):
            step_num = i + 1
            
            if i < self.current_step:
                # Completed - show with value
                value = self.values.get(var.name, var.default or "")
                display_value = value[:30] + "..." if len(value) > 30 else value
                lines.append(f"  [green]✓ {step_num}. {var.name}:[/green] {display_value}")
            
            elif i == self.current_step:
                # Current - highlighted
                lines.append(f"  [cyan bold]▶ {step_num}. {var.name}[/cyan bold] [dim](current)[/dim]")
            
            else:
                # Future - dimmed
                optional = "[dim](optional)[/dim]" if var.is_optional else ""
                lines.append(f"  [dim]○ {step_num}. {var.name} {optional}[/dim]")
        
        return "\n".join(lines)
    
    def render_current_step(self) -> Panel:
        """Render the current step input panel"""
        var = self.variables[self.current_step]
        
        # Build help text
        help_text = var.description or f"Enter value for {var.name}"
        if var.default:
            help_text += f"\n[dim]Default: {var.default}[/dim]"
        if var.name in self.context.auto_filled:
            help_text += f"\n[cyan]Suggested: {self.context.auto_filled[var.name]}[/cyan]"
        
        return Panel(
            help_text,
            title=f"Step {self.current_step + 1} of {len(self.variables)}: {var.name}",
            border_style="cyan"
        )
```

### Wizard Display Layout

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Prompt Builder - Design Document Template                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Progress:
  ✓ 1. PROJECT_PATH: /Users/neil/myproject
  ✓ 2. FEATURE_NAME: High Score Storage
  ▶ 3. PRIORITY (current)
  ○ 4. ESTIMATED_EFFORT (optional)
  ○ 5. INCLUDE_TESTING
  ○ 6. INCLUDE_ACCESSIBILITY

┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3 of 6: PRIORITY                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ Select the priority level for this feature                                   │
│                                                                              │
│ Suggested: High                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

? Select priority: (Use arrow keys)
 ❯ High
   Medium
   Low

[Enter] Select  [↑↓] Navigate  [Esc] Back  [Ctrl+C] Cancel
```

### Form View Layout

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Prompt Builder - Design Document Template                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│ Template Variables                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PROJECT_PATH     │ /Users/neil/myproject          │ ✓ auto-filled          │
│  FEATURE_NAME     │ High Score Storage             │ ✓ entered              │
│  PRIORITY         │ [High ▼]                       │   select               │
│  ESTIMATED_EFFORT │ 2-3 hours                      │   (optional)           │
│  INCLUDE_TESTING  │ [✓]                            │   checkbox             │
│  INCLUDE_ACCESS   │ [✓]                            │   checkbox             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Preview (first 10 lines)                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ ## Task: Create Feature Design Documents                                     │
│                                                                              │
│ ### Context                                                                  │
│ Review the project requirements at /Users/neil/myproject...                  │
│                                                                              │
│ ... (428 words total)                                                        │
└─────────────────────────────────────────────────────────────────────────────┘

[Tab] Next Field  [Shift+Tab] Previous  [F2] Preview Full  [Enter] Generate  [Esc] Cancel
```

---

## 📄 Built-in Templates

### design_document.yaml

```yaml
# src/startd8/prompt_builder/templates/design_document.yaml

id: design_document
name: Design Document Prompt
description: Generate a comprehensive design document for a software feature
category: documentation
version: 1.0.0

variables:
  - name: PATH
    description: Path to the project or feature directory
    required: true
    input_type: path
    order: 1
  
  - name: FEATURE_NAME
    description: Name of the feature being designed
    required: true
    input_type: text
    order: 2
  
  - name: PRIORITY
    description: Priority level of the feature
    input_type: select
    options: [High, Medium, Low]
    default: Medium
    order: 3
  
  - name: ESTIMATED_EFFORT
    description: Estimated implementation effort
    input_type: text
    default: "2-4 hours"
    order: 4
  
  - name: TARGET_LANGUAGE
    description: Primary programming language
    input_type: select
    options: [TypeScript, Python, Go, Rust, Other]
    default: TypeScript
    order: 5

content: |
  ## Task: Create Feature Design Documents

  ### Context
  Review the project requirements at {{PATH}} to understand the feature scope.

  ### Output Requirements
  Create a separate .md file for each feature with the following structure:

  ---

  #### Required Sections (in this order):

  1. **Header**
     - Feature name, author/agent name, date, status, priority
     - Estimated effort (hours)

  2. **User Stories** (2-4 stories)
     - "As a [role], I want [goal] so that [benefit]"
     - Cover: end user, competitive player, developer perspectives

  3. **Requirements**
     - Functional requirements (numbered, with ✅ checkboxes)
     - Non-functional requirements (performance, accessibility, browser support)
     - **Critical business logic** - explicitly state any restrictions or guards
       (e.g., "High scores only count for games starting at Level 1")

  4. **Data Structure**
     - {{TARGET_LANGUAGE}} interface with inline comments
     - Include ALL fields needed for business logic
     - Explain why each field exists

  5. **Configuration**
     - Create a config file approach (e.g., `featureConfig.ts`)
     - Expose constants for future extensibility
     - Support analytics hooks where applicable

  6. **Implementation**
     - Custom hook with full {{TARGET_LANGUAGE}} code
     - Include validation logic for loaded data
     - Handle error cases gracefully
     - Use appropriate performance optimization patterns

  7. **UI/UX Design**
     - Component code examples
     - **Accessibility requirements:**
       - `aria-live` regions for dynamic content
       - Contrast ratio ≥ 4.5:1
       - Screen reader considerations
     - **UX enhancements:**
       - Delta/difference displays where applicable
       - Animations for key moments (e.g., pulse on achievement)
       - Empty state messaging
     - CSS with responsive design (`clamp()`, rem units)

  8. **Integration**
     - How this feature integrates with existing code
     - Code example showing integration points
     - State management approach

  9. **Testing Plan**
     - Unit test examples (actual code, not just descriptions)
     - Manual test scenarios (numbered, specific steps)
     - Edge cases list (minimum 6 cases)
     - Accessibility test cases

  10. **Definition of Done** (checklist format)
      - [ ] Core functionality works
      - [ ] Edge cases handled
      - [ ] Accessibility verified
      - [ ] Cross-browser tested
      - [ ] Performance verified
      - [ ] Documentation complete

  11. **Files to Create/Modify**
      - List with (NEW) or (MODIFY) tags
      - Brief description of changes

  12. **Notes Section**
      - Explain "why" decisions were made
      - Rationale for technical choices
      - Future enhancement possibilities

  13. **Out of Scope**
      - Explicitly list what is NOT included
      - Prevent scope creep

  ---

  ### Quality Standards

  - **Code must be copy-paste ready** - full implementations, not pseudocode
  - **Validate all loaded data** - type checking, corruption handling
  - **Include versioned storage keys** if using browser storage
  - **Handle skip/cancel flows** where user input is optional

  ### Critical Requirements Checklist
  Before finalizing, verify the design includes:
  - [ ] All business logic guards explicitly stated
  - [ ] Data validation on load
  - [ ] Error handling with graceful degradation
  - [ ] Accessibility (aria-live, contrast)
  - [ ] Configuration abstraction
  - [ ] Unit test code examples
  - [ ] Definition of Done checklist

  ---

  ### Output Format
  - One .md file per feature
  - Filename: `FEATURE_X_[NAME]_DESIGN.md`
  - Include agent/model name in header
  - Target length: 300-500 lines per feature
```

### project_plan.yaml (Placeholder)

```yaml
# src/startd8/prompt_builder/templates/project_plan.yaml

id: project_plan
name: Project Plan Prompt
description: Generate a high-level project plan (placeholder template)
category: planning
version: 1.0.0

variables:
  - name: PROJECT_NAME
    description: Name of the project
    required: true
    input_type: text
    order: 1
  
  - name: PROJECT_PATH
    description: Path to the project directory
    required: false
    input_type: path
    order: 2
  
  - name: TIMELINE
    description: Expected timeline
    input_type: select
    options: [1 week, 2 weeks, 1 month, 3 months]
    default: "2 weeks"
    order: 3

content: |
  ## Task: Create Project Plan for {{PROJECT_NAME}}

  ### Context
  {{PROJECT_PATH|default="Review the project requirements"}}

  ### Output Requirements
  Create a project plan document with the following sections:

  ---

  #### Required Sections:

  1. **Executive Summary**
     - [Section content to be defined]

  2. **Goals & Objectives**
     - [Section content to be defined]

  3. **Scope**
     - [Section content to be defined]

  4. **Timeline: {{TIMELINE}}**
     - [Section content to be defined]

  5. **Resources**
     - [Section content to be defined]

  6. **Risks & Mitigations**
     - [Section content to be defined]

  7. **Success Criteria**
     - [Section content to be defined]

  ---

  *This is a placeholder template. Expand sections as needed.*
```

---

## 🔌 CLI Integration

### New Commands

```python
# Add to cli.py

@app.command()
def templates(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category")
):
    """List available prompt templates"""
    from .prompt_builder.loader import TemplateLoader
    
    loader = TemplateLoader()
    templates = loader.list_templates()
    
    if category:
        templates = [t for t in templates if t.category == category]
    
    table = Table(title="Available Templates")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Category", style="green")
    table.add_column("Source", style="magenta")
    table.add_column("Description")
    
    for template in templates:
        table.add_row(
            template.id,
            template.name,
            template.category,
            template.source,
            template.description[:50] + "..." if len(template.description) > 50 else template.description
        )
    
    console.print(table)


@app.command()
def build_prompt(
    template_id: str = typer.Argument(..., help="Template ID to use"),
    project_path: Optional[Path] = typer.Option(None, "--project", "-p", help="Project path for context"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Use interactive wizard"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save prompt to file")
):
    """Build a prompt from a template"""
    from .prompt_builder.loader import TemplateLoader
    from .prompt_builder.context import ProjectContext
    from .prompt_builder.generator import PromptGenerator
    
    loader = TemplateLoader()
    template = loader.get_template(template_id)
    
    if not template:
        console.print(f"❌ Template '{template_id}' not found", style="red")
        raise typer.Exit(1)
    
    # Get project context
    context_scanner = ProjectContext(project_path or Path.cwd())
    suggestions = context_scanner.suggest_values()
    
    if interactive:
        # Launch TUI wizard
        from .tui_prompt_builder import run_prompt_builder_wizard
        result = run_prompt_builder_wizard(template, suggestions)
    else:
        # Use suggestions as values
        from .prompt_builder.models import TemplateContext
        context = TemplateContext(
            project_path=project_path,
            variable_values=suggestions
        )
        generator = PromptGenerator()
        result = generator.fill_template(template, context)
    
    # Output result
    console.print(Panel(result.content, title="Generated Prompt"))
    console.print(f"\n📊 {result.word_count} words, {result.line_count} lines")
    
    if output:
        with open(output, 'w') as f:
            f.write(result.content)
        console.print(f"✅ Saved to {output}", style="green")
```

### TUI Menu Integration

Add to `main_menu()` in `tui_improved.py`:

```python
# Add to WORKFLOW section
choices.append("📝 Prompt Builder")

# Handle in run() method
elif "Prompt Builder" in choice:
    self.prompt_builder_menu()
```

---

## ✅ Definition of Done

- [ ] TemplateLoader loads built-in and user templates
- [ ] User templates override built-in templates with same ID
- [ ] TemplateParser extracts variables from `{{VAR}}` and `{{VAR|default="x"}}` syntax
- [ ] ProjectContext scans directory and suggests variable values
- [ ] PromptGenerator fills templates and produces GeneratedPrompt
- [ ] TUI wizard shows completed, current, and future steps
- [ ] TUI form view shows all fields at once
- [ ] `design_document` template matches provided specification
- [ ] `project_plan` template has scaffold structure
- [ ] CLI `templates` command lists available templates
- [ ] CLI `build-prompt` command generates prompts
- [ ] Error handling for malformed templates
- [ ] Works without questionary (graceful degradation)

---

## 📁 Files to Create

| File | Description |
|------|-------------|
| `src/startd8/prompt_builder/__init__.py` | Module init, exports |
| `src/startd8/prompt_builder/config.py` | Configuration constants |
| `src/startd8/prompt_builder/models.py` | Pydantic data models |
| `src/startd8/prompt_builder/parser.py` | Template parsing logic |
| `src/startd8/prompt_builder/loader.py` | Template loading (builtin + user) |
| `src/startd8/prompt_builder/context.py` | Project context detection |
| `src/startd8/prompt_builder/generator.py` | Template filling |
| `src/startd8/prompt_builder/templates/design_document.yaml` | Built-in template |
| `src/startd8/prompt_builder/templates/project_plan.yaml` | Placeholder template |
| `src/startd8/tui_prompt_builder.py` | TUI wizard and form views |

## 📁 Files to Modify

| File | Changes |
|------|---------|
| `src/startd8/cli.py` | Add `templates` and `build-prompt` commands |
| `src/startd8/tui_improved.py` | Add Prompt Builder menu option |
| `setup.py` | Add `pyyaml` dependency |
| `requirements.txt` | Add `pyyaml` |

---

## 📝 Notes

### Why YAML for Templates?
- More readable than JSON for multi-line content
- Supports block scalars (`|`) for preserving formatting
- Familiar to developers
- Easy to edit by hand

### Why Simple Placeholder Syntax?
- `{{VAR}}` is intuitive and widely recognized
- Avoids complexity of full templating engines (Jinja2)
- Sufficient for prompt generation use case
- Can be extended later if needed

### Future Enhancements
- Template versioning and migration
- Template sharing/import from URLs
- Conditional sections (`{{#if VAR}}...{{/if}}`)
- Template inheritance/composition
- Integration with prompt version control

---

## 🚫 Out of Scope

- Token tracking for generated prompts
- Cost projection before sending
- Template usage analytics
- Automatic execution of generated prompts
- Export format selection (implementer decision)
- Complex templating (loops, conditionals)
- Template marketplace/sharing

---

**Design Document Complete - Ready for Implementation**

