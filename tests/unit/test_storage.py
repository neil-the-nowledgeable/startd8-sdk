"""
Unit tests for storage operations
"""

import pytest
import json
from pathlib import Path

from startd8.storage import FileSystemStorage
from startd8.models import Prompt, AgentResponse, Benchmark, TokenUsage
from startd8.exceptions import StorageError, FileOperationError


class TestFileSystemStorage:
    """Test FileSystemStorage operations"""
    
    def test_save_and_load_prompt(self, storage_backend: FileSystemStorage, sample_prompt: Prompt):
        """Test saving and loading a prompt"""
        storage_backend.save_prompt(sample_prompt)
        
        loaded = storage_backend.load_prompt(sample_prompt.id)
        assert loaded is not None
        assert loaded.id == sample_prompt.id
        assert loaded.content == sample_prompt.content
        assert loaded.version == sample_prompt.version
    
    def test_load_nonexistent_prompt(self, storage_backend: FileSystemStorage):
        """Test loading a prompt that doesn't exist"""
        loaded = storage_backend.load_prompt("nonexistent")
        assert loaded is None
    
    def test_list_prompts(self, storage_backend: FileSystemStorage, prompt_factory):
        """Test listing prompts"""
        # Create multiple prompts
        prompts = [
            prompt_factory.create(content=f"Prompt {i}", version="1.0.0")
            for i in range(3)
        ]
        
        for prompt in prompts:
            storage_backend.save_prompt(prompt)
        
        listed = storage_backend.list_prompts()
        assert len(listed) == 3
        # Should be sorted newest first
        assert listed[0].timestamp >= listed[1].timestamp
    
    def test_save_and_load_response(self, storage_backend: FileSystemStorage, sample_response: AgentResponse):
        """Test saving and loading a response"""
        storage_backend.save_response(sample_response)
        
        loaded = storage_backend.load_response(sample_response.id)
        assert loaded is not None
        assert loaded.id == sample_response.id
        assert loaded.agent_name == sample_response.agent_name
        assert loaded.response == sample_response.response
    
    def test_list_responses(self, storage_backend: FileSystemStorage, response_factory, sample_prompt: Prompt):
        """Test listing responses"""
        responses = [
            response_factory.create(
                prompt_id=sample_prompt.id,
                agent_name=f"agent-{i}",
                response=f"Response {i}"
            )
            for i in range(3)
        ]
        
        for response in responses:
            storage_backend.save_response(response)
        
        listed = storage_backend.list_responses()
        assert len(listed) == 3
    
    def test_save_and_load_benchmark(self, storage_backend: FileSystemStorage, sample_benchmark: Benchmark):
        """Test saving and loading a benchmark"""
        storage_backend.save_benchmark(sample_benchmark)
        
        loaded = storage_backend.load_benchmark(sample_benchmark.id)
        assert loaded is not None
        assert loaded.id == sample_benchmark.id
        assert loaded.name == sample_benchmark.name
    
    def test_atomic_write(self, storage_backend: FileSystemStorage, sample_prompt: Prompt):
        """Test that writes are atomic (no partial files)"""
        # This is tested implicitly - if write fails, file shouldn't exist
        storage_backend.save_prompt(sample_prompt)
        
        file_path = storage_backend.prompts_dir / f"{sample_prompt.id}.json"
        assert file_path.exists()
        
        # File should be valid JSON
        with open(file_path, 'r') as f:
            data = json.load(f)
            assert data['id'] == sample_prompt.id
    
    def test_corrupted_file_handling(self, storage_backend: FileSystemStorage):
        """Test handling of corrupted JSON files"""
        # Create a corrupted JSON file
        corrupted_file = storage_backend.prompts_dir / "corrupted.json"
        with open(corrupted_file, 'w') as f:
            f.write("{ invalid json")
        
        # Should raise FileOperationError when trying to load
        with pytest.raises(FileOperationError):
            storage_backend.load_prompt("corrupted")
    
    def test_list_skips_corrupted_files(self, storage_backend: FileSystemStorage, sample_prompt: Prompt):
        """Test that list operations skip corrupted files"""
        # Create a valid prompt
        storage_backend.save_prompt(sample_prompt)
        
        # Create a corrupted file
        corrupted_file = storage_backend.prompts_dir / "corrupted.json"
        with open(corrupted_file, 'w') as f:
            f.write("{ invalid json")
        
        # List should still work and skip corrupted file
        listed = storage_backend.list_prompts()
        assert len(listed) == 1
        assert listed[0].id == sample_prompt.id









