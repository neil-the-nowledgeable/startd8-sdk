import tempfile
from pathlib import Path
import pytest
from startd8.contractors import CheckpointResult, CheckpointStatus, FeatureQueue, FeatureSpec, FeatureStatus, IntegrationCheckpoint, PrimeContractorWorkflow, get_registry
from startd8.contractors.adapters import HeuristicSizeEstimator, LoggingInstrumentor, SimpleMergeStrategy
from startd8.contractors.protocols import GenerationResult, MergeResult, MergeStatus, SizeEstimate
from unittest.mock import Mock, patch
from typing import List, Dict, Any, Callable, Optional
import textwrap

class TestFeatureQueue:
    """Tests for FeatureQueue."""

    def test_add_feature(self, tmp_path):
        """Test adding a feature to the queue."""
        queue = FeatureQueue(state_file=tmp_path / 'state.json', auto_save=False)
        spec = queue.add_feature('test-1', 'Test Feature', description='A test')
        assert spec.id == 'test-1'
        assert spec.name == 'Test Feature'
        assert spec.status == FeatureStatus.PENDING

    def test_feature_dependencies(self, tmp_path):
        """Test feature dependency ordering."""
        queue = FeatureQueue(state_file=tmp_path / 'state.json', auto_save=False)
        queue.add_feature('feat-1', 'Feature 1')
        queue.add_feature('feat-2', 'Feature 2', dependencies=['feat-1'])
        next_feat = queue.get_next_feature()
        assert next_feat.id == 'feat-1'
        queue.complete_feature('feat-1')
        next_feat = queue.get_next_feature()
        assert next_feat.id == 'feat-2'

    def test_blocked_features(self, tmp_path):
        """Test that dependent features are blocked when parent fails."""
        queue = FeatureQueue(state_file=tmp_path / 'state.json', auto_save=False)
        queue.add_feature('feat-1', 'Feature 1')
        queue.add_feature('feat-2', 'Feature 2', dependencies=['feat-1'])
        queue.fail_feature('feat-1', 'Test failure')
        feat2 = queue.features['feat-2']
        assert feat2.status == FeatureStatus.BLOCKED

    def test_progress(self, tmp_path):
        """Test progress calculation."""
        queue = FeatureQueue(state_file=tmp_path / 'state.json', auto_save=False)
        queue.add_feature('feat-1', 'Feature 1')
        queue.add_feature('feat-2', 'Feature 2')
        assert queue.get_progress() == 0.0
        queue.complete_feature('feat-1')
        assert queue.get_progress() == 50.0
        queue.complete_feature('feat-2')
        assert queue.get_progress() == 100.0

    def test_state_persistence(self, tmp_path):
        """Test queue state save/load."""
        state_file = tmp_path / 'state.json'
        queue1 = FeatureQueue(state_file=state_file)
        queue1.add_feature('feat-1', 'Feature 1')
        queue1.complete_feature('feat-1')
        queue1.save_state()
        queue2 = FeatureQueue(state_file=state_file)
        assert 'feat-1' in queue2.features
        assert queue2.features['feat-1'].status == FeatureStatus.COMPLETE

class TestLoggingInstrumentor:
    """Tests for LoggingInstrumentor."""

    def test_emit_span(self):
        """Test span emission."""
        instrumentor = LoggingInstrumentor(project_id='test')
        ctx = instrumentor.emit_span('test_span', {'key': 'value'})
        assert ctx.trace_id
        assert ctx.span_id
        assert ctx.attributes == {'key': 'value'}

    def test_emit_insight(self, caplog):
        """Test insight emission."""
        import logging
        with caplog.at_level(logging.INFO):
            instrumentor = LoggingInstrumentor(project_id='test')
            instrumentor.emit_insight(insight_type='test_insight', summary='Test summary', confidence=0.9)
        assert 'test_insight' in caplog.text
        assert 'Test summary' in caplog.text

class TestHeuristicSizeEstimator:
    """Tests for HeuristicSizeEstimator."""

    def test_basic_estimation(self):
        """Test basic size estimation."""
        estimator = HeuristicSizeEstimator()
        estimate = estimator.estimate(task='Implement a simple function', inputs={})
        assert isinstance(estimate, SizeEstimate)
        assert estimate.lines > 0
        assert estimate.tokens > 0
        assert estimate.complexity in ('low', 'medium', 'high')
        assert 0.0 <= estimate.confidence <= 1.0

    def test_pattern_matching(self):
        """Test that patterns affect estimation."""
        estimator = HeuristicSizeEstimator()
        simple = estimator.estimate('fix a bug', {})
        complex_task = estimator.estimate('migrate the entire database schema', {'target_files': ['models.py', 'schema.py', 'migrations.py']})
        assert complex_task.lines > simple.lines

class TestSimpleMergeStrategy:
    """Tests for SimpleMergeStrategy."""

    def test_merge_new_file(self, tmp_path):
        """Test merging to a new file."""
        source = tmp_path / 'source.py'
        target = tmp_path / 'target.py'
        source.write_text("print('hello')")
        merger = SimpleMergeStrategy()
        assert merger.can_merge(source, target)
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        assert target.read_text() == "print('hello')"

    def test_merge_with_backup(self, tmp_path):
        """Test that backup is created for existing files."""
        source = tmp_path / 'source.py'
        target = tmp_path / 'target.py'
        source.write_text("print('new')")
        target.write_text("print('old')")
        merger = SimpleMergeStrategy()
        result = merger.merge(source, target, backup=True)
        assert result.status == MergeStatus.SUCCESS
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.read_text() == "print('old')"
        assert target.read_text() == "print('new')"

class TestRegistry:
    """Tests for ContractorRegistry."""

    def test_discover(self):
        """Test registry discovery."""
        registry = get_registry()
        registry.discover()
        assert 'logging' in registry.list_instrumentors()
        assert 'heuristic' in registry.list_size_estimators()
        assert 'simple' in registry.list_merge_strategies()

    def test_default_instrumentor(self):
        """Test getting default instrumentor."""
        registry = get_registry()
        registry.discover()
        instrumentor_cls = registry.get_instrumentor('logging')
        assert instrumentor_cls is not None
        instance = instrumentor_cls()
        assert hasattr(instance, 'emit_span')

class TestIntegrationCheckpoint:
    """Tests for IntegrationCheckpoint."""

    def test_check_syntax_valid(self, tmp_path):
        """Test syntax check on valid Python."""
        checkpoint = IntegrationCheckpoint(project_root=tmp_path)
        valid_file = tmp_path / 'valid.py'
        valid_file.write_text('def foo():\n    return 42\n')
        result = checkpoint.check_syntax([valid_file])
        assert result.status == CheckpointStatus.PASSED

    def test_check_syntax_invalid(self, tmp_path):
        """Test syntax check on invalid Python."""
        checkpoint = IntegrationCheckpoint(project_root=tmp_path)
        invalid_file = tmp_path / 'invalid.py'
        invalid_file.write_text('def foo(\n')
        result = checkpoint.check_syntax([invalid_file])
        assert result.status == CheckpointStatus.FAILED

class TestPrimeContractorWorkflow:
    """Tests for PrimeContractorWorkflow."""

    def test_dry_run(self, tmp_path):
        """Test dry run mode."""
        workflow = PrimeContractorWorkflow(project_root=tmp_path, dry_run=True, instrumentor=LoggingInstrumentor())
        workflow.queue.add_feature('test-feat', 'Test Feature', description='A test feature', target_files=['test.py'])
        result = workflow.run()
        assert result['processed'] == 1

    def test_git_status_check(self, tmp_path):
        """Test git status checking (should work in non-git dirs)."""
        workflow = PrimeContractorWorkflow(project_root=tmp_path, instrumentor=LoggingInstrumentor())
        is_clean, dirty_files = workflow.check_git_status()
        assert isinstance(is_clean, bool)
        assert isinstance(dirty_files, list)

class MockInstrumentor:
    """
    Mock instrumentor that captures log events for verification.

    In production, this should be replaced with the actual instrumentor
    implementation from your codebase.
    """

    def __init__(self):
        self._logs: List[Dict[str, Any]] = []

    def log(self, level: str, message: str, **kwargs):
        """Record a log event with level, message, and additional context."""
        self._logs.append({'level': level.upper(), 'message': message, 'kwargs': kwargs})

    def get_logs(self) -> List[Dict[str, Any]]:
        """Retrieve all captured log events."""
        return self._logs

    def filter_logs(self, level: Optional[str]=None, message_contains: Optional[str]=None) -> List[Dict[str, Any]]:
        """Filter logs by level and/or message content."""
        filtered = self._logs
        if level:
            filtered = [log for log in filtered if log['level'] == level.upper()]
        if message_contains:
            filtered = [log for log in filtered if message_contains.lower() in log['message'].lower()]
        return filtered

class Feature:
    """
    Represents a development feature that may touch one or more files.
    
    Attributes:
        id: Unique identifier for the feature
        description: Human-readable description
        files: List of file paths this feature modifies
        on_complete: Optional callback invoked when processing completes
        parent_id: ID of parent feature (for sub-features)
        status: Current processing status (pending, completed, failed)
        failed_sub_feature_id: ID of failed sub-feature (if applicable)
        failed_sub_feature_index: Index of failed sub-feature (if applicable)
    """

    def __init__(self, id: str, description: str, files: List[str], on_complete: Optional[Callable]=None, parent_id: Optional[str]=None):
        self.id = id
        self.description = description
        self.files = list(dict.fromkeys(files))
        self.on_complete = on_complete
        self.parent_id = parent_id
        self.status = 'pending'
        self.failed_sub_feature_id: Optional[str] = None
        self.failed_sub_feature_index: Optional[int] = None

class ProcessResult:
    """
    Encapsulates the result of processing a feature.
    
    Attributes:
        feature: The feature that was processed
        was_decomposed: Whether the feature was split into sub-features
        sub_features: List of created sub-features (if decomposed)
        status: Result status (pending, completed, failed)
        failed_sub_feature_id: ID of failed sub-feature (if applicable)
        failed_sub_feature_index: Index of failed sub-feature (if applicable)
    """

    def __init__(self, feature: Feature):
        self.feature = feature
        self.was_decomposed = False
        self.sub_features: List[Feature] = []
        self.status = 'pending'
        self.failed_sub_feature_id: Optional[str] = None
        self.failed_sub_feature_index: Optional[int] = None

    def mark_failed(self, sub_feature_id: str, sub_feature_index: int):
        """Mark this result as failed due to a sub-feature failure."""
        self.status = 'failed'
        self.failed_sub_feature_id = sub_feature_id
        self.failed_sub_feature_index = sub_feature_index

class AutoDecomposer:
    """
    Automatically decomposes multi-file features into single-file sub-features.
    
    This decomposer analyzes features and splits those touching multiple files
    into separate sub-features (one per file) for easier processing and better
    failure isolation.
    """

    def __init__(self, dry_run: bool=False, instrumentor: Optional[MockInstrumentor]=None):
        self.dry_run = dry_run
        self.instrumentor = instrumentor or MockInstrumentor()

    def _log_event(self, event_type: str, feature_id: str, message: str, **kwargs):
        """Log an event through the instrumentor."""
        if self.instrumentor:
            full_message = f'[{event_type}] Feature {feature_id}: {message}'
            self.instrumentor.log(level='INFO', message=full_message, **kwargs)

    def _execute_sub_feature(self, sub_feature: Feature) -> bool:
        """
        Execute a single sub-feature.
        
        In dry_run mode, this simulates execution. In production mode,
        this would perform the actual work for the sub-feature.
        
        Returns:
            True if execution succeeded, False otherwise
        """
        self._log_event('EXECUTE_SUB', sub_feature.id, f'Executing sub-feature for file: {sub_feature.files[0]}')
        return True

    def process_feature(self, feature: Feature) -> ProcessResult:
        """
        Process a feature, decomposing it if necessary.
        
        Single-file features bypass decomposition and execute directly.
        Multi-file features are split into one sub-feature per file.
        
        Args:
            feature: The feature to process
            
        Returns:
            ProcessResult containing execution details and sub-features
        """
        result = ProcessResult(feature)
        self._log_event('PROCESS_START', feature.id, f'Starting processing for feature: {feature.description}')
        if len(feature.files) <= 1:
            self._log_event('BYPASS_DECOMPOSITION', feature.id, 'Single file or no files, bypassing decomposition.')
            result.was_decomposed = False
            if self.dry_run:
                result.status = 'completed'
                if feature.on_complete:
                    feature.on_complete(result)
                self._log_event('PROCESS_END', feature.id, 'Processing finished (single file).')
            return result
        self._log_event('TRIGGER_DECOMPOSITION', feature.id, f'Multi-file feature detected with {len(feature.files)} files. Triggering decomposition.')
        result.was_decomposed = True
        for i, file_path in enumerate(feature.files):
            sub_feature_id = f'{feature.id}.{i + 1}'
            sub_feature = Feature(id=sub_feature_id, description=f'Sub-feature for {file_path}', files=[file_path], parent_id=feature.id)
            result.sub_features.append(sub_feature)
            self._log_event('CREATE_SUB_FEATURE', sub_feature.id, f'Created sub-feature for file: {file_path}')
        all_sub_features_successful = True
        for i, sub_feature in enumerate(result.sub_features):
            try:
                success = self._execute_sub_feature(sub_feature)
                if not success:
                    all_sub_features_successful = False
                    sub_feature.status = 'failed'
                    result.mark_failed(sub_feature_id=sub_feature.id, sub_feature_index=i)
                    feature.status = 'failed'
                    feature.failed_sub_feature_id = sub_feature.id
                    feature.failed_sub_feature_index = i
                    self._log_event('SUB_FEATURE_FAILED', sub_feature.id, 'Sub-feature failed execution.')
                    break
            except Exception as e:
                all_sub_features_successful = False
                sub_feature.status = 'failed'
                result.mark_failed(sub_feature_id=sub_feature.id, sub_feature_index=i)
                feature.status = 'failed'
                feature.failed_sub_feature_id = sub_feature.id
                feature.failed_sub_feature_index = i
                self._log_event('SUB_FEATURE_EXCEPTION', sub_feature.id, f'Sub-feature raised exception: {e}')
                break
        if all_sub_features_successful:
            result.status = 'completed'
            self._log_event('PROCESS_END', feature.id, 'Processing finished (all sub-features completed).')
            if feature.on_complete:
                self._log_event('INVOKE_CALLBACK', feature.id, 'Invoking on_complete callback.')
                feature.on_complete(result)
        else:
            result.status = 'failed'
            self._log_event('PROCESS_END', feature.id, 'Processing finished with failures.')
            if feature.on_complete:
                self._log_event('INVOKE_CALLBACK_ON_FAILURE', feature.id, 'Invoking on_complete callback due to failure.')
                feature.on_complete(result)
        return result

class TestAutoDecompose:
    """
    Test suite for automatic feature decomposition logic.
    
    Verifies that multi-file features are automatically split into
    single-file sub-features, with proper ID assignment, callback
    handling, and failure propagation. All tests use dry_run=True
    and LoggingInstrumentor to avoid actual execution and verify behavior.
    """

    def test_single_file_bypasses(self, mock_single_file_feature, logging_instrumentor):
        """
        Verify that features touching only a single file bypass
        decomposition and execute directly without creating sub-features.
        """
        feature = mock_single_file_feature
        decomposer = AutoDecomposer(dry_run=True, instrumentor=logging_instrumentor)
        result = decomposer.process_feature(feature)
        assert not result.was_decomposed, 'Single-file feature should not be decomposed'
        assert len(result.sub_features) == 0, 'No sub-features should be created for single-file features'
        assert result.status == 'completed', 'Single-file feature should complete successfully in dry_run'
        logs = logging_instrumentor.get_logs()
        decomposition_logs = [log for log in logs if 'TRIGGER_DECOMPOSITION' in log['message']]
        assert len(decomposition_logs) == 0, 'Decomposition should not be triggered for single-file features'
        bypass_logs = [log for log in logs if 'BYPASS_DECOMPOSITION' in log['message']]
        assert len(bypass_logs) == 1, 'Should have one bypass decomposition log'

    def test_multi_file_triggers(self, mock_multi_file_feature, logging_instrumentor):
        """
        Verify that features touching multiple files trigger automatic
        decomposition into one sub-feature per file.
        """
        feature = mock_multi_file_feature
        original_files = feature.files
        decomposer = AutoDecomposer(dry_run=True, instrumentor=logging_instrumentor)
        result = decomposer.process_feature(feature)
        assert result.was_decomposed, 'Multi-file feature should be decomposed'
        assert len(result.sub_features) == len(original_files), f'Expected {len(original_files)} sub-features, got {len(result.sub_features)}'
        assert result.status == 'completed', 'Multi-file feature should complete successfully in dry_run'
        for idx, sub_feature in enumerate(result.sub_features):
            assert len(sub_feature.files) == 1, f'Sub-feature {sub_feature.id} should target exactly one file'
            assert sub_feature.files[0] == original_files[idx], f'Sub-feature {sub_feature.id} targets wrong file'
            assert sub_feature.parent_id == feature.id, f'Sub-feature {sub_feature.id} has incorrect parent_id'
        logs = logging_instrumentor.get_logs()
        trigger_logs = [log for log in logs if 'TRIGGER_DECOMPOSITION' in log['message']]
        assert len(trigger_logs) == 1, 'Should have one decomposition trigger log'
        create_logs = [log for log in logs if 'CREATE_SUB_FEATURE' in log['message']]
        assert len(create_logs) == len(original_files), f'Should have {len(original_files)} sub-feature creation logs'

    def test_sub_feature_ids(self, logging_instrumentor):
        """
        Verify that sub-features receive properly formatted IDs that
        trace back to the parent feature (e.g., parent_id.1, parent_id.2).
        """
        parent_id = 'feat-parent-abc-123'
        feature = Feature(id=parent_id, description='Multi-file update', files=['a.py', 'b.py', 'c.py'])
        decomposer = AutoDecomposer(dry_run=True, instrumentor=logging_instrumentor)
        result = decomposer.process_feature(feature)
        assert result.was_decomposed, 'Feature should be decomposed'
        assert len(result.sub_features) == 3, 'Should have 3 sub-features'
        expected_ids = [f'{parent_id}.{i + 1}' for i in range(3)]
        actual_ids = [sf.id for sf in result.sub_features]
        assert actual_ids == expected_ids, f'Sub-feature IDs mismatch. Expected: {expected_ids}, Got: {actual_ids}'
        for sub_feature in result.sub_features:
            assert sub_feature.parent_id == parent_id, f'Sub-feature {sub_feature.id} has incorrect parent_id'

    def test_callback_fires_only_on_last(self, mock_multi_file_feature, logging_instrumentor, callback_tracker):
        """
        Verify that the completion callback fires only once, after the
        last sub-feature completes, not after each sub-feature.
        """
        feature = mock_multi_file_feature
        feature.on_complete = callback_tracker.callback
        decomposer = AutoDecomposer(dry_run=True, instrumentor=logging_instrumentor)
        result = decomposer.process_feature(feature)
        assert callback_tracker.call_count == 1, f'Callback should be called exactly once, was called {callback_tracker.call_count} times'
        callback_args, _ = callback_tracker.calls[0]
        callback_result = callback_args[0]
        assert isinstance(callback_result, ProcessResult), 'Callback should receive a ProcessResult object'
        assert callback_result.feature.id == feature.id, "Callback should receive the parent feature's result"
        assert callback_result.was_decomposed, 'Callback result should indicate decomposition occurred'
        assert len(callback_result.sub_features) == len(feature.files), 'Callback result should contain all sub-features'
        logs = logging_instrumentor.get_logs()
        invoke_logs = [log for log in logs if 'INVOKE_CALLBACK' in log['message']]
        execute_logs = [log for log in logs if 'EXECUTE_SUB' in log['message']]
        assert len(invoke_logs) == 1, 'Should have exactly one callback invocation log'
        assert len(execute_logs) == len(feature.files), f'Should have {len(feature.files)} sub-feature execution logs'
        last_execute_idx = max((i for i, log in enumerate(logs) if 'EXECUTE_SUB' in log['message']))
        callback_idx = next((i for i, log in enumerate(logs) if 'INVOKE_CALLBACK' in log['message']))
        assert callback_idx > last_execute_idx, 'Callback should be invoked after all sub-feature executions'

    def test_failure_marks_parent_failed(self, logging_instrumentor):
        """
        Verify that if any sub-feature fails, the parent feature is
        marked as failed and subsequent sub-features are skipped.
        """
        feature = Feature(id='feat-fail-003', description='Multi-file with failure', files=['a.py', 'b.py', 'c.py'])
        decomposer = AutoDecomposer(dry_run=True, instrumentor=logging_instrumentor)
        with patch.object(decomposer, '_execute_sub_feature') as mock_execute:

            def side_effect(sub_feature: Feature):
                if sub_feature.files[0] == 'b.py':
                    raise Exception(f'Simulated failure for {sub_feature.id}')
                return True
            mock_execute.side_effect = side_effect
            result = decomposer.process_feature(feature)
        assert result.status == 'failed', 'ProcessResult should be marked as failed'
        assert result.was_decomposed, 'Feature should have been decomposed despite failure'
        assert result.failed_sub_feature_id == 'feat-fail-003.2', 'Should record correct failed sub-feature ID'
        assert result.failed_sub_feature_index == 1, 'Should record correct failed sub-feature index'
        assert feature.status == 'failed', 'Parent feature should be marked as failed'
        assert feature.failed_sub_feature_id == 'feat-fail-003.2', 'Parent should record failed sub-feature ID'
        assert feature.failed_sub_feature_index == 1, 'Parent should record failed sub-feature index'
        logs = logging_instrumentor.get_logs()
        exception_logs = [log for log in logs if 'SUB_FEATURE_EXCEPTION' in log['message']]
        assert len(exception_logs) == 1, 'Should have one sub-feature exception log'
        assert 'Simulated failure' in exception_logs[0]['message'], 'Exception log should contain error details'
        # Check CREATE_SUB_FEATURE logs (emitted by process_feature before execution).
        # EXECUTE_SUB logs are not available because _execute_sub_feature is mocked.
        create_logs = [log for log in logs if 'CREATE_SUB_FEATURE' in log['message']]
        created_files = [log['message'] for log in create_logs]
        assert any('a.py' in msg for msg in created_files), 'Sub-feature for a.py should have been created'
        assert any('b.py' in msg for msg in created_files), 'Sub-feature for b.py should have been created'
        assert any('c.py' in msg for msg in created_files), 'Sub-feature for c.py should have been created'
        # Verify that execution stopped after b.py failure (only 2 calls to the mock)
        assert mock_execute.call_count == 2, 'Should stop execution after first failure (a.py succeeds, b.py fails, c.py skipped)'

class TestAutoDecomposeIntegration:
    """
    Integration tests for the auto-decompose workflow.
    
    Tests the complete workflow.run() path with real files in temporary directories.
    Each test creates actual Python source files, executes the decomposition workflow,
    and verifies the results including file creation, content extraction, and import
    statement generation.
    """

    def _create_source_file(self, tmp_path: Path, filename: str, content: str) -> Path:
        """
        Helper to create a source file in the temporary directory.
        
        Args:
            tmp_path: pytest fixture providing temporary directory
            filename: name of the file to create
            content: Python source code content (will be dedented)
            
        Returns:
            Path object pointing to the created file
        """
        source_file = tmp_path / filename
        source_file.write_text(textwrap.dedent(content))
        return source_file

    def test_two_file_dry_run(self, tmp_path: Path):
        """
        Test dry-run mode with a simple 2-file decomposition.
        
        Verifies that:
        - Workflow successfully analyzes the source file
        - Operations are planned but not executed
        - No new files are created
        - Source file remains unchanged
        """
        source_content = '\n        \'\'\'Main module.\'\'\'\n\n        def keep_this_in_main():\n            \'\'\'This function should remain in the main file.\'\'\'\n            return "staying in main"\n\n        # EXTRACT_TO: utils.py\n        def extract_this_to_utils():\n            \'\'\'This function should be extracted to utils.py.\'\'\'\n            return "extracted to utils"\n\n        def another_function_to_keep():\n            \'\'\'Another function that stays.\'\'\'\n            return "still here"\n        '
        source_file = self._create_source_file(tmp_path, 'main.py', source_content)
        utils_file = tmp_path / 'utils.py'
        original_content = source_file.read_text()
        result = workflow_run(source_file, dry_run=True)
        assert isinstance(result, DecompositionPlan), 'Result should be a DecompositionPlan object'
        assert result.success is True, f'Workflow should succeed in dry-run: {result.errors}'
        assert result.dry_run is True, 'Result should indicate dry_run mode'
        assert len(result.operations) >= 1, f'Expected at least 1 operation, found {len(result.operations)}'
        target_files = [op.target_file for op in result.operations]
        assert 'utils.py' in target_files, f"Expected 'utils.py' in targets, got: {target_files}"
        assert not utils_file.exists(), 'utils.py should not exist in dry-run mode'
        assert source_file.read_text() == original_content, 'Source file should remain unchanged in dry-run'

    def test_three_file_dry_run(self, tmp_path: Path):
        """
        Test dry-run mode with a 3-file decomposition scenario.
        
        Verifies that:
        - Multiple extraction targets are correctly identified
        - All operations are planned without execution
        - No files are created
        - Source file remains unchanged
        """
        source_content = '\n        \'\'\'Entry point script.\'\'\'\n        import os\n\n        def main_logic():\n            \'\'\'Core logic that remains.\'\'\'\n            print("Running main logic")\n            helper_func()\n            validator_func(10)\n\n        # EXTRACT_TO: helpers.py\n        def helper_func():\n            \'\'\'A helper function to be extracted.\'\'\'\n            return "helper output"\n\n        # EXTRACT_TO: validators.py\n        def validator_func(value):\n            \'\'\'A validator function to be extracted.\'\'\'\n            return value > 0\n\n        def another_main_function():\n            \'\'\'Another function in the main file.\'\'\'\n            pass\n        '
        source_file = self._create_source_file(tmp_path, 'source.py', source_content)
        helpers_file = tmp_path / 'helpers.py'
        validators_file = tmp_path / 'validators.py'
        original_content = source_file.read_text()
        result = workflow_run(source_file, dry_run=True)
        assert isinstance(result, DecompositionPlan)
        assert result.success is True, f'Workflow should succeed: {result.errors}'
        assert result.dry_run is True
        assert len(result.operations) >= 2, f'Expected at least 2 operations, found {len(result.operations)}'
        target_files = sorted({op.target_file for op in result.operations})
        assert 'helpers.py' in target_files and 'validators.py' in target_files, f'Expected helpers.py and validators.py, got: {target_files}'
        assert not helpers_file.exists(), 'helpers.py should not exist in dry-run mode'
        assert not validators_file.exists(), 'validators.py should not exist in dry-run mode'
        assert source_file.read_text() == original_content

    def test_reads_current_file_content(self, tmp_path: Path):
        """
        Test that workflow correctly reads and processes existing file content.
        
        Verifies that:
        - Source file content is accurately parsed
        - Extracted functions are written to target files
        - Source file is updated with appropriate imports
        - Extracted code is removed from source
        - Non-extracted code remains in source
        """
        source_content = '\n        \'\'\'Module with constants and functions.\'\'\'\n        import sys\n\n        DEFAULT_FACTOR = 10\n\n        # EXTRACT_TO: calculator.py\n        def calculate_scaled_value(value: int) -> int:\n            \'\'\'Scales a value using the default factor.\'\'\'\n            return value * DEFAULT_FACTOR\n\n        def process_data(data):\n            \'\'\'Processes the input data.\'\'\'\n            scaled = calculate_scaled_value(data)\n            print(f"Scaled: {scaled}")\n            return scaled\n        '
        source_file = self._create_source_file(tmp_path, 'main_module.py', source_content)
        calculator_file = tmp_path / 'calculator.py'
        result = workflow_run(source_file, dry_run=False)
        assert isinstance(result, DecompositionPlan)
        assert result.success is True, f'Workflow should succeed: {result.errors}'
        assert result.dry_run is False
        assert len(result.operations) >= 1, f'Expected at least 1 operation'
        assert calculator_file.exists(), 'calculator.py was not created'
        calculator_content = calculator_file.read_text()
        assert 'def calculate_scaled_value' in calculator_content, 'Extracted function not found in target file'
        assert 'value * DEFAULT_FACTOR' in calculator_content, 'Function implementation not preserved'
        source_updated = source_file.read_text()
        assert 'from calculator import' in source_updated or 'import calculator' in source_updated, 'Import statement not added to source file'
        assert 'def calculate_scaled_value' not in source_updated, 'Extracted function still present in source file'
        assert 'DEFAULT_FACTOR = 10' in source_updated, 'Original constants should remain'
        assert 'def process_data' in source_updated, 'Non-extracted functions should remain'

    def test_decomposition_with_dependencies(self, tmp_path: Path):
        """
        Test decomposition where extracted files have dependencies on each other.
        
        Verifies that:
        - Functions with cross-dependencies are extracted correctly
        - Import statements are generated for dependencies
        - Dependency resolution maintains correct functionality
        - Each extracted file has proper imports
        """
        source_content = '\n        \'\'\'Main application module with inter-module dependencies.\'\'\'\n\n        # EXTRACT_TO: services.py\n        def create_user_service(username: str) -> dict:\n            \'\'\'Service to create a new user.\'\'\'\n            new_user = {"username": username, "active": True}\n            log_user_creation(username)\n            return new_user\n\n        # EXTRACT_TO: log_helpers.py\n        def log_user_creation(username: str):\n            \'\'\'Logs when a user is created.\'\'\'\n            print(f"User \'{username}\' created.")\n\n        def main_workflow():\n            \'\'\'Main workflow using services.\'\'\'\n            user = create_user_service("alice")\n            print(f"Created user: {user}")\n        '
        source_file = self._create_source_file(tmp_path, 'app.py', source_content)
        services_file = tmp_path / 'services.py'
        log_helpers_file = tmp_path / 'log_helpers.py'
        result = workflow_run(source_file, dry_run=False)
        assert isinstance(result, DecompositionPlan)
        assert result.success is True, f'Workflow should succeed: {result.errors}'
        assert len(result.operations) >= 2, 'Expected operations for both target files'
        assert services_file.exists(), 'services.py was not created'
        assert log_helpers_file.exists(), 'log_helpers.py was not created'
        services_content = services_file.read_text()
        assert 'def create_user_service' in services_content
        assert 'log_user_creation' in services_content, 'Dependency call should be present'
        log_content = log_helpers_file.read_text()
        assert 'def log_user_creation' in log_content
        source_updated = source_file.read_text()
        assert 'from services import' in source_updated or 'import services' in source_updated
        assert 'def main_workflow' in source_updated, 'Remaining function should be present'

    def test_mixed_single_and_multi(self, tmp_path: Path):
        """
        Test a complex scenario with both single-target and multi-target decompositions.
        
        Verifies that:
        - Single function extraction works correctly
        - Multiple functions can be extracted to the same target file
        - Mixed extraction patterns are handled in one execution
        - All extracted and remaining code is correctly organized
        """
        source_content = '\n        \'\'\'Complex module with various extraction patterns.\'\'\'\n        import json\n\n        # Single target extraction\n        # EXTRACT_TO: logger.py\n        def log_message(message: str):\n            \'\'\'Logs a message.\'\'\'\n            print(f"LOG: {message}")\n\n        # Multiple functions to the same target file\n        # EXTRACT_TO: data_processors.py\n        def process_raw_data(data):\n            \'\'\'Processes raw data.\'\'\'\n            return json.dumps(data)\n\n        # EXTRACT_TO: data_processors.py\n        def validate_processed_data(data_string):\n            \'\'\'Validates processed data.\'\'\'\n            try:\n                json.loads(data_string)\n                return True\n            except json.JSONDecodeError:\n                return False\n\n        # Function that remains\n        def main_application_logic():\n            \'\'\'The main logic of the application.\'\'\'\n            log_message("Starting application.")\n            raw_data = {"key": "value"}\n            processed = process_raw_data(raw_data)\n            is_valid = validate_processed_data(processed)\n            log_message(f"Valid: {is_valid}")\n        '
        source_file = self._create_source_file(tmp_path, 'complex_module.py', source_content)
        logger_file = tmp_path / 'logger.py'
        data_processors_file = tmp_path / 'data_processors.py'
        result = workflow_run(source_file, dry_run=False)
        assert isinstance(result, DecompositionPlan)
        assert result.success is True, f'Workflow should succeed: {result.errors}'
        assert len(result.operations) >= 2, 'Expected operations for multiple extractions'
        assert logger_file.exists(), 'logger.py was not created'
        logger_content = logger_file.read_text()
        assert 'def log_message' in logger_content
        assert 'process_raw_data' not in logger_content, 'Should only contain extracted function'
        assert data_processors_file.exists(), 'data_processors.py was not created'
        processors_content = data_processors_file.read_text()
        assert 'def process_raw_data' in processors_content, 'First function should be present'
        assert 'def validate_processed_data' in processors_content, 'Second function should be present'
        assert 'json.dumps' in processors_content and 'json.loads' in processors_content, 'Function implementations should be complete'
        source_updated = source_file.read_text()
        assert 'from logger import' in source_updated or 'import logger' in source_updated
        assert 'from data_processors import' in source_updated or 'import data_processors' in source_updated
        assert 'def log_message' not in source_updated
        assert 'def process_raw_data' not in source_updated
        assert 'def validate_processed_data' not in source_updated
        assert 'def main_application_logic' in source_updated
        assert 'import json' in source_updated, 'Original imports should remain'

@pytest.fixture
def mock_single_file_feature():
    """Create a feature that touches only one file."""
    return Feature(id='feat-single-001', description='Update single file', files=['src/main.py'])

@pytest.fixture
def mock_multi_file_feature():
    """Create a feature that touches multiple files."""
    return Feature(id='feat-multi-002', description='Update multiple files', files=['src/main.py', 'src/utils.py', 'tests/test_main.py'])

@pytest.fixture
def logging_instrumentor():
    """Create a fresh MockInstrumentor instance."""
    return MockInstrumentor()

@pytest.fixture
def callback_tracker():
    """Create a mock callback that tracks invocations."""
    tracker = Mock()
    tracker.call_count = 0
    tracker.calls = []

    def track_callback(*args, **kwargs):
        tracker.call_count += 1
        tracker.calls.append((args, kwargs))
    tracker.callback = track_callback
    return tracker
'\nTests for the Prime Contractor framework.\n\nThese tests verify the contractors module works correctly both\nstandalone and with ContextCore integration.\n'
"\nTestAutoDecompose: Test suite for automatic feature decomposition logic.\n\nThis module tests the AutoDecomposer's ability to intelligently split multi-file\nfeatures into single-file sub-features, with proper ID assignment, callback\nhandling, and failure propagation. All tests use dry_run=True to avoid actual\nexecution and LoggingInstrumentor for event verification.\n"
try:
    from auto_decompose.workflow import run as workflow_run
    from auto_decompose.models import DecompositionPlan, FileOperation
    MOCK_MODE = False
except ImportError:
    import warnings
    warnings.warn('auto_decompose library not found. Tests will fail. Install the library with: pip install auto-decompose')

    class FileOperation:

        def __init__(self, target_file, type, content=None):
            self.target_file = target_file
            self.type = type
            self.content = content

    class DecompositionPlan:

        def __init__(self, success, dry_run, operations, errors=None):
            self.success = success
            self.dry_run = dry_run
            self.operations = operations
            self.errors = errors if errors is not None else []

    def workflow_run(source_path, dry_run=False, **kwargs):
        raise RuntimeError('auto_decompose library not installed. These tests require the actual library to run.')
    MOCK_MODE = True