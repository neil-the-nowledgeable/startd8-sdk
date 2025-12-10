"""
Agent implementations for different LLM providers
"""

import os
import time
import asyncio
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Optional dependencies - import with clear error messages
try:
    from anthropic import Anthropic, AsyncAnthropic
except ImportError:
    Anthropic = None
    AsyncAnthropic = None
    _ANTHROPIC_AVAILABLE = False
else:
    _ANTHROPIC_AVAILABLE = True

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    _OPENAI_AVAILABLE = False
else:
    _OPENAI_AVAILABLE = True

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
except ImportError:
    genai = None
    GenerationConfig = None
    _GEMINI_AVAILABLE = False
else:
    _GEMINI_AVAILABLE = True

from .models import TokenUsage, AgentResponse

# Import cost tracking (optional dependency within the same package)
try:
    from .costs import CostTracker, BudgetManager, get_cost_context
    from .costs.budget import BudgetExceededError
    _COSTS_AVAILABLE = True
except ImportError:
    CostTracker = None
    BudgetManager = None
    get_cost_context = None
    BudgetExceededError = None
    _COSTS_AVAILABLE = False


class BaseAgent(ABC):
    """Base class for LLM agents with sync and async support"""
    
    def __init__(
        self, 
        name: str, 
        model: str,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize agent
        
        Args:
            name: Agent identifier
            model: Model name to use
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
        """
        self.name = name
        self.model = model
        self.cost_tracker = cost_tracker
        self.budget_manager = budget_manager
    
    @abstractmethod
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Async generate a response to a prompt.
        
        This is the primary method that subclasses must implement.
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
        """
        pass
    
    def generate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Synchronous wrapper for backward compatibility.
        
        Runs the async method in an event loop.
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
        """
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, we need to run in a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(lambda: asyncio.run(self.agenerate(prompt)))
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.agenerate(prompt))
    
    async def _run_with_cost_tracking(
        self,
        prompt: str,
        prompt_id: str,
        response_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Tuple[str, int, TokenUsage]:
        """
        Execute API call with cost tracking and budget enforcement.
        
        This helper method orchestrates:
        1. Pre-call budget check (if budget_manager is configured)
        2. API call execution (agenerate)
        3. Post-call cost recording (if cost_tracker is configured)
        
        Args:
            prompt: The prompt text
            prompt_id: ID of the prompt (for cost record)
            response_id: ID of the response (unique identifier linking cost record to response)
            metadata: Optional metadata to include in cost record
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
        
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
            
        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # STEP 1: Pre-call budget check
        if self.cost_tracker and self.budget_manager and _COSTS_AVAILABLE:
            # Get context defaults (Phase 1 integration)
            context = get_cost_context() if get_cost_context else {}
            
            # Use explicit project or fall back to context default
            effective_project = project or context.get("project")
            
            # Estimate cost from pricing service
            estimated_cost = self.cost_tracker.pricing.estimate_cost(
                model=self.model,
                prompt_chars=len(prompt),
                expected_output_chars=500  # Conservative estimate
            )
            
            # Check budget (may raise BudgetExceededError if block_on_exceed=True)
            if effective_project:
                self.budget_manager.check_budget(
                    model=self.model,
                    project=effective_project,
                    tags=tags or context.get("tags", []),
                    estimated_cost=estimated_cost
                )
        
        # STEP 2: Execute API call
        response_text, response_time_ms, token_usage = await self.agenerate(prompt)
        
        # STEP 3: Post-call cost recording
        if self.cost_tracker and _COSTS_AVAILABLE:
            # Get context defaults for recording (Phase 1 integration)
            context = get_cost_context() if get_cost_context else {}
            
            # Use explicit project or fall back to context default
            effective_project = project or context.get("project")
            
            # Merge explicit tags with context tags (decision A3)
            context_tags = context.get("tags", []) if context else []
            effective_tags = list(set((tags or []) + context_tags))
            
            # Record actual cost with token usage
            self.cost_tracker.record_cost(
                agent_name=self.name,
                model=self.model,
                input_tokens=token_usage.input,
                output_tokens=token_usage.output,
                tags=effective_tags,
                project=effective_project,
                prompt_id=prompt_id,
                response_id=response_id,
                metadata=metadata or {}
            )
            # COST_RECORDED event is emitted automatically by record_cost()
        
        return response_text, response_time_ms, token_usage
    
    async def acreate_response(
        self,
        prompt_id: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None
    ) -> AgentResponse:
        """
        Async generate and create an AgentResponse object
        
        Integrates with cost tracking and budget enforcement if configured.
        
        Args:
            prompt_id: ID of the prompt
            prompt: Prompt text
            metadata: Optional metadata
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
            
        Returns:
            AgentResponse object
            
        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # Generate response_id once at the start to ensure cost record and response use the same ID
        response_id = f"response-{uuid.uuid4().hex[:12]}"
        
        # Use cost tracking helper if cost_tracker is available
        if self.cost_tracker and _COSTS_AVAILABLE:
            response_text, response_time_ms, token_usage = await self._run_with_cost_tracking(
                prompt=prompt,
                prompt_id=prompt_id,
                response_id=response_id,
                metadata=metadata,
                project=project,
                tags=tags
            )
        else:
            # Direct call without cost tracking
            response_text, response_time_ms, token_usage = await self.agenerate(prompt)
        
        return AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )
    
    def create_response(
        self,
        prompt_id: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None
    ) -> AgentResponse:
        """
        Generate and create an AgentResponse object (sync wrapper)
        
        Integrates with cost tracking and budget enforcement if configured.
        Bridges sync code to async cost tracking pipeline.
        
        Args:
            prompt_id: ID of the prompt
            prompt: Prompt text
            metadata: Optional metadata
            project: Optional project identifier (overrides context default)
            tags: Optional tags (merged with context tags)
            
        Returns:
            AgentResponse object
            
        Raises:
            BudgetExceededError: If budget check fails with block_on_exceed=True
        """
        # Generate response_id once at the start to ensure cost record and response use the same ID
        response_id = f"response-{uuid.uuid4().hex[:12]}"
        
        # Use cost tracking helper via asyncio bridge if cost_tracker is available
        if self.cost_tracker and _COSTS_AVAILABLE:
            try:
                loop = asyncio.get_running_loop()
                # If we're already in an async context, we need to run in a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        lambda: asyncio.run(
                            self._run_with_cost_tracking(
                                prompt=prompt,
                                prompt_id=prompt_id,
                                response_id=response_id,
                                metadata=metadata,
                                project=project,
                                tags=tags
                            )
                        )
                    )
                    response_text, response_time_ms, token_usage = future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run directly
                response_text, response_time_ms, token_usage = asyncio.run(
                    self._run_with_cost_tracking(
                        prompt=prompt,
                        prompt_id=prompt_id,
                        response_id=response_id,
                        metadata=metadata,
                        project=project,
                        tags=tags
                    )
                )
        else:
            # Direct call without cost tracking
            response_text, response_time_ms, token_usage = self.generate(prompt)
        
        return AgentResponse(
            id=response_id,
            prompt_id=prompt_id,
            agent_name=self.name,
            model=self.model,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            metadata=metadata or {}
        )


class ClaudeAgent(BaseAgent):
    """Anthropic Claude agent with async support"""
    
    def __init__(
        self,
        name: str = "claude",
        model: str = "claude-3-opus-20240229",  # Most stable, widely available model
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize Claude agent
        
        Args:
            name: Agent identifier
            model: Claude model to use
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install startd8[anthropic] or pip install anthropic"
            )
        
        self.client = Anthropic(api_key=api_key)
        self.async_client = AsyncAnthropic(api_key=api_key)
        self.max_tokens = max_tokens
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate response using Claude async API"""
        start_time = time.time()
        
        response = await self.async_client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        response_text = response.content[0].text
        
        token_usage = TokenUsage(
            input=response.usage.input_tokens,
            output=response.usage.output_tokens,
            total=response.usage.input_tokens + response.usage.output_tokens
        )
        
        return response_text, response_time_ms, token_usage


class GPT4Agent(BaseAgent):
    """OpenAI GPT-4 agent with async support"""
    
    def __init__(
        self,
        name: str = "gpt4",
        model: str = "gpt-4-turbo-preview",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize GPT-4 agent
        
        Args:
            name: Agent identifier
            model: GPT model to use
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )
        
        self.client = OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)
        self.max_tokens = max_tokens
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate response using GPT-4 async API"""
        start_time = time.time()
        
        response = await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        response_text = response.choices[0].message.content
        
        token_usage = TokenUsage(
            input=response.usage.prompt_tokens,
            output=response.usage.completion_tokens,
            total=response.usage.total_tokens
        )
        
        return response_text, response_time_ms, token_usage


class GeminiAgent(BaseAgent):
    """Google Gemini agent with async support"""
    
    def __init__(
        self,
        name: str = "gemini",
        model: str = "gemini-pro",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize Gemini agent
        
        Args:
            name: Agent identifier
            model: Gemini model to use (e.g., 'gemini-pro', 'gemini-1.5-pro')
            api_key: Google API key (uses GOOGLE_API_KEY env var if not provided)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
            
        Raises:
            ImportError: If google-generativeai package is not installed
            ValueError: If API key is not provided and not in environment
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. "
                "Install with: pip install startd8[gemini] or pip install google-generativeai"
            )
        
        # Get API key from parameter or environment
        if api_key is None:
            api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            raise ValueError(
                "Google API key required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )
        
        # Configure the API
        genai.configure(api_key=api_key)
        
        # Create the model instance with generation config
        generation_config = GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        
        self.model_instance = genai.GenerativeModel(
            model_name=self.model,
            generation_config=generation_config
        )
        
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """
        Generate response using Gemini async API
        
        Args:
            prompt: The prompt text
            
        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
            
        Raises:
            RuntimeError: If Gemini API call fails
        """
        start_time = time.time()
        
        try:
            # google-generativeai doesn't have native async,
            # but we can use asyncio to run it in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model_instance.generate_content(prompt)
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {e}") from e
        
        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)
        
        # Extract response text
        if not response.text:
            raise RuntimeError(
                f"Gemini returned empty response. "
                f"Finish reason: {response.finish_reason}"
            )
        
        response_text = response.text
        
        # Google Gemini doesn't provide token counts in standard API response,
        # so we need to use the countTokens method
        try:
            # Count input tokens
            input_count_response = self.model_instance.count_tokens(prompt)
            input_tokens = input_count_response.total_tokens
            
            # Count output tokens (response text)
            output_count_response = self.model_instance.count_tokens(response_text)
            output_tokens = output_count_response.total_tokens
        except Exception as e:
            # If token counting fails, provide reasonable estimates
            # ~1.3 tokens per word as rough estimate
            input_tokens = max(1, int(len(prompt.split()) / 1.3))
            output_tokens = max(1, int(len(response_text.split()) / 1.3))
            logger.warning(f"Failed to count tokens, using estimate: {e}")
        
        token_usage = TokenUsage(
            input=int(input_tokens),
            output=int(output_tokens),
            total=int(input_tokens + output_tokens)
        )
        
        return response_text, response_time_ms, token_usage


class OpenAICompatibleAgent(BaseAgent):
    """Agent for OpenAI-compatible APIs (Cursor, Ollama, Together AI, Groq, etc.) with async support"""
    
    def __init__(
        self,
        name: str = "custom",
        model: str = "custom-model",
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 4096,
        cost_tracker: Optional['CostTracker'] = None,
        budget_manager: Optional['BudgetManager'] = None
    ):
        """
        Initialize OpenAI-compatible agent
        
        Args:
            name: Agent identifier
            model: Model name to use
            api_key: API key (or use api_key_env to specify env var name)
            api_key_env: Environment variable name for API key
            base_url: Base URL for the API (e.g., 'https://api.cursor.sh/v1')
            max_tokens: Maximum tokens to generate
            cost_tracker: Optional cost tracker for recording costs
            budget_manager: Optional budget manager for enforcing limits
        """
        super().__init__(name, model, cost_tracker, budget_manager)
        
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install startd8[openai] or pip install openai"
            )
        
        # Get API key from env var if specified
        import os
        actual_api_key = api_key
        if not actual_api_key and api_key_env:
            actual_api_key = os.getenv(api_key_env)
        
        # Some APIs (like Ollama) don't need an API key
        # For localhost URLs, we can use None if the client supports it
        if not actual_api_key and base_url:
            # Check if this looks like a local URL (Ollama, etc.)
            if 'localhost' in base_url or '127.0.0.1' in base_url:
                # Use None instead of dummy key - OpenAI client accepts None for local APIs
                actual_api_key = None
        
        self.client = OpenAI(
            api_key=actual_api_key,
            base_url=base_url
        )
        self.async_client = AsyncOpenAI(
            api_key=actual_api_key,
            base_url=base_url
        )
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.api_key_env = api_key_env
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate response using OpenAI-compatible API (async)"""
        start_time = time.time()
        
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            response_text = response.choices[0].message.content
            
            # Some APIs may not return usage info
            if hasattr(response, 'usage') and response.usage:
                token_usage = TokenUsage(
                    input=response.usage.prompt_tokens or 0,
                    output=response.usage.completion_tokens or 0,
                    total=response.usage.total_tokens or 0
                )
            else:
                # Estimate tokens if not provided
                token_usage = TokenUsage(
                    input=len(prompt.split()),
                    output=len(response_text.split()) if response_text else 0,
                    total=len(prompt.split()) + (len(response_text.split()) if response_text else 0)
                )
            
            return response_text, response_time_ms, token_usage
            
        except Exception as e:
            from .logging_config import get_logger
            from .exceptions import APIError
            
            logger = get_logger(__name__)
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            logger.error(
                f"API call failed for {self.name}: {e}",
                exc_info=True,
                extra={"agent_name": self.name, "model": self.model, "response_time_ms": response_time_ms}
            )
            
            # Preserve original exception context
            raise APIError(
                f"API call failed: {str(e)}",
                provider=self.name,
                original_error=e
            ) from e


class MockAgent(BaseAgent):
    """Mock agent for testing with async support"""
    
    def __init__(self, name: str = "mock", model: str = "mock-model"):
        """Initialize mock agent"""
        super().__init__(name, model)
    
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        """Generate mock response (async)"""
        await asyncio.sleep(0.1)  # Simulate async latency
        
        response = f"Mock response to: {prompt[:50]}..."
        response_time_ms = 100
        
        token_usage = TokenUsage(
            input=len(prompt.split()),
            output=len(response.split()),
            total=len(prompt.split()) + len(response.split())
        )
        
        return response, response_time_ms, token_usage


class ComposerAgent(OpenAICompatibleAgent):
    """Cursor Composer agent (via OpenAI-compatible API)"""
    
    def __init__(
        self,
        name: str = "composer",
        model: str = "composer",
        api_key: Optional[str] = None,
        api_key_env: str = "CURSOR_API_KEY",
        base_url: str = "https://api.cursor.sh/v1",
        max_tokens: int = 8192
    ):
        """
        Initialize Cursor Composer agent.
        
        Composer is Cursor's AI model accessed via OpenAI-compatible API.
        
        Args:
            name: Agent identifier (default: "composer")
            model: Model name (default: "composer")
            api_key: Cursor API key (or use api_key_env)
            api_key_env: Environment variable for API key (default: CURSOR_API_KEY)
            base_url: Cursor API base URL
            max_tokens: Maximum tokens to generate
        """
        super().__init__(
            name=name,
            model=model,
            api_key=api_key,
            api_key_env=api_key_env,
            base_url=base_url,
            max_tokens=max_tokens
        )

