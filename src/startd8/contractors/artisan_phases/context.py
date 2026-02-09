import logging
from enum import Enum, auto
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

class _FallbackEncoding:
    """Char-based token estimator (~4 chars/token) when tiktoken is absent."""

    def encode(self, text: str) -> list:
        return [0] * (len(text) // 4 or 1)

    def decode(self, tokens: list) -> str:
        raise NotImplementedError('Fallback encoding cannot decode tokens')

class ContextPriority(Enum):
    """
    Priority levels for context components.
    
    CRITICAL: Must be included, even if over budget (e.g., system prompts)
    HIGH: Include if possible, compress if needed (e.g., key instructions)
    NORMAL: Include if budget allows (e.g., examples, documentation)
    LOW: Include only if ample budget remains (e.g., optional context)
    """
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3

    def __lt__(self, other):
        """Enable priority comparison for sorting."""
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

class CompressionType(Enum):
    """
    Types of compression strategies available.
    
    NONE: No compression applied
    TRUNCATE: Simple token-based truncation with ellipsis
    SUMMARIZE: AI-based summarization (placeholder implementation)
    CUSTOM: Reserved for future extensibility
    """
    NONE = 'none'
    TRUNCATE = 'truncate'
    SUMMARIZE = 'summarize'
    CUSTOM = 'custom'

@dataclass(frozen=True)
class ContextComponent:
    """
    Represents a single context component with metadata.
    
    Attributes:
        name: Unique identifier for the component
        content: The actual text content
        priority: Priority level for inclusion decisions
        token_count: Pre-calculated token count
        compression_type: Strategy to use if compression needed
        metadata: Additional metadata for tracking and debugging
    """
    name: str
    content: str
    priority: ContextPriority
    token_count: int
    compression_type: CompressionType = CompressionType.TRUNCATE
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class BudgetMetrics:
    """
    Token budget utilization metrics for monitoring and debugging.
    
    Attributes:
        total_budget: Configured maximum token limit
        used_tokens: Tokens actually allocated
        remaining_tokens: Tokens still available
        components_included: Number of components in final context
        components_excluded: Number of components that didn't fit
        components_compressed: Number of components that were compressed
        utilization_percentage: Percentage of total budget used
        is_over_budget: Flag indicating budget overflow (due to CRITICAL components)
    """
    total_budget: int
    used_tokens: int
    remaining_tokens: int
    components_included: int
    components_excluded: int
    components_compressed: int
    utilization_percentage: float
    is_over_budget: bool

@dataclass(frozen=True)
class ContextResult:
    """
    Final assembled context with comprehensive metadata.
    
    Attributes:
        content: The assembled context string
        total_tokens: Actual token count of final content
        components: List of included components
        excluded_components: Names of components that were excluded
        compressed_components: Names of components that were compressed
        metrics: Budget utilization metrics
        warnings: Any warnings generated during assembly
    """
    content: str
    total_tokens: int
    components: List[ContextComponent]
    excluded_components: List[str]
    compressed_components: List[str]
    metrics: BudgetMetrics
    warnings: List[str]

class CompressionStrategy(ABC):
    """
    Base class for content compression strategies.
    
    Implementations should focus on reducing token count while preserving
    semantic meaning as much as possible.
    """

    @abstractmethod
    def compress(self, content: str, target_tokens: int, current_tokens: int) -> str:
        """
        Compress content to fit within target token count.
        
        Args:
            content: Original content to compress
            target_tokens: Maximum allowed tokens after compression
            current_tokens: Current token count of content
            
        Returns:
            Compressed content string
        """
        pass

    @abstractmethod
    def estimate_compression_ratio(self) -> float:
        """
        Return estimated compression ratio (0.0 to 1.0).
        
        Returns:
            Ratio where 0.0 = maximum compression, 1.0 = no compression
        """
        pass

class TruncationStrategy(CompressionStrategy):
    """
    Truncates content to fit token budget by removing trailing tokens.
    
    This is a simple but effective strategy that preserves the beginning
    of the content and adds an ellipsis to indicate truncation.
    """

    def __init__(self, encoding_name: str='cl100k_base'):
        """
        Initialize truncation strategy.
        
        Args:
            encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4)
        """
        try:
            self.encoding = _get_encoding(encoding_name)
        except ValueError as e:
            logger.error(f'Invalid encoding name: {encoding_name}. Falling back to cl100k_base.')
            self.encoding = _get_encoding('cl100k_base')

    def compress(self, content: str, target_tokens: int, current_tokens: int) -> str:
        """Truncate content with ellipsis."""
        if current_tokens <= target_tokens:
            return content
        if target_tokens <= 0:
            return '[Content removed due to budget constraints]'
        ellipsis_tokens = 1
        max_content_tokens = max(0, target_tokens - ellipsis_tokens)
        if max_content_tokens <= 0:
            return '[...]'
        if _HAS_TIKTOKEN:
            tokens = self.encoding.encode(content)
            truncated_tokens = tokens[:max_content_tokens]
            compressed_content = self.encoding.decode(truncated_tokens)
        else:
            char_limit = max_content_tokens * 4
            compressed_content = content[:char_limit]
        return compressed_content + '...'

    def estimate_compression_ratio(self) -> float:
        """Truncation can achieve any ratio."""
        return 0.0

class SummarizationStrategy(CompressionStrategy):
    """
    Summarizes content to reduce token count while preserving meaning.
    
    Note: This is a placeholder implementation. In production, this should
    integrate with an LLM API for actual summarization.
    """

    def __init__(self, target_ratio: float=0.3, encoding_name: str='cl100k_base'):
        """
        Initialize summarization strategy.
        
        Args:
            target_ratio: Target compression ratio (default 30% of original)
            encoding_name: Tiktoken encoding name
        """
        if not 0.0 < target_ratio <= 1.0:
            raise ValueError('target_ratio must be between 0.0 (exclusive) and 1.0 (inclusive).')
        self.target_ratio = target_ratio
        try:
            self.encoding = _get_encoding(encoding_name)
        except ValueError:
            logger.error(f'Invalid encoding. Falling back to cl100k_base.')
            self.encoding = _get_encoding('cl100k_base')

    def compress(self, content: str, target_tokens: int, current_tokens: int) -> str:
        """
        Summarize content to target ratio.
        
        TODO: Replace with actual LLM-based summarization in production.
        """
        summarized_target = int(current_tokens * self.target_ratio)
        effective_target = min(target_tokens, summarized_target)
        if effective_target <= 0:
            return '[Content summarized and removed due to budget constraints]'
        logger.debug(f'Using truncation fallback for summarization. Target: {effective_target} tokens')
        truncation = TruncationStrategy()
        return truncation.compress(content, effective_target, current_tokens)

    def estimate_compression_ratio(self) -> float:
        """Return configured target ratio."""
        return self.target_ratio

class NoCompressionStrategy(CompressionStrategy):
    """No compression - returns original content unchanged."""

    def compress(self, content: str, target_tokens: int, current_tokens: int) -> str:
        """Return content unchanged."""
        return content

    def estimate_compression_ratio(self) -> float:
        """No compression capability."""
        return 1.0

class TokenCounter:
    """
    Utility class for counting tokens using tiktoken with caching.
    
    Caching significantly improves performance when counting tokens
    for the same content multiple times.
    """

    def __init__(self, encoding_name: str='cl100k_base'):
        """
        Initialize token counter.
        
        Args:
            encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4)
        """
        try:
            self.encoding = _get_encoding(encoding_name)
        except ValueError as e:
            logger.error(f'Invalid encoding name: {encoding_name}. Falling back to cl100k_base.')
            self.encoding = _get_encoding('cl100k_base')
        self._cache: Dict[str, int] = {}

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text with caching.
        
        Args:
            text: Input text
            
        Returns:
            Number of tokens
        """
        if not isinstance(text, str):
            logger.warning(f'Attempted to count tokens for non-string type: {type(text)}. Returning 0.')
            return 0
        if text in self._cache:
            return self._cache[text]
        token_count = len(self.encoding.encode(text))
        self._cache[text] = token_count
        return token_count

    def estimate_tokens_for_chars(self, char_count: int) -> int:
        """
        Estimate token count based on character count.
        
        Uses rough heuristic: ~4 chars per token for English text.
        For accurate counts, always use count_tokens().
        
        Args:
            char_count: Number of characters
            
        Returns:
            Estimated token count
        """
        if char_count <= 0:
            return 0
        return max(1, (char_count + 3) // 4)

    def clear_cache(self):
        """Clear the token count cache."""
        self._cache.clear()

class ContextBudget:
    """
    Manages token budget tracking and enforcement.
    
    Implements safety margins and structural overhead to ensure
    the assembled context fits comfortably within limits.
    """

    def __init__(self, total_budget: int, safety_margin: float=0.05, structural_overhead: int=100):
        """
        Initialize context budget.
        
        Args:
            total_budget: Maximum allowed tokens
            safety_margin: Percentage of budget to reserve (default 5%)
            structural_overhead: Reserved tokens for formatting (default 100)
        """
        if total_budget < 0:
            raise ValueError('Total budget cannot be negative.')
        if not 0.0 <= safety_margin < 1.0:
            raise ValueError('Safety margin must be between 0.0 and 1.0 (exclusive).')
        if structural_overhead < 0:
            raise ValueError('Structural overhead cannot be negative.')
        self._total_budget = total_budget
        self._safety_margin = safety_margin
        self._structural_overhead = structural_overhead
        self._used_tokens = 0
        self._components_included = 0
        self._components_excluded = 0
        self._components_compressed = 0
        if self.effective_budget <= 0 and total_budget > 0:
            logger.warning(f'Total budget {total_budget} is too small for safety margin ({safety_margin * 100}%) and overhead ({structural_overhead} tokens). Effective budget is {self.effective_budget}.')

    @property
    def effective_budget(self) -> int:
        """Calculate effective budget after safety margin and overhead."""
        budget_after_margin = int(self._total_budget * (1 - self._safety_margin))
        return max(0, budget_after_margin - self._structural_overhead)

    @property
    def total_budget(self) -> int:
        """Get the configured total budget."""
        return self._total_budget

    @property
    def used_tokens(self) -> int:
        """Get currently used tokens."""
        return self._used_tokens

    @property
    def remaining_tokens(self) -> int:
        """Get remaining available tokens within effective budget."""
        return max(0, self.effective_budget - self._used_tokens)

    @property
    def is_exhausted(self) -> bool:
        """Check if effective budget is exhausted."""
        return self._used_tokens >= self.effective_budget

    def can_fit(self, token_count: int) -> bool:
        """
        Check if token_count fits in remaining budget.
        
        Args:
            token_count: Tokens to check
            
        Returns:
            True if fits, False otherwise
        """
        return token_count <= self.remaining_tokens

    def allocate(self, token_count: int, component_compressed: bool=False, force_allocate: bool=False) -> bool:
        """
        Allocate tokens from budget.
        
        Args:
            token_count: Tokens to allocate
            component_compressed: Whether the component was compressed
            force_allocate: If True, allows over-budget allocation (for CRITICAL)
            
        Returns:
            True if allocated successfully, False otherwise
        """
        if token_count < 0:
            logger.warning(f'Attempted to allocate negative token count: {token_count}. Ignoring.')
            return False
        if force_allocate:
            self._used_tokens += token_count
            self._components_included += 1
            if component_compressed:
                self._components_compressed += 1
            return True
        if self.can_fit(token_count):
            self._used_tokens += token_count
            self._components_included += 1
            if component_compressed:
                self._components_compressed += 1
            return True
        return False

    def record_exclusion(self):
        """Record that a component was excluded."""
        self._components_excluded += 1

    def get_metrics(self) -> BudgetMetrics:
        """
        Generate comprehensive budget metrics.
        
        Returns:
            BudgetMetrics instance with current state
        """
        utilization = self._used_tokens / self._total_budget * 100 if self._total_budget > 0 else 0.0
        is_over_budget = self._used_tokens > self.effective_budget
        return BudgetMetrics(total_budget=self._total_budget, used_tokens=self._used_tokens, remaining_tokens=self.remaining_tokens, components_included=self._components_included, components_excluded=self._components_excluded, components_compressed=self._components_compressed, utilization_percentage=round(utilization, 2), is_over_budget=is_over_budget)

    def reset_counters(self):
        """Reset internal counters for a new assembly process."""
        self._used_tokens = 0
        self._components_included = 0
        self._components_excluded = 0
        self._components_compressed = 0

class ContextAssembler:
    """
    Main orchestrator for context assembly with budget management.
    
    This class provides a fluent interface for building and assembling
    context from multiple components while respecting token budgets.
    
    Example:
        assembler = ContextAssembler(total_budget=4000)
        result = (assembler
            .add_system_prompt("You are a helpful assistant.")
            .add_component("instructions", "...", ContextPriority.HIGH)
            .add_file_context("data.txt", ContextPriority.NORMAL)
            .assemble())
    """

    def __init__(self, total_budget: int, encoding_name: str='cl100k_base', safety_margin: float=0.05, structural_overhead: int=100):
        """
        Initialize context assembler.
        
        Args:
            total_budget: Maximum token budget
            encoding_name: Tiktoken encoding name
            safety_margin: Budget safety margin (default 5%)
            structural_overhead: Reserved tokens for formatting (default 100)
        """
        if total_budget < 0:
            raise ValueError('Total budget cannot be negative.')
        self.token_counter = TokenCounter(encoding_name)
        self.budget = ContextBudget(total_budget, safety_margin, structural_overhead)
        self.structural_overhead = structural_overhead
        self.encoding_name = encoding_name
        self._components: List[ContextComponent] = []
        self._compression_strategies: Dict[CompressionType, CompressionStrategy] = {CompressionType.NONE: NoCompressionStrategy(), CompressionType.TRUNCATE: TruncationStrategy(encoding_name), CompressionType.SUMMARIZE: SummarizationStrategy()}
        self._reset_assembly_state()

    def _reset_assembly_state(self):
        """Reset state variables for assembly."""
        self._warnings: List[str] = []
        self._excluded_component_names: List[str] = []
        self._compressed_component_names: List[str] = []
        self._included_components: List[ContextComponent] = []

    def add_component(self, name: str, content: str, priority: ContextPriority, compression_type: CompressionType=CompressionType.TRUNCATE, metadata: Optional[Dict[str, Any]]=None) -> 'ContextAssembler':
        """
        Add a context component (fluent interface).
        
        Args:
            name: Component identifier (must be unique)
            content: Component content
            priority: Priority level
            compression_type: Compression strategy to use
            metadata: Optional metadata dictionary
            
        Returns:
            Self for method chaining
            
        Raises:
            ValueError: If name is empty or invalid
            TypeError: If priority or compression_type have wrong types
        """
        if not isinstance(name, str) or not name:
            raise ValueError('Component name must be a non-empty string.')
        if not isinstance(content, str):
            content = str(content)
            logger.warning(f"Component '{name}' content was not a string. Converted to string.")
        if not isinstance(priority, ContextPriority):
            raise TypeError('Priority must be a ContextPriority enum member.')
        if not isinstance(compression_type, CompressionType):
            raise TypeError('Compression type must be a CompressionType enum member.')
        token_count = self.token_counter.count_tokens(content)
        if compression_type == CompressionType.CUSTOM:
            logger.warning(f"Custom compression type specified for '{name}'. No custom strategy registered, defaulting to TRUNCATE.")
            compression_type = CompressionType.TRUNCATE
        if not content.strip():
            token_count = max(1, token_count)
        component = ContextComponent(name=name, content=content, priority=priority, token_count=token_count, compression_type=compression_type, metadata=metadata or {})
        self._components.append(component)
        logger.debug(f"Added component '{name}': {token_count} tokens, priority={priority.name}")
        return self

    def add_file_context(self, file_path: str, priority: ContextPriority=ContextPriority.NORMAL, compression_type: CompressionType=CompressionType.TRUNCATE) -> 'ContextAssembler':
        """
        Add file content as context component.
        
        Args:
            file_path: Path to file
            priority: Priority level
            compression_type: Compression strategy
            
        Returns:
            Self for method chaining
            
        Raises:
            FileNotFoundError: If file doesn't exist
            RuntimeError: If file cannot be read
        """
        if not isinstance(file_path, str) or not file_path:
            raise ValueError('File path must be a non-empty string.')
        path = Path(file_path)
        try:
            content = path.read_text(encoding='utf-8')
            if len(content) > 1024 * 1024:
                logger.warning(f"File '{file_path}' is very large ({len(content)} characters). Consider more aggressive compression.")
            return self.add_component(name=f'file:{file_path}', content=content, priority=priority, compression_type=compression_type, metadata={'file_path': str(path.absolute()), 'file_size': len(content)})
        except FileNotFoundError:
            error_msg = f'File not found: {file_path}'
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f'Error reading file {file_path}: {e}'
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def add_system_prompt(self, prompt: str) -> 'ContextAssembler':
        """
        Add system prompt (always CRITICAL priority, no compression).
        
        System prompts are essential instructions that must always be included.
        
        Args:
            prompt: System prompt content
            
        Returns:
            Self for method chaining
        """
        if not isinstance(prompt, str):
            prompt = str(prompt)
            logger.warning('System prompt was not a string. Converted to string.')
        return self.add_component(name='system_prompt', content=prompt, priority=ContextPriority.CRITICAL, compression_type=CompressionType.NONE, metadata={'is_system_prompt': True})

    def assemble(self, format_template: Optional[str]=None) -> ContextResult:
        """
        Assemble context respecting budget constraints.
        
        Assembly process:
        1. Sort components by priority
        2. For each component (CRITICAL first):
           - If fits: add as-is
           - If doesn't fit: compress (if not CRITICAL) or force-add (if CRITICAL)
           - If still doesn't fit after compression: exclude
        3. Format final context
        4. Generate metrics and warnings
        
        Args:
            format_template: Optional template for formatting.
                           Available placeholders: component names, {all_content}, {system_prompt}
            
        Returns:
            ContextResult with assembled content and comprehensive metadata
        """
        self._reset_assembly_state()
        self.budget.reset_counters()
        sorted_components = sorted(self._components, key=lambda c: c.priority)
        logger.info(f'Starting assembly with {len(sorted_components)} components, budget={self.budget.effective_budget} tokens')
        for component in sorted_components:
            self._process_component(component)
        final_content = self._format_context(self._included_components, format_template)
        actual_tokens = self.token_counter.count_tokens(final_content)
        metrics = self.budget.get_metrics()
        if metrics.is_over_budget:
            self._warnings.append(f'Context assembly exceeded effective budget. Used: {metrics.used_tokens} / Effective: {self.budget.effective_budget}. This is due to force-added CRITICAL components.')
        logger.info(f'Assembly complete: {metrics.components_included} included, {metrics.components_excluded} excluded, {metrics.components_compressed} compressed, {actual_tokens} total tokens')
        return ContextResult(content=final_content, total_tokens=actual_tokens, components=self._included_components, excluded_components=self._excluded_component_names, compressed_components=self._compressed_component_names, metrics=metrics, warnings=self._warnings)

    def _process_component(self, component: ContextComponent):
        """Process a single component for inclusion."""
        component_to_add = component
        was_compressed = False
        if self.budget.can_fit(component.token_count):
            pass
        elif component.priority == ContextPriority.CRITICAL:
            self._warnings.append(f"CRITICAL component '{component.name}' exceeds budget ({component.token_count} tokens needed, {self.budget.remaining_tokens} available). Force-adding.")
        elif component.compression_type != CompressionType.NONE:
            compressed = self._try_compress_component(component, self.budget.remaining_tokens)
            if compressed:
                component_to_add = compressed
                was_compressed = True
                self._compressed_component_names.append(component.name)
                logger.debug(f"Compressed '{component.name}': {component.token_count} -> {compressed.token_count} tokens")
            else:
                self._excluded_component_names.append(component.name)
                self.budget.record_exclusion()
                logger.debug(f"Excluded '{component.name}': compression failed")
                return
        else:
            self._excluded_component_names.append(component.name)
            self.budget.record_exclusion()
            logger.debug(f"Excluded '{component.name}': doesn't fit, no compression allowed")
            return
        allocated = self.budget.allocate(token_count=component_to_add.token_count, component_compressed=was_compressed, force_allocate=component.priority == ContextPriority.CRITICAL)
        if allocated:
            self._included_components.append(component_to_add)
        elif component.name not in self._excluded_component_names:
            self._excluded_component_names.append(component.name)
            self.budget.record_exclusion()
            self._warnings.append(f"Failed to allocate component '{component.name}' unexpectedly. This may indicate a bug.")

    def _try_compress_component(self, component: ContextComponent, available_tokens: int) -> Optional[ContextComponent]:
        """
        Attempt to compress component to fit available tokens.
        
        Args:
            component: Component to compress
            available_tokens: Available token budget
            
        Returns:
            Compressed component if successful, None otherwise
        """
        if component.token_count <= available_tokens:
            return None
        strategy = self._get_compression_strategy(component.compression_type)
        if isinstance(strategy, NoCompressionStrategy):
            return None
        target_tokens = max(0, available_tokens)
        try:
            compressed_content = strategy.compress(component.content, target_tokens, component.token_count)
            compressed_token_count = self.token_counter.count_tokens(compressed_content)
            if compressed_token_count <= available_tokens:
                return replace(component, content=compressed_content, token_count=compressed_token_count, metadata={**component.metadata, 'was_compressed': True})
            else:
                logger.warning(f"Compression for '{component.name}' failed to meet target. Original: {component.token_count}, Compressed: {compressed_token_count}, Target: {available_tokens}")
                return None
        except Exception as e:
            logger.error(f"Error compressing component '{component.name}': {e}")
            return None

    def _get_compression_strategy(self, compression_type: CompressionType) -> CompressionStrategy:
        """Get compression strategy instance for type."""
        strategy = self._compression_strategies.get(compression_type)
        if strategy is None:
            logger.warning(f'No compression strategy found for {compression_type}. Defaulting to NoCompressionStrategy.')
            return NoCompressionStrategy()
        return strategy

    def _format_context(self, components: List[ContextComponent], template: Optional[str]=None) -> str:
        """
        Format components into final context string.
        
        Args:
            components: List of components to format
            template: Optional custom template
            
        Returns:
            Formatted context string
        """
        if not components:
            return ''
        if template:
            context_data: Dict[str, str] = {}
            for comp in components:
                context_data[comp.name] = comp.content
            context_data['all_content'] = '\n\n---\n\n'.join((c.content for c in components))
            system_prompt_comp = next((c for c in components if c.metadata.get('is_system_prompt')), None)
            if system_prompt_comp:
                context_data['system_prompt'] = system_prompt_comp.content
            try:
                return template.format(**context_data)
            except KeyError as e:
                logger.warning(f'Template placeholder {e} not found in context data. Using default formatting.')
                return '\n\n---\n\n'.join((c.content for c in components))
            except Exception as e:
                logger.error(f'Error formatting template: {e}. Using default formatting.')
                return '\n\n---\n\n'.join((c.content for c in components))
        else:
            return '\n\n---\n\n'.join((c.content for c in components))

    def clear(self) -> 'ContextAssembler':
        """
        Clear all components and reset state (fluent interface).
        
        Returns:
            Self for method chaining
        """
        self._components = []
        self._reset_assembly_state()
        self.budget.reset_counters()
        self.token_counter.clear_cache()
        logger.debug('Assembler cleared')
        return self

def _get_encoding(name: str='cl100k_base') -> Any:
    """Return a tiktoken encoding or the char-based fallback."""
    if _HAS_TIKTOKEN:
        return tiktoken.get_encoding(name)
    return _FallbackEncoding()

def create_context_assembler(budget: int, **kwargs) -> ContextAssembler:
    """
    Factory function for creating ContextAssembler instances.
    
    This provides a convenient way to create assemblers with default settings.
    
    Args:
        budget: Token budget
        **kwargs: Additional arguments passed to ContextAssembler
        
    Returns:
        ContextAssembler instance
        
    Raises:
        ValueError: If budget is negative
        
    Example:
        assembler = create_context_assembler(4000, safety_margin=0.1)
    """
    if budget < 0:
        raise ValueError('Budget cannot be negative.')
    return ContextAssembler(total_budget=budget, **kwargs)
"\nCentralized Context Assembly System with Token Budget Management\n\nThis module provides a comprehensive context assembly system with token budget tracking,\noverflow protection, prioritization, and compression capabilities. It's designed for\nmanaging LLM context windows efficiently.\n\nFeatures:\n- Token budget tracking using tiktoken\n- Component prioritization (CRITICAL, HIGH, NORMAL, LOW)\n- Multiple compression strategies (truncation, summarization placeholder)\n- Overflow protection and safety margins\n- Detailed metrics and warnings\n- Fluent builder interface\n- File content integration\n\nAuthor: Lead Contractor\nVersion: 1.0.0\n"
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    tiktoken = None
    _HAS_TIKTOKEN = False
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
__all__ = ['ContextPriority', 'CompressionType', 'ContextComponent', 'BudgetMetrics', 'ContextResult', 'CompressionStrategy', 'TruncationStrategy', 'SummarizationStrategy', 'NoCompressionStrategy', 'TokenCounter', 'ContextBudget', 'ContextAssembler', 'create_context_assembler']
__version__ = '1.0.0'
__author__ = 'Lead Contractor'
__license__ = 'MIT'