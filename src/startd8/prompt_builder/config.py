"""
Prompt Builder Configuration
"""

from pathlib import Path

PROMPT_BUILDER_CONFIG = {
    # Template locations
    "builtin_templates_dir": Path(__file__).parent / "templates",
    "user_templates_dir": Path.home() / ".startd8" / "templates",
    
    # Placeholder syntax: {{VAR}} or {{VAR|default="value"}}
    "placeholder_pattern": r"\{\{(\w+)(?:\|default=\"([^\"]*)\")?\}\}",
    
    # Auto-fill settings
    "auto_fill_enabled": True,
    "max_dir_scan_depth": 3,
    
    # File patterns to detect project type
    "project_indicators": {
        "python": ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile"],
        "typescript": ["package.json", "tsconfig.json"],
        "javascript": ["package.json"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "java": ["pom.xml", "build.gradle"],
        "ruby": ["Gemfile"],
        "php": ["composer.json"],
    },
    
    # Display settings
    "wizard_show_future_steps": True,
    "wizard_show_completed_steps": True,
    "preview_max_length": 500,
}

