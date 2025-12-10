"""
Test datetime comparison fix in storage layer
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from startd8.models import Prompt
from startd8.storage.base import BaseStorageOperations


def test_list_all_with_mixed_timezone_datetimes():
    """Test that list_all handles mixed timezone-aware and naive datetimes"""
    
    with TemporaryDirectory() as tmpdir:
        storage = BaseStorageOperations(
            storage_dir=Path(tmpdir),
            model_class=Prompt,
            subdirectory="prompts"
        )
        
        # Create prompts with different datetime types
        
        # Timezone-aware datetime
        prompt1 = Prompt(
            id="prompt-1",
            content="First prompt",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 10, 0, 0, tzinfo=timezone.utc)
        )
        
        # Timezone-naive datetime (simulating old data)
        prompt2 = Prompt(
            id="prompt-2",
            content="Second prompt",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 11, 0, 0)  # No tzinfo
        )
        
        # Another timezone-aware
        prompt3 = Prompt(
            id="prompt-3",
            content="Third prompt",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 12, 0, 0, tzinfo=timezone.utc)
        )
        
        # Save all prompts
        storage.save(prompt1)
        storage.save(prompt2)
        storage.save(prompt3)
        
        # This should NOT raise TypeError
        prompts = storage.list_all(sort_key="timestamp", reverse=True)
        
        # Verify sorting works correctly
        assert len(prompts) == 3
        assert prompts[0].id == "prompt-3"  # Most recent
        assert prompts[1].id == "prompt-2"  # Middle
        assert prompts[2].id == "prompt-1"  # Oldest


def test_list_all_with_all_naive_datetimes():
    """Test list_all with all timezone-naive datetimes"""
    
    with TemporaryDirectory() as tmpdir:
        storage = BaseStorageOperations(
            storage_dir=Path(tmpdir),
            model_class=Prompt,
            subdirectory="prompts"
        )
        
        # Create prompts with naive datetimes
        prompt1 = Prompt(
            id="prompt-1",
            content="First",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 10, 0, 0)
        )
        
        prompt2 = Prompt(
            id="prompt-2",
            content="Second",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 11, 0, 0)
        )
        
        storage.save(prompt1)
        storage.save(prompt2)
        
        # Should work fine
        prompts = storage.list_all(sort_key="timestamp", reverse=True)
        assert len(prompts) == 2
        assert prompts[0].id == "prompt-2"


def test_list_all_with_all_aware_datetimes():
    """Test list_all with all timezone-aware datetimes"""
    
    with TemporaryDirectory() as tmpdir:
        storage = BaseStorageOperations(
            storage_dir=Path(tmpdir),
            model_class=Prompt,
            subdirectory="prompts"
        )
        
        # Create prompts with aware datetimes
        prompt1 = Prompt(
            id="prompt-1",
            content="First",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 10, 0, 0, tzinfo=timezone.utc)
        )
        
        prompt2 = Prompt(
            id="prompt-2",
            content="Second",
            version="1.0.0",
            timestamp=datetime(2025, 12, 6, 11, 0, 0, tzinfo=timezone.utc)
        )
        
        storage.save(prompt1)
        storage.save(prompt2)
        
        # Should work fine
        prompts = storage.list_all(sort_key="timestamp", reverse=True)
        assert len(prompts) == 2
        assert prompts[0].id == "prompt-2"


def test_storage_error_accepts_original_error():
    """Test that StorageError accepts original_error parameter"""
    from startd8.exceptions import StorageError
    
    original = ValueError("Original error")
    
    # This should NOT raise TypeError
    error = StorageError("Storage failed", original_error=original)
    
    assert str(error) == "Storage failed"
    assert error.original_error is original


def test_storage_error_without_original():
    """Test StorageError works without original_error"""
    from startd8.exceptions import StorageError
    
    error = StorageError("Storage failed")
    
    assert str(error) == "Storage failed"
    assert error.original_error is None



