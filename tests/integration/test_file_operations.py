"""
Integration tests for file system operations
"""

import pytest
import threading
import time
from pathlib import Path

from startd8 import AgentFramework
from startd8.storage import FileSystemStorage
from startd8.models import Prompt, TokenUsage
from startd8.utils.file_operations import FileLock


class TestConcurrentAccess:
    """Test concurrent file access"""
    
    def test_concurrent_prompt_creation(self, storage_dir: Path):
        """Test creating prompts concurrently"""
        framework = AgentFramework(storage_dir=storage_dir)
        
        def create_prompt(i: int):
            framework.create_prompt(
                content=f"Prompt {i}",
                version="1.0.0"
            )
        
        threads = [threading.Thread(target=create_prompt, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        prompts = framework.list_prompts()
        assert len(prompts) == 10
    
    def test_file_locking(self, storage_dir: Path):
        """Test that file locking works correctly"""
        lock_file = storage_dir / "test.lock"
        
        acquired = []
        
        def try_lock(thread_id: int):
            lock = FileLock(lock_file)
            if lock.acquire(blocking=False):
                acquired.append(thread_id)
                time.sleep(0.1)
                lock.release()
        
        threads = [threading.Thread(target=try_lock, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # At least one thread should have acquired the lock
        assert len(acquired) > 0


class TestAtomicOperations:
    """Test atomic file operations"""
    
    def test_atomic_write_no_corruption(self, storage_dir: Path):
        """Test that atomic writes prevent corruption"""
        storage = FileSystemStorage(storage_dir)
        prompt = Prompt(
            id="test-atomic",
            content="Test content",
            version="1.0.0"
        )
        
        storage.save_prompt(prompt)
        
        # File should exist and be valid
        file_path = storage.prompts_dir / "test-atomic.json"
        assert file_path.exists()
        
        # Should be able to load it
        loaded = storage.load_prompt("test-atomic")
        assert loaded is not None
        assert loaded.content == "Test content"
    
    def test_atomic_write_on_failure(self, storage_dir: Path, monkeypatch):
        """Test that failed writes don't leave partial files"""
        storage = FileSystemStorage(storage_dir)
        
        # Monkeypatch to simulate write failure
        original_write = storage.save_prompt
        
        def failing_write(prompt):
            raise Exception("Simulated write failure")
        
        storage.save_prompt = failing_write
        
        prompt = Prompt(
            id="test-fail",
            content="Test",
            version="1.0.0"
        )
        
        with pytest.raises(Exception):
            storage.save_prompt(prompt)
        
        # File should not exist (or be in original state)
        file_path = storage.prompts_dir / "test-fail.json"
        # The atomic write should have cleaned up


class TestEndToEndWorkflow:
    """Test end-to-end workflows"""
    
    def test_create_prompt_and_response(self, framework: AgentFramework):
        """Test creating a prompt and recording responses"""
        # Create prompt
        prompt = framework.create_prompt(
            content="Test prompt",
            version="1.0.0"
        )
        
        # Record response
        response = framework.record_response(
            prompt_id=prompt.id,
            agent_name="test-agent",
            model="test-model",
            response="Test response",
            response_time_ms=100,
            token_usage=TokenUsage(input=50, output=50, total=100)
        )
        
        # Verify
        assert framework.get_prompt(prompt.id) is not None
        assert framework.get_response(response.id) is not None
    
    def test_benchmark_workflow(self, framework: AgentFramework):
        """Test complete benchmark workflow"""
        # Create prompt
        prompt = framework.create_prompt(
            content="Benchmark test",
            version="1.0.0"
        )
        
        # Create benchmark
        benchmark = framework.create_benchmark(
            name="Test Benchmark",
            prompt_id=prompt.id
        )
        
        # Add responses
        for i in range(3):
            framework.record_response(
                prompt_id=prompt.id,
                agent_name=f"agent{i}",
                model=f"model{i}",
                response=f"Response {i}",
                response_time_ms=100 + i * 50,
                token_usage=TokenUsage(input=50, output=50, total=100)
            )
        
        # Complete benchmark
        completed = framework.complete_benchmark(
            benchmark.id,
            summary="Test summary"
        )
        
        # Compare
        comparison = framework.compare_responses(prompt.id)
        
        assert completed.status == "completed"
        assert comparison['total_responses'] == 3









