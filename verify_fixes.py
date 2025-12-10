#!/usr/bin/env python3
"""
Verification script to test that all bug fixes are working correctly.
Run this to verify the TUI will not crash on startup.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_storage_error_initialization():
    """Test that StorageError accepts keyword arguments"""
    from startd8.exceptions import StorageError
    
    try:
        # This should not raise TypeError anymore
        error = StorageError("Test error", original_error=ValueError("Original"))
        assert error.original_error is not None
        print("✅ StorageError initialization: PASS")
        return True
    except TypeError as e:
        print(f"❌ StorageError initialization: FAIL - {e}")
        return False


def test_datetime_consistency():
    """Test that datetime usage is consistent"""
    from startd8.models import Prompt, AgentResponse, Benchmark
    
    try:
        # Create test objects with default timestamps
        prompt = Prompt(
            id="test-prompt",
            content="Test content",
            version="1.0.0"
        )
        
        response = AgentResponse(
            id="test-response",
            prompt_id="test-prompt",
            agent_name="test",
            model="test-model",
            response="Test response",
            response_time_ms=100
        )
        
        benchmark = Benchmark(
            id="test-benchmark",
            name="Test",
            prompt_id="test-prompt"
        )
        
        # All should have timezone-aware datetimes
        assert prompt.timestamp.tzinfo is not None, "Prompt timestamp should be timezone-aware"
        assert response.timestamp.tzinfo is not None, "Response timestamp should be timezone-aware"
        assert benchmark.created_at.tzinfo is not None, "Benchmark created_at should be timezone-aware"
        
        # Should be able to compare them without error
        items = [prompt.timestamp, response.timestamp, benchmark.created_at]
        sorted_items = sorted(items)  # This would raise TypeError if datetimes are mixed
        
        print("✅ DateTime consistency: PASS")
        return True
    except Exception as e:
        print(f"❌ DateTime consistency: FAIL - {e}")
        return False


def test_storage_list_with_mixed_datetimes():
    """Test that storage can handle mixed timezone-aware/naive datetimes"""
    import tempfile
    import json
    from startd8.storage.backend import FileSystemStorage
    from startd8.models import Prompt
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileSystemStorage(Path(tmpdir))
            
            # Create a prompt with timezone-aware datetime (normal case)
            prompt1 = Prompt(
                id="test-1",
                content="Test 1",
                version="1.0.0",
                timestamp=datetime.now(timezone.utc)
            )
            storage.save_prompt(prompt1)
            
            # Manually create a file with naive datetime (legacy data simulation)
            prompt2_data = {
                "id": "test-2",
                "content": "Test 2",
                "version": "1.0.0",
                "timestamp": datetime.now().isoformat(),  # Naive datetime
                "tags": [],
                "metadata": {}
            }
            prompt2_path = Path(tmpdir) / "prompts" / "test-2.json"
            with open(prompt2_path, 'w') as f:
                json.dump(prompt2_data, f)
            
            # This should not crash even with mixed datetimes
            prompts = storage.list_prompts()
            assert len(prompts) == 2, f"Expected 2 prompts, got {len(prompts)}"
            
            print("✅ Storage list with mixed datetimes: PASS")
            return True
    except Exception as e:
        print(f"❌ Storage list with mixed datetimes: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_framework_error_handling():
    """Test that framework operations don't crash on storage errors"""
    import tempfile
    from startd8.framework import AgentFramework
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            framework = AgentFramework(Path(tmpdir))
            
            # These should return empty lists instead of crashing
            prompts = framework.list_prompts()
            responses = framework.list_responses()
            
            assert isinstance(prompts, list), "list_prompts should return a list"
            assert isinstance(responses, list), "list_responses should return a list"
            
            print("✅ Framework error handling: PASS")
            return True
    except Exception as e:
        print(f"❌ Framework error handling: FAIL - {e}")
        return False


def test_tui_initialization():
    """Test that TUI can initialize without crashing"""
    import tempfile
    from startd8.tui_improved import ImprovedTUI
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # This should not crash even if storage has issues
            tui = ImprovedTUI(Path(tmpdir))
            
            # TUI should have these attributes
            assert hasattr(tui, 'framework'), "TUI should have framework attribute"
            assert hasattr(tui, 'console'), "TUI should have console attribute"
            assert hasattr(tui, 'key_manager'), "TUI should have key_manager attribute"
            
            print("✅ TUI initialization: PASS")
            return True
    except Exception as e:
        print(f"❌ TUI initialization: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests"""
    print("=" * 60)
    print("Bug Fix Verification Script")
    print("=" * 60)
    print()
    
    tests = [
        test_storage_error_initialization,
        test_datetime_consistency,
        test_storage_list_with_mixed_datetimes,
        test_framework_error_handling,
        test_tui_initialization,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ {test.__name__}: EXCEPTION - {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
        print()
    
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All fixes verified! TUI is safe to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

