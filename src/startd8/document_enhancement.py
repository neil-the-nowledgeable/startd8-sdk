"""
Document Enhancement Chain

Orchestrates sequential document enhancement using multiple AI agents.
Each agent receives the output from the previous agent, creating a refinement pipeline.
"""

import time
import re
import uuid
from pathlib import Path
from typing import Optional, Callable, List
from datetime import datetime, timezone

from .models import (
    DocumentEnhancementConfig,
    DocumentEnhancementResult,
    EnhancementStepResult,
    AgentConfig,
    ErrorHandling,
)
from .utils.file_operations import save_text_file_with_versioning
from .agents import BaseAgent


# Default prompt template for document enhancement
ENHANCEMENT_PROMPT_TEMPLATE = """You are an expert technical writer and software architect. Your task is to review and enhance a design document.

# Original Document

{document_content}

# Enhancement Instructions

{instructions}

# Task

Please review the document above and provide an enhanced version that:
1. Incorporates the enhancement instructions provided
2. Maintains the document structure and formatting
3. Improves clarity, completeness, and technical accuracy
4. Preserves all important information from the original

# Output Format

Please provide the complete enhanced document in markdown format. Return ONLY the enhanced document content, without additional commentary or explanations outside the document itself.

If you need to include notes about changes, add them as comments within the document using HTML comments: <!-- Your note here -->
"""


STEP_CONTEXT_TEMPLATE = """

# Context

This document has already been enhanced by {previous_agent_name}. Please review their enhancements and apply your own improvements based on the instructions above.
"""


class DocumentExtractionError(Exception):
    """Could not extract document from agent response"""
    pass


class AgentFailureError(Exception):
    """Agent call failed"""
    pass


class InvalidDocumentError(Exception):
    """Source document is invalid or unreadable"""
    pass


class DocumentEnhancementChain:
    """
    Orchestrates sequential document enhancement using multiple agents.
    
    Each agent receives:
    1. The document from the previous step (or original if first)
    2. User's enhancement instructions (if provided)
    3. Context about the enhancement task
    
    Example:
        ```python
        from startd8.document_enhancement import DocumentEnhancementChain
        from startd8.models import DocumentEnhancementConfig, AgentConfig
        from startd8.providers import ProviderRegistry
        from pathlib import Path

        ProviderRegistry.discover()
        openai = ProviderRegistry.get_provider("openai")
        anthropic = ProviderRegistry.get_provider("anthropic")
        openai.validate_config({})
        anthropic.validate_config({})
        
        config = DocumentEnhancementConfig(
            source_document=Path("design.md"),
            enhancement_instructions="Add accessibility section",
            agents=[
                AgentConfig(
                    agent_name="openai:gpt-4-turbo-preview",
                    agent_instance=openai.create_agent("gpt-4-turbo-preview"),
                    step_name="openai:gpt-4-turbo-preview-enhancement",
                    order=0
                ),
                AgentConfig(
                    agent_name="anthropic:claude-3-5-sonnet-20241022",
                    agent_instance=anthropic.create_agent("claude-3-5-sonnet-20241022"),
                    step_name="anthropic:claude-3-5-sonnet-20241022-refinement",
                    order=1
                )
            ],
            save_intermediate=True
        )
        
        chain = DocumentEnhancementChain(config, framework)
        result = chain.run()
        print(f"Success: {result.success}")
        print(f"Output: {result.output_path}")
        ```
    """
    
    def __init__(
        self,
        config: DocumentEnhancementConfig,
        framework=None
    ):
        """
        Initialize document enhancement chain.
        
        Args:
            config: Enhancement configuration
            framework: Optional AgentFramework for storage
        """
        self.config = config
        self.framework = framework
        self.results: List[EnhancementStepResult] = []
        self.chain_id = f"chain-{uuid.uuid4().hex[:12]}"
    
    def _load_document(self, path: Path) -> str:
        """
        Load document content from file.
        
        Args:
            path: Path to document
            
        Returns:
            Document content as string
            
        Raises:
            InvalidDocumentError: If document cannot be read
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                raise InvalidDocumentError(f"Document is empty: {path}")
            
            return content
        except Exception as e:
            raise InvalidDocumentError(f"Failed to load document {path}: {e}")
    
    def _load_prompt_from_file(self, prompt_file_path: Path) -> str:
        """
        Load prompt template from a .md file.
        
        Args:
            prompt_file_path: Path to the prompt file
            
        Returns:
            Prompt content as string
            
        Raises:
            InvalidDocumentError: If file cannot be read
        """
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                raise InvalidDocumentError(f"Prompt file is empty: {prompt_file_path}")
            
            return content
        except Exception as e:
            raise InvalidDocumentError(f"Failed to load prompt file {prompt_file_path}: {e}")
    
    def _build_prompt(
        self,
        document_content: str,
        instructions: Optional[str] = None,
        step_number: int = 0,
        previous_agent: Optional[str] = None
    ) -> str:
        """
        Build enhancement prompt for an agent.
        
        Args:
            document_content: Current document content
            instructions: User's enhancement instructions
            step_number: Current step number (0-based)
            previous_agent: Name of previous agent (if any)
            
        Returns:
            Formatted prompt string
        """
        # Check if prompt file is provided
        if self.config.prompt_file_path:
            try:
                prompt_template = self._load_prompt_from_file(self.config.prompt_file_path)
                # Replace placeholders in the template
                # Support {document_content} and {instructions} placeholders
                instructions_text = instructions if instructions else \
                    "Review and enhance this document using your expertise. Improve clarity, completeness, and technical accuracy."
                
                # Use format() if template has placeholders, otherwise simple replace
                try:
                    # Try format() first (supports {document_content} and {instructions})
                    prompt = prompt_template.format(
                        document_content=document_content,
                        instructions=instructions_text
                    )
                except (KeyError, ValueError):
                    # Fall back to simple string replacement for custom placeholders
                    prompt = prompt_template.replace('{document_content}', document_content)
                    prompt = prompt.replace('{instructions}', instructions_text)
                
                # Add step context if not first step
                if step_number > 0 and previous_agent:
                    step_context = STEP_CONTEXT_TEMPLATE.format(
                        previous_agent_name=previous_agent
                    )
                    prompt += step_context
                
                return prompt
            except Exception as e:
                # Fall back to default template if file loading fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load prompt file, using default template: {e}")
        
        # Use provided instructions or default message
        instructions_text = instructions if instructions else \
            "Review and enhance this document using your expertise. Improve clarity, completeness, and technical accuracy."
        
        # Build base prompt using default template
        prompt = ENHANCEMENT_PROMPT_TEMPLATE.format(
            document_content=document_content,
            instructions=instructions_text
        )
        
        # Add step context if not first step
        if step_number > 0 and previous_agent:
            step_context = STEP_CONTEXT_TEMPLATE.format(
                previous_agent_name=previous_agent
            )
            prompt += step_context
        
        return prompt
    
    def _extract_document_from_response(
        self,
        response: str,
        original_document: str
    ) -> str:
        """
        Extract enhanced document from agent response.
        
        Uses hybrid strategy:
        1. Try to extract from markdown code blocks (```markdown or ```md)
        2. Try to extract from any code blocks (```)
        3. If response is mostly markdown, use entire response
        4. Fallback: Return response as-is
        
        Args:
            response: Agent's response
            original_document: Original document for reference
            
        Returns:
            Extracted document content
            
        Raises:
            DocumentExtractionError: If extraction fails completely
        """
        if not response or not response.strip():
            raise DocumentExtractionError("Response is empty")
        
        # Strategy 1: Look for markdown code blocks
        markdown_pattern = r'```(?:markdown|md)\s*\n(.*?)```'
        matches = re.findall(markdown_pattern, response, re.DOTALL | re.IGNORECASE)
        if matches:
            # Use the last match (often the complete document)
            extracted = matches[-1].strip()
            if extracted:
                return extracted
        
        # Strategy 2: Look for any code blocks
        code_block_pattern = r'```(?:\w+)?\s*\n(.*?)```'
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        if matches:
            # Filter for markdown-like content (has headers)
            for match in reversed(matches):  # Try last match first
                if re.search(r'^#+\s+', match.strip(), re.MULTILINE):
                    return match.strip()
        
        # Strategy 3: If response has markdown headers, treat as document
        if re.search(r'^#+\s+', response.strip(), re.MULTILINE):
            # Response looks like markdown, use it directly
            return response.strip()
        
        # Strategy 4: Fallback - use entire response
        # This might include some commentary, but it's better than failing
        return response.strip()
    
    def _save_intermediate_result(
        self,
        document_content: str,
        step_number: int,
        agent_name: str,
        base_dir: Path
    ) -> Path:
        """
        Save intermediate document to file.
        
        Args:
            document_content: Document content to save
            step_number: Step number
            agent_name: Agent name
            base_dir: Base directory for intermediate results
            
        Returns:
            Path to saved file
        """
        # Sanitize agent_name for filesystem safety (models may contain '/', ':', etc.)
        safe_agent = re.sub(r"[^a-zA-Z0-9._-]+", "-", (agent_name or "").strip())
        safe_agent = safe_agent.strip("-._") or "agent"
        safe_agent = safe_agent[:80]

        step_dir = base_dir / f"step{step_number}_{safe_agent}"
        step_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = step_dir / f"enhanced_{step_number}.md"
        
        # Use versioned save to avoid overwriting intermediate results
        saved_path = save_text_file_with_versioning(output_file, document_content)
        
        return saved_path
    
    def _create_output_directory(self) -> Path:
        """
        Create output directory with timestamp.
        
        Uses preferred output directory from config if available,
        otherwise falls back to config.output_path or default location.
        
        Returns:
            Path to created directory
        """
        # Priority: 1) config.output_path parent, 2) preferred_output_dir, 3) default
        if self.config.output_path and self.config.output_path.parent.exists():
            base_dir = self.config.output_path.parent
        elif self.config.preferred_output_dir:
            # Use preferred output directory from config
            preferred_dir = Path(self.config.preferred_output_dir).expanduser().resolve()
            preferred_dir.mkdir(parents=True, exist_ok=True)
            base_dir = preferred_dir / "enhanced_documents"
        else:
            # Default fallback
            base_dir = Path.cwd() / "enhanced_documents"
        
        # Create timestamp folder: YYYYMMDD_HHMM
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        output_dir = base_dir / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return output_dir
    
    def _execute_agent_step(
        self,
        agent_config: AgentConfig,
        document_content: str,
        step_number: int,
        previous_agent: Optional[str] = None
    ) -> EnhancementStepResult:
        """
        Execute a single agent step.
        
        Args:
            agent_config: Agent configuration
            document_content: Current document content
            step_number: Step number (1-based)
            previous_agent: Name of previous agent
            
        Returns:
            EnhancementStepResult
        """
        start_time = time.time()
        
        try:
            # Build prompt
            prompt = self._build_prompt(
                document_content=document_content,
                instructions=self.config.enhancement_instructions,
                step_number=step_number - 1,  # Convert to 0-based
                previous_agent=previous_agent
            )
            
            # Call agent
            agent = agent_config.agent_instance
            response_text, response_time_ms, token_usage = agent.generate(prompt)
            
            # Extract enhanced document
            enhanced_document = self._extract_document_from_response(
                response_text,
                document_content
            )
            
            # Create successful result
            return EnhancementStepResult(
                step_number=step_number,
                agent_name=agent_config.agent_name,
                model=agent.model,
                input_document=document_content,
                output_document=enhanced_document,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                success=True,
                error=None
            )
            
        except Exception as e:
            # Log error with full context for debugging
            import logging
            logger = logging.getLogger(__name__)
            
            model_name = "unknown"
            if hasattr(agent_config, 'agent_instance') and hasattr(agent_config.agent_instance, 'model'):
                model_name = agent_config.agent_instance.model
            elif hasattr(agent, 'model'):
                model_name = agent.model
            
            logger.error(
                f"Agent step {step_number} failed: {e}",
                exc_info=True,
                extra={
                    "step_number": step_number,
                    "agent_name": agent_config.agent_name,
                    "model": model_name,
                    "operation": "document_enhancement",
                    "document_length": len(document_content) if document_content else 0
                }
            )
            
            # Create error result
            elapsed_ms = int((time.time() - start_time) * 1000)
            return EnhancementStepResult(
                step_number=step_number,
                agent_name=agent_config.agent_name,
                model=model_name,
                input_document=document_content,
                output_document=document_content,  # Keep original on failure
                response_time_ms=elapsed_ms,
                token_usage=None,
                success=False,
                error=str(e)
            )
    
    def run(
        self,
        on_step_start: Optional[Callable[[int, int, str], None]] = None,
        on_step_complete: Optional[Callable[[int, int, str, EnhancementStepResult], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> DocumentEnhancementResult:
        """
        Execute the enhancement chain.
        
        Args:
            on_step_start: Callback when step starts (step_num, total, agent_name)
            on_step_complete: Callback when step completes (step_num, total, agent_name, result)
            on_progress: Callback for progress updates (current, total)
            
        Returns:
            DocumentEnhancementResult
        """
        start_time = time.time()
        
        # Load source document
        try:
            current_document = self._load_document(self.config.source_document)
        except InvalidDocumentError as e:
            # Return failed result
            return DocumentEnhancementResult(
                config=self.config,
                steps=[],
                final_document="",
                total_time_ms=int((time.time() - start_time) * 1000),
                total_tokens=0,
                total_cost=0.0,
                success=False,
                output_path=None,
                chain_id=self.chain_id
            )
        
        # Create output directory
        output_dir = self._create_output_directory()
        
        # Sort agents by order
        sorted_agents = sorted(self.config.agents, key=lambda a: a.order)
        total_steps = len(sorted_agents)
        
        # Track metrics
        total_tokens = 0
        total_cost = 0.0
        previous_agent_name = None
        
        # Execute each step
        for step_num, agent_config in enumerate(sorted_agents, 1):
            # Callback: step start
            if on_step_start:
                on_step_start(step_num, total_steps, agent_config.agent_name)
            
            # Execute step
            result = self._execute_agent_step(
                agent_config=agent_config,
                document_content=current_document,
                step_number=step_num,
                previous_agent=previous_agent_name
            )
            
            # Save intermediate result if configured
            if self.config.save_intermediate and result.success:
                intermediate_path = self._save_intermediate_result(
                    document_content=result.output_document,
                    step_number=step_num,
                    agent_name=agent_config.agent_name,
                    base_dir=output_dir
                )
                result.intermediate_path = intermediate_path
            
            # Store result
            self.results.append(result)
            
            # Update metrics
            if result.token_usage:
                total_tokens += result.token_usage.total
                total_cost += result.token_usage.cost_estimate
            
            # Callback: step complete
            if on_step_complete:
                on_step_complete(step_num, total_steps, agent_config.agent_name, result)
            
            # Callback: progress
            if on_progress:
                on_progress(step_num, total_steps)
            
            # Handle errors based on configuration
            if not result.success:
                if self.config.on_error == ErrorHandling.STOP:
                    # Stop chain, use current document as final
                    break
                elif self.config.on_error == ErrorHandling.RETRY:
                    # Retry once
                    retry_result = self._execute_agent_step(
                        agent_config=agent_config,
                        document_content=current_document,
                        step_number=step_num,
                        previous_agent=previous_agent_name
                    )
                    if retry_result.success:
                        self.results[-1] = retry_result
                        result = retry_result
                    else:
                        # Retry failed, stop if configured
                        if self.config.on_error == ErrorHandling.STOP:
                            break
                elif self.config.on_error == ErrorHandling.SKIP:
                    # Skip failed step, continue with current document
                    pass
            
            # Update current document for next step
            if result.success:
                current_document = result.output_document
                previous_agent_name = agent_config.agent_name
        
        # Calculate total time
        total_time_ms = int((time.time() - start_time) * 1000)
        
        # Save final document
        final_output_path = output_dir / "enhanced_final.md"
        final_output_path = save_text_file_with_versioning(final_output_path, current_document)
        
        # Determine overall success
        overall_success = all(step.success for step in self.results)
        
        # Store in framework if available
        if self.framework:
            self._store_in_framework(
                final_document=current_document,
                total_cost=total_cost
            )
        
        # Build final result
        return DocumentEnhancementResult(
            config=self.config,
            steps=self.results,
            final_document=current_document,
            total_time_ms=total_time_ms,
            total_tokens=total_tokens,
            total_cost=total_cost,
            success=overall_success,
            output_path=final_output_path,
            chain_id=self.chain_id
        )
    
    def _store_in_framework(self, final_document: str, total_cost: float):
        """
        Store enhancement run in AgentFramework.
        
        Args:
            final_document: Final enhanced document
            total_cost: Total cost of enhancement
        """
        if not self.framework:
            return
        
        try:
            # Create a prompt for the enhancement chain
            instructions = self.config.enhancement_instructions or "Document enhancement"
            
            prompt = self.framework.create_prompt(
                content=instructions,
                version="1.0.0",
                tags=["enhancement", "chain", "document"],
                metadata={
                    "source_document": str(self.config.source_document),
                    "agents": [a.agent_name for a in self.config.agents],
                    "chain_id": self.chain_id,
                    "total_steps": len(self.results),
                    "save_intermediate": self.config.save_intermediate
                }
            )
            
            # Store each step as a response
            for step_result in self.results:
                self.framework.record_response(
                    prompt_id=prompt.id,
                    agent_name=step_result.agent_name,
                    model=step_result.model,
                    response=step_result.output_document,
                    response_time_ms=step_result.response_time_ms,
                    token_usage=step_result.token_usage,
                    metadata={
                        "step_number": step_result.step_number,
                        "chain_id": self.chain_id,
                        "success": step_result.success,
                        "error": step_result.error,
                        "intermediate_path": str(step_result.intermediate_path) if step_result.intermediate_path else None
                    }
                )
        except Exception as e:
            # Don't fail the enhancement if framework storage fails
            import logging
            logger = logging.getLogger(__name__)
            enhancement_id = None
            if hasattr(result, 'enhancement_id'):
                enhancement_id = result.enhancement_id
            logger.warning(
                f"Failed to store enhancement in framework: {e}",
                exc_info=True,
                extra={
                    "operation": "store_enhancement_result",
                    "enhancement_id": enhancement_id
                }
            )


