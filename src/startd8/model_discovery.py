"""
Model Discovery Service

Discovers new models from provider APIs and merges them with hardcoded model lists.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
from .paths import default_config_dir
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)


class _JsonFileStore:
    """Reusable JSON file-store with atomic writes and malformed-file recovery.

    Shared by :class:`ModelDiscoveryService` (``discovered_models.json``) and
    ``UserModelStore`` (``user_models.json``) so both recover from corruption
    and persist atomically in exactly the same way (REQ-TMM-106, PL-TMM-1).
    """

    def __init__(self, config_dir: Optional[Path], filename: str):
        if config_dir is None:
            config_dir = default_config_dir()
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / filename

    def load_raw(self, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return the parsed JSON object, or a copy of ``default`` on any failure.

        A missing, unreadable, malformed, or non-object file degrades to the
        default rather than raising — callers never crash on corruption.
        """
        base = {} if default is None else dict(default)
        if not self.config_file.exists():
            return base
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Failed to load {self.config_file}: {e}")
            return base
        if not isinstance(data, dict):
            logger.warning(
                f"{self.config_file}: expected a JSON object, got "
                f"{type(data).__name__}; using default"
            )
            return base
        return data

    def save_raw(self, data: Dict[str, Any]) -> bool:
        """Atomically persist ``data`` (temp file + ``os.replace``).

        Returns True on success, False on IO failure (without raising) so the
        in-memory state is preserved on an unwritable path (REQ-TMM-106).
        """
        tmp = self.config_file.with_name(self.config_file.name + '.tmp')
        try:
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.config_file)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Failed to save {self.config_file}: {e}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False


class ModelDiscoveryService:
    """Service for discovering new models from provider APIs"""
    
    CONFIG_FILENAME = "discovered_models.json"
    CACHE_DURATION_HOURS = 24
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize model discovery service.
        
        Args:
            config_dir: Directory to store discovered models config
        """
        self._store = _JsonFileStore(config_dir, self.CONFIG_FILENAME)
        # Preserved for backward compatibility with callers reading these attrs.
        self.config_dir = self._store.config_dir
        self.config_file = self._store.config_file
        self._discovered_models: Dict[str, Dict[str, Any]] = {}
        self._load_discovered_models()

    def _load_discovered_models(self) -> None:
        """Load discovered models from config file"""
        self._discovered_models = self._store.load_raw().get('models', {})

    def _save_discovered_models(self) -> None:
        """Save discovered models to config file"""
        self._store.save_raw({
            'models': self._discovered_models,
            'last_updated': datetime.now().isoformat()
        })
    
    def discover_anthropic_models(self, api_key: Optional[str] = None) -> List[str]:
        """
        Discover Anthropic models from API.
        
        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            
        Returns:
            List of model IDs discovered from API
        """
        if api_key is None:
            api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not api_key:
            logger.warning("No Anthropic API key available for model discovery")
            return []
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                models = []
                for model in data.get('data', []):
                    model_id = model.get('id')
                    if model_id:
                        models.append(model_id)
                
                logger.info(f"Discovered {len(models)} Anthropic models from API")
                return models
        except Exception as e:
            logger.warning(f"Failed to discover Anthropic models: {e}")
            return []
    
    def discover_openai_models(self, api_key: Optional[str] = None) -> List[str]:
        """
        Discover OpenAI models from API.
        
        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            
        Returns:
            List of model IDs discovered from API
        """
        if api_key is None:
            api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            logger.warning("No OpenAI API key available for model discovery")
            return []
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    "https://api.openai.com/v1/models",
                    headers={
                        "Authorization": f"Bearer {api_key}"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                models = []
                for model in data.get('data', []):
                    model_id = model.get('id')
                    # Filter for GPT models only (exclude embeddings, etc.)
                    if model_id and (
                        model_id.startswith('gpt-') or 
                        model_id.startswith('o1-') or
                        model_id.startswith('chatgpt-')
                    ):
                        models.append(model_id)
                
                logger.info(f"Discovered {len(models)} OpenAI models from API")
                return models
        except Exception as e:
            logger.warning(f"Failed to discover OpenAI models: {e}")
            return []
    
    def discover_gemini_models(self, api_key: Optional[str] = None) -> List[str]:
        """
        Discover Google Gemini models from API.
        
        Args:
            api_key: Google API key (uses GOOGLE_API_KEY env var if not provided)
            
        Returns:
            List of model IDs discovered from API
        """
        if api_key is None:
            api_key = os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            logger.warning("No Google API key available for model discovery")
            return []
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key}
                )
                response.raise_for_status()
                data = response.json()
                
                models = []
                for model in data.get('models', []):
                    model_name = model.get('name')
                    if model_name:
                        # Extract model ID from name (e.g., "models/gemini-1.5-flash" -> "gemini-1.5-flash")
                        if '/' in model_name:
                            model_id = model_name.split('/')[-1]
                        else:
                            model_id = model_name
                        models.append(model_id)
                
                logger.info(f"Discovered {len(models)} Gemini models from API")
                return models
        except Exception as e:
            logger.warning(f"Failed to discover Gemini models: {e}")
            return []
    
    def discover_all_models(
        self, 
        api_keys: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[str]]:
        """
        Discover models from all providers.
        
        Args:
            api_keys: Optional dict mapping provider names to API keys
                Format: {'anthropic': 'sk-ant-...', 'openai': 'sk-...', 'gemini': '...'}
        
        Returns:
            Dictionary mapping provider names to lists of discovered model IDs
        """
        results = {}
        
        # Discover Anthropic models
        anthropic_key = None
        if api_keys:
            anthropic_key = api_keys.get('anthropic')
        discovered = self.discover_anthropic_models(anthropic_key)
        if discovered:
            results['anthropic'] = discovered
            self._discovered_models['anthropic'] = {
                'models': discovered,
                'discovered_at': datetime.now().isoformat()
            }
        
        # Discover OpenAI models
        openai_key = None
        if api_keys:
            openai_key = api_keys.get('openai')
        discovered = self.discover_openai_models(openai_key)
        if discovered:
            results['openai'] = discovered
            self._discovered_models['openai'] = {
                'models': discovered,
                'discovered_at': datetime.now().isoformat()
            }
        
        # Discover Gemini models
        gemini_key = None
        if api_keys:
            gemini_key = api_keys.get('gemini')
        discovered = self.discover_gemini_models(gemini_key)
        if discovered:
            results['gemini'] = discovered
            self._discovered_models['gemini'] = {
                'models': discovered,
                'discovered_at': datetime.now().isoformat()
            }
        
        # Save discovered models
        if results:
            self._save_discovered_models()
        
        return results
    
    def get_discovered_models(self, provider: str) -> List[str]:
        """
        Get previously discovered models for a provider.
        
        Args:
            provider: Provider name ('anthropic', 'openai', 'gemini')
            
        Returns:
            List of discovered model IDs
        """
        provider_data = self._discovered_models.get(provider, {})
        return provider_data.get('models', [])
    
    def get_new_models(
        self, 
        provider: str, 
        hardcoded_models: List[str]
    ) -> List[str]:
        """
        Get new models that were discovered but aren't in hardcoded list.
        
        Args:
            provider: Provider name
            hardcoded_models: List of hardcoded model IDs
            
        Returns:
            List of new model IDs
        """
        discovered = set(self.get_discovered_models(provider))
        hardcoded = set(hardcoded_models)
        new_models = discovered - hardcoded
        return sorted(list(new_models))
    
    def merge_models(
        self, 
        provider: str, 
        hardcoded_models: List[str]
    ) -> List[str]:
        """
        Merge discovered models with hardcoded models.
        
        Args:
            provider: Provider name
            hardcoded_models: List of hardcoded model IDs
            
        Returns:
            Merged list of model IDs (hardcoded first, then discovered)
        """
        discovered = self.get_discovered_models(provider)
        hardcoded_set = set(hardcoded_models)
        
        # Start with hardcoded models
        merged = list(hardcoded_models)
        
        # Add discovered models that aren't already in hardcoded list
        for model in discovered:
            if model not in hardcoded_set:
                merged.append(model)
        
        return merged
    
    def is_model_new(self, provider: str, model: str, hardcoded_models: List[str]) -> bool:
        """
        Check if a model is newly discovered (not in hardcoded list).
        
        Args:
            provider: Provider name
            model: Model ID to check
            hardcoded_models: List of hardcoded model IDs
            
        Returns:
            True if model is newly discovered
        """
        discovered = self.get_discovered_models(provider)
        return model in discovered and model not in hardcoded_models
