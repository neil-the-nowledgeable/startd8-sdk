"""
Prompt Builder Data Models
"""

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
        """Check if variable is optional (has default or not required)"""
        return self.default is not None or not self.required


class TemplateSource(str, Enum):
    """Where the template came from"""
    BUILTIN = "builtin"
    USER = "user"


class PromptTemplate(BaseModel):
    """A reusable prompt template"""
    id: str = Field(description="Unique identifier (e.g., 'design_document')")
    name: str = Field(description="Human-readable name")
    description: str = Field(default="", description="What this template is for")
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
    variable_values: Dict[str, str] = Field(default_factory=dict)
    auto_filled: Dict[str, str] = Field(default_factory=dict, description="Variables auto-filled from context")
    
    class Config:
        arbitrary_types_allowed = True


class GeneratedPrompt(BaseModel):
    """Result of filling a template"""
    template_id: str
    template_name: str
    content: str = Field(description="The final generated prompt text")
    variables_used: Dict[str, str] = Field(description="Variable name -> value mapping")
    generated_at: str = Field(description="ISO timestamp")
    word_count: int
    line_count: int

