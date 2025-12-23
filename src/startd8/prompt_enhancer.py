"""
Prompt Enhancement Module for startd8

Reads prompts from files and uses Claude to enhance them based on
prompt engineering best practices.
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from .config import get_config_manager
from .models import TokenUsage
from .logging_config import get_logger

logger = get_logger(__name__)


class EnhancementStrategy(str, Enum):
    """Available enhancement strategies"""
    COMPREHENSIVE = "comprehensive"  # Full enhancement with all techniques
    CLARITY = "clarity"              # Focus on clear instructions
    STRUCTURE = "structure"          # Add structure and formatting guidance
    CONTEXT = "context"              # Enhance context and examples
    CONSTRAINTS = "constraints"      # Add constraints and guardrails
    MINIMAL = "minimal"              # Light touch - preserve original style


@dataclass
class EnhancementResult:
    """Result of a prompt enhancement operation"""
    original_content: str
    enhanced_content: str
    strategy: EnhancementStrategy
    model: str
    timestamp: datetime
    response_time_ms: int
    token_usage: Optional[TokenUsage]
    changes_summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def improvement_ratio(self) -> float:
        """Ratio of enhanced length to original"""
        if len(self.original_content) == 0:
            return 0.0
        return len(self.enhanced_content) / len(self.original_content)
    
    @property
    def word_count_original(self) -> int:
        return len(self.original_content.split())
    
    @property
    def word_count_enhanced(self) -> int:
        return len(self.enhanced_content.split())


# System prompts for different enhancement strategies
ENHANCEMENT_PROMPTS = {
    EnhancementStrategy.COMPREHENSIVE: """You are an expert prompt engineer. Your task is to enhance the given prompt to make it more effective for AI agents.

Apply these prompt engineering best practices:

1. **Clarity & Specificity**
   - Make instructions explicit and unambiguous
   - Define technical terms and expected formats
   - Specify the desired output structure

2. **Context & Background**
   - Add relevant context that helps understand the task
   - Include domain-specific information when helpful
   - Specify the target audience or use case

3. **Structure**
   - Use clear sections with headers
   - Add numbered steps for sequential tasks
   - Include examples where helpful

4. **Constraints & Guardrails**
   - Specify what to include AND what to avoid
   - Set length/scope boundaries when appropriate
   - Define quality criteria for the output

5. **Output Format**
   - Specify exact format expected (markdown, JSON, etc.)
   - Include template structures when useful
   - Define sections/headers for the response

IMPORTANT RULES:
- Preserve the core intent of the original prompt
- Don't add unnecessary complexity
- Make the enhanced prompt self-contained
- Output ONLY the enhanced prompt, no explanations

After the enhanced prompt, add a brief "---CHANGES---" section listing key improvements made.""",

    EnhancementStrategy.CLARITY: """You are a prompt clarity specialist. Improve the given prompt by:

1. Making instructions crystal clear and unambiguous
2. Breaking complex requests into numbered steps
3. Defining any technical terms
4. Removing vague language
5. Specifying exactly what output format is expected

Keep the original intent but make it impossible to misunderstand.

Output ONLY the enhanced prompt, followed by "---CHANGES---" with a brief list of clarifications made.""",

    EnhancementStrategy.STRUCTURE: """You are a prompt structure expert. Improve the given prompt by:

1. Adding clear section headers
2. Using bullet points and numbered lists appropriately
3. Creating a logical flow of information
4. Adding output format templates
5. Organizing requirements by priority or sequence

Maintain the original content but give it professional structure.

Output ONLY the enhanced prompt, followed by "---CHANGES---" with structural improvements made.""",

    EnhancementStrategy.CONTEXT: """You are a prompt context specialist. Improve the given prompt by:

1. Adding helpful background information
2. Including concrete examples
3. Specifying the use case and audience
4. Providing sample inputs/outputs when helpful
5. Adding domain-specific context

Enrich the prompt with context that helps produce better responses.

Output ONLY the enhanced prompt, followed by "---CHANGES---" with context additions made.""",

    EnhancementStrategy.CONSTRAINTS: """You are a prompt constraints specialist. Improve the given prompt by:

1. Adding specific boundaries and limits
2. Specifying what to avoid or exclude
3. Defining success criteria
4. Adding error handling guidance
5. Setting scope limitations

Add guardrails that prevent common failure modes.

Output ONLY the enhanced prompt, followed by "---CHANGES---" with constraints added.""",

    EnhancementStrategy.MINIMAL: """You are a prompt polish specialist. Make light improvements to the given prompt:

1. Fix any grammar or spelling issues
2. Improve word choices for precision
3. Remove redundancy
4. Ensure consistency
5. Keep the original voice and style

Make minimal but impactful improvements.

Output ONLY the enhanced prompt, followed by "---CHANGES---" with minor improvements made."""
}


class PromptEnhancer:
    """
    Enhances prompts using Claude's capabilities.
    
    Reads prompts from files, enhances them using prompt engineering
    best practices, and outputs enhanced versions.
    """
    
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 8192
    ):
        """
        Initialize the prompt enhancer.
        
        Args:
            api_key: Anthropic API key (uses config/env if not provided)
            model: Model to use for enhancement
            max_tokens: Maximum tokens for response
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )
        
        # Get API key from config if not provided
        if api_key is None:
            config = get_config_manager()
            api_key = config.get_api_key("anthropic")
        
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment "
                "variable or configure via: startd8 config set-key anthropic <key>"
            )
        
        self.client = Anthropic(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens
    
    def enhance(
        self,
        content: str,
        strategy: EnhancementStrategy = EnhancementStrategy.COMPREHENSIVE,
        additional_guidance: Optional[str] = None
    ) -> EnhancementResult:
        """
        Enhance a prompt string.
        
        Args:
            content: The prompt content to enhance
            strategy: Enhancement strategy to use
            additional_guidance: Optional extra instructions for enhancement
            
        Returns:
            EnhancementResult with original and enhanced content
        """
        system_prompt = ENHANCEMENT_PROMPTS[strategy]
        
        if additional_guidance:
            system_prompt += f"\n\nAdditional guidance:\n{additional_guidance}"
        
        user_message = f"Enhance this prompt:\n\n---\n{content}\n---"
        
        start_time = time.time()
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        response_text = response.content[0].text
        
        # Parse out the changes summary
        enhanced_content = response_text
        changes_summary = ""
        
        if "---CHANGES---" in response_text:
            parts = response_text.split("---CHANGES---")
            enhanced_content = parts[0].strip()
            changes_summary = parts[1].strip() if len(parts) > 1 else ""
        
        token_usage = TokenUsage(
            input=response.usage.input_tokens,
            output=response.usage.output_tokens,
            total=response.usage.input_tokens + response.usage.output_tokens,
            model_name=self.model,
        )
        
        return EnhancementResult(
            original_content=content,
            enhanced_content=enhanced_content,
            strategy=strategy,
            model=self.model,
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            changes_summary=changes_summary,
            metadata={
                "additional_guidance": additional_guidance
            }
        )
    
    def enhance_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        strategy: EnhancementStrategy = EnhancementStrategy.COMPREHENSIVE,
        additional_guidance: Optional[str] = None,
        include_metadata: bool = True
    ) -> EnhancementResult:
        """
        Enhance a prompt from a file and save to a new file.
        
        Args:
            input_path: Path to file containing the prompt
            output_path: Path for enhanced output (default: input_enhanced.ext)
            strategy: Enhancement strategy to use
            additional_guidance: Optional extra instructions
            include_metadata: Include metadata header in output file
            
        Returns:
            EnhancementResult with file paths in metadata
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Read original content
        content = input_path.read_text(encoding="utf-8")
        
        # Enhance the content
        result = self.enhance(content, strategy, additional_guidance)
        
        # Determine output path
        if output_path is None:
            stem = input_path.stem
            suffix = input_path.suffix
            output_path = input_path.parent / f"{stem}_enhanced{suffix}"
        else:
            output_path = Path(output_path)
        
        # Build output content
        output_content = result.enhanced_content
        
        if include_metadata:
            metadata_header = self._build_metadata_header(result, input_path)
            output_content = metadata_header + output_content
        
        # Write enhanced content with versioning to avoid overwriting
        from .utils.file_operations import save_text_file_with_versioning
        output_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path = save_text_file_with_versioning(output_path, output_content)
        
        # Add file paths to metadata (use actual saved path)
        result.metadata["input_file"] = str(input_path)
        result.metadata["output_file"] = str(saved_path)
        
        return result
    
    def _build_metadata_header(
        self,
        result: EnhancementResult,
        input_path: Path
    ) -> str:
        """Build a metadata header for the output file"""
        header_lines = [
            "<!-- ",
            "PROMPT ENHANCEMENT METADATA",
            f"Original: {input_path.name}",
            f"Strategy: {result.strategy.value}",
            f"Model: {result.model}",
            f"Enhanced: {result.timestamp.isoformat()}",
            f"Response Time: {result.response_time_ms}ms",
        ]
        
        if result.token_usage:
            header_lines.append(f"Tokens: {result.token_usage.total}")
            header_lines.append(f"Cost: ${result.token_usage.cost_estimate:.4f}")
        
        if result.changes_summary:
            header_lines.append("")
            header_lines.append("Changes Made:")
            for line in result.changes_summary.split("\n")[:10]:  # Limit to 10 lines
                header_lines.append(f"  {line}")
        
        header_lines.append("-->")
        header_lines.append("")
        header_lines.append("")
        
        return "\n".join(header_lines)
    
    def batch_enhance(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        pattern: str = "*.md",
        strategy: EnhancementStrategy = EnhancementStrategy.COMPREHENSIVE,
        additional_guidance: Optional[str] = None
    ) -> List[EnhancementResult]:
        """
        Enhance all matching files in a directory.
        
        Args:
            input_dir: Directory containing prompts
            output_dir: Output directory (default: input_dir/enhanced/)
            pattern: Glob pattern for files to process
            strategy: Enhancement strategy
            additional_guidance: Optional extra instructions
            
        Returns:
            List of EnhancementResults
        """
        input_dir = Path(input_dir)
        
        if output_dir is None:
            output_dir = input_dir / "enhanced"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for input_file in input_dir.glob(pattern):
            if input_file.is_file():
                output_file = output_dir / f"{input_file.stem}_enhanced{input_file.suffix}"
                try:
                    result = self.enhance_file(
                        input_file,
                        output_file,
                        strategy,
                        additional_guidance
                    )
                    results.append(result)
                except Exception as e:
                    # Log but continue with other files
                    logger.error(
                        f"Error enhancing file: {input_file}",
                        exc_info=True,
                        extra={"input_file": str(input_file), "error": str(e)}
                    )
        
        return results


def enhance_prompt_file(
    input_path: str,
    output_path: Optional[str] = None,
    strategy: str = "comprehensive",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> EnhancementResult:
    """
    Convenience function to enhance a prompt file.
    
    Args:
        input_path: Path to input file
        output_path: Path for output (optional)
        strategy: Enhancement strategy name
        api_key: Anthropic API key (optional)
        model: Model to use (optional)
        
    Returns:
        EnhancementResult
    """
    try:
        strategy_enum = EnhancementStrategy(strategy)
    except ValueError:
        valid = [s.value for s in EnhancementStrategy]
        raise ValueError(f"Invalid strategy '{strategy}'. Valid: {valid}")
    
    enhancer = PromptEnhancer(api_key=api_key, model=model)
    
    return enhancer.enhance_file(
        Path(input_path),
        Path(output_path) if output_path else None,
        strategy_enum
    )


