"""
Template Loader - Load templates from built-in and user directories
"""

from pathlib import Path
from typing import List, Dict, Optional
import yaml
import logging

from .models import PromptTemplate, TemplateVariable, TemplateSource
from .config import PROMPT_BUILDER_CONFIG

logger = logging.getLogger(__name__)


class TemplateLoader:
    """Load and manage prompt templates"""
    
    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None,
        project_dir: Optional[Path] = None
    ):
        """
        Initialize template loader.
        
        Args:
            builtin_dir: Directory for built-in templates (defaults to package templates/)
            user_dir: Directory for user templates (defaults to ~/.startd8/templates/)
            project_dir: Optional project-specific templates directory
        """
        self.builtin_dir = builtin_dir or PROMPT_BUILDER_CONFIG["builtin_templates_dir"]
        self.user_dir = user_dir or PROMPT_BUILDER_CONFIG["user_templates_dir"]
        self.project_dir = project_dir
        self._cache: Dict[str, PromptTemplate] = {}
    
    def load_builtin_templates(self) -> Dict[str, PromptTemplate]:
        """Load all built-in templates from package"""
        templates = {}
        
        if not self.builtin_dir.exists():
            logger.warning(f"Built-in templates directory not found: {self.builtin_dir}")
            return templates
        
        for file_path in self.builtin_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(file_path, TemplateSource.BUILTIN)
                templates[template.id] = template
                logger.debug(f"Loaded built-in template: {template.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        
        return templates
    
    def load_user_templates(self) -> Dict[str, PromptTemplate]:
        """Load all user-defined templates from ~/.startd8/templates/"""
        templates = {}
        
        if not self.user_dir.exists():
            return templates
        
        for file_path in self.user_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(file_path, TemplateSource.USER)
                templates[template.id] = template
                logger.debug(f"Loaded user template: {template.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        
        return templates
    
    def load_project_templates(self) -> Dict[str, PromptTemplate]:
        """Load templates from project directory if specified"""
        templates = {}
        
        if not self.project_dir or not self.project_dir.exists():
            return templates
        
        templates_dir = self.project_dir / "templates"
        if not templates_dir.exists():
            return templates
        
        for file_path in templates_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(file_path, TemplateSource.USER)
                templates[template.id] = template
                logger.debug(f"Loaded project template: {template.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        
        return templates
    
    def list_templates(self, refresh: bool = False) -> List[PromptTemplate]:
        """
        List all available templates.
        Priority order: project > user > builtin (later overrides earlier)
        """
        if refresh or not self._cache:
            # Load in priority order (builtin first, then overrides)
            self._cache = self.load_builtin_templates()
            
            user_templates = self.load_user_templates()
            self._cache.update(user_templates)
            
            project_templates = self.load_project_templates()
            self._cache.update(project_templates)
        
        return sorted(self._cache.values(), key=lambda t: (t.category, t.name))
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """Get a specific template by ID"""
        if not self._cache:
            self.list_templates()
        return self._cache.get(template_id)
    
    def get_templates_by_category(self) -> Dict[str, List[PromptTemplate]]:
        """Get templates grouped by category"""
        templates = self.list_templates()
        by_category: Dict[str, List[PromptTemplate]] = {}
        
        for template in templates:
            category = template.category
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(template)
        
        return by_category
    
    def _load_template_file(
        self, 
        file_path: Path, 
        source: TemplateSource
    ) -> PromptTemplate:
        """Load a single template from a YAML file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            raise ValueError(f"Empty or invalid template file: {file_path}")
        
        # Convert variable dicts to TemplateVariable objects
        variables = []
        for i, var_data in enumerate(data.get('variables', [])):
            # Set order if not specified
            if 'order' not in var_data:
                var_data['order'] = i + 1
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
    
    def create_user_templates_dir(self) -> Path:
        """Create user templates directory if it doesn't exist"""
        self.user_dir.mkdir(parents=True, exist_ok=True)
        return self.user_dir

