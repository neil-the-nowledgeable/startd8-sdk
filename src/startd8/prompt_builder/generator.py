"""
Prompt Generator - Fill templates and generate prompts
"""

import re
from datetime import datetime, timezone
from typing import Dict, Optional, List, Tuple

from .models import PromptTemplate, TemplateContext, GeneratedPrompt, TemplateVariable
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
    
    def get_ordered_variables(self, template: PromptTemplate) -> List[TemplateVariable]:
        """
        Get template variables in order for wizard display.
        Merges defined variables with extracted variables from content.
        """
        # Start with defined variables
        defined_vars = {v.name: v for v in template.variables}
        
        # Extract variables from content
        extracted = self.extract_variables(template)
        
        # Create list with all variables
        result = []
        seen = set()
        
        # First add defined variables in order
        for var in sorted(template.variables, key=lambda v: v.order):
            result.append(var)
            seen.add(var.name)
        
        # Then add any extracted variables not in defined list
        for var_name, default_value in extracted.items():
            if var_name not in seen:
                result.append(TemplateVariable(
                    name=var_name,
                    description=f"Value for {var_name}",
                    default=default_value,
                    required=default_value is None,
                    order=len(result) + 1
                ))
        
        return result
    
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
        
        # Check defined variables
        for var in template.variables:
            if var.required and var.name not in context.variable_values:
                # Check if there's a default in the template content
                if var.default is None and extracted.get(var.name) is None:
                    # Check auto-filled
                    if var.name not in context.auto_filled:
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
            generated_at=datetime.now(timezone.utc).isoformat(),
            word_count=len(content.split()),
            line_count=content.count('\n') + 1
        )
    
    def preview(
        self, 
        template: PromptTemplate, 
        context: TemplateContext,
        max_length: int = None
    ) -> str:
        """Generate a preview of the filled template"""
        if max_length is None:
            max_length = PROMPT_BUILDER_CONFIG["preview_max_length"]
        
        result = self.fill_template(template, context)
        
        if len(result.content) <= max_length:
            return result.content
        
        return result.content[:max_length] + f"\n\n... ({result.word_count} words total)"
    
    def get_unfilled_preview(
        self,
        template: PromptTemplate,
        context: TemplateContext,
        max_length: int = None
    ) -> Tuple[str, List[str]]:
        """
        Get preview with unfilled variables highlighted.
        Returns (preview_text, list of unfilled variable names)
        """
        if max_length is None:
            max_length = PROMPT_BUILDER_CONFIG["preview_max_length"]
        
        content = template.content
        unfilled = []
        
        def highlight_placeholder(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) else None
            
            # Check if we have a value
            if var_name in context.variable_values:
                return context.variable_values[var_name]
            elif var_name in context.auto_filled:
                return f"[auto:{context.auto_filled[var_name]}]"
            elif default_value:
                return f"[default:{default_value}]"
            else:
                unfilled.append(var_name)
                return f"[MISSING:{var_name}]"
        
        preview = self.placeholder_pattern.sub(highlight_placeholder, content)
        
        if len(preview) > max_length:
            preview = preview[:max_length] + "\n... (truncated)"
        
        return preview, unfilled

