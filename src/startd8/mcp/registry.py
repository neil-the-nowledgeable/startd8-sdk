"""
Skill registry for MCP Gateway.

Handles skill discovery, metadata caching, and version tracking.
"""

import asyncio
import time
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SkillMetadata:
    """Metadata for a discovered skill."""
    skill_id: str
    name: str
    description: str
    version: str
    capabilities: List[str]
    tags: List[str]
    last_discovered: float = field(default_factory=time.time)


class SkillRegistry:
    """
    Registry of available skills.
    
    Handles skill discovery, metadata caching, and version tracking.
    
    Example:
        >>> registry = SkillRegistry()
        >>> 
        >>> # Register a skill
        >>> skill = SkillMetadata(
        ...     skill_id="skill-react-game-enhancer",
        ...     name="React Game Enhancer",
        ...     description="Enhances React games",
        ...     version="1.0.0",
        ...     capabilities=["messaging", "HUD"],
        ...     tags=["game", "react"]
        ... )
        >>> await registry.register(skill)
        >>> 
        >>> # Retrieve skill info
        >>> skill_info = await registry.get("skill-react-game-enhancer")
        >>> 
        >>> # List all skills
        >>> all_skills = await registry.list_all()
    """
    
    def __init__(self):
        """Initialize skill registry."""
        self._skills: Dict[str, SkillMetadata] = {}
        self._discovery_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def register(self, skill: SkillMetadata) -> None:
        """
        Register a skill in the registry.
        
        Args:
            skill: Skill metadata to register
        """
        async with self._lock:
            self._skills[skill.skill_id] = skill
            logger.debug(f"Registered skill: {skill.skill_id}")
    
    async def get(self, skill_id: str) -> Optional[SkillMetadata]:
        """
        Get skill metadata by ID.
        
        Args:
            skill_id: The skill identifier
            
        Returns:
            Skill metadata or None if not found
        """
        async with self._lock:
            return self._skills.get(skill_id)
    
    async def list_all(self) -> List[SkillMetadata]:
        """
        List all registered skills.
        
        Returns:
            List of all registered skill metadata
        """
        async with self._lock:
            return list(self._skills.values())
    
    async def is_registered(self, skill_id: str) -> bool:
        """
        Check if skill is registered.
        
        Args:
            skill_id: The skill identifier
            
        Returns:
            True if skill is registered, False otherwise
        """
        async with self._lock:
            return skill_id in self._skills
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with registry statistics
        """
        return {
            'total_skills': len(self._skills),
            'last_discovery': self._discovery_time or 0
        }
