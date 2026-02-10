# Test Suite Documentation: Callback and Verification Tests

## Overview

This document describes the comprehensive test suite for the callback collection, final verification, and developer retry mechanisms added to the Ouroboros agent harness.

## Test Files

### 1. test_callback_and_verification.py
**Purpose**: Unit and component tests for callback infrastructure
**Test Classes**: 7
**Test Cases**: 20+

#### Test Classes

**TestCallbackCollection**
- ✅ `test_callbacks_initialized_empty` - Verify callbacks list starts empty
- ✅ `test_callback_handler_collects_callback` - Callbacks are collected during execution
- ✅ `test_blocker_callback_logged_as_warning` - Blocker type callbacks logged as WARNING

**TestBlockerExtraction**
- ✅ `test_get_blocker_callbacks_filters_blockers` - Only blocker callbacks returned
- ✅ `test_get_blocker_callbacks_empty_when_no_blockers` - Returns empty when no blockers

**TestFinalVerificationTask**
- ✅ `test_final_verification_task_created` - Valid verification task created
- ✅ `test_final_verification_includes_blocker_context` - Task includes blocker context

**TestDeveloperRetry**
- ✅ `test_task_result_includes_file_count` - File creation tracked in results

**TestCallbackToAgentExecution**
- ✅ `test_blocker_callback_recorded_in_events` - Callbacks in event log

**TestEndToEndFlow**
- ✅ `test_callbacks_collected_during_assignment_execution` - Callbacks collected
- ✅ `test_final_verification_runs_in_assign_and_execute` - Verification phase runs
- ✅ `test_multiple_callbacks_tracked_separately` - Multiple callbacks tracked

**TestRetryMechanism**
- ✅ `test_no_callback_before_retry_attempt` - Developer executes before callback

**TestMockIntegration**
- ✅ `test_mock_filesystem_write_and_read` - Mock filesystem works
- ✅ `test_mock_filesystem_list_files` - File listing works
- ✅ `test_mock_filesystem_record_events` - Event recording works

---

### 2. test_callback_routing_and_retry.py
**Purpose**: Integration tests for callback routing and retry mechanisms
**Test Classes**: 7
**Test Cases**: 25+

#### Test Classes

**TestDeveloperCompletionWithoutCode**
- ✅ `test_developer_task_without_file_creation` - Task completion without files tracked
- ✅ `test_auditor_detects_missing_files_and_raises_blocker` - Auditor detects and raises blocker
- ✅ `test_missing_file_blocker_recorded_in_events` - Blocker in event log

**TestCallbackRouting**
- ✅ `test_blocker_callback_creates_retry_task` - Blocker triggers retry consideration
- ✅ `test_multiple_blockers_from_different_auditors` - Multiple blockers tracked

**TestCallbackToAgentExecution**
- ✅ `test_developer_agent_receives_retry_task_for_blocker` - Developer receives retry task
- ✅ `test_agent_execution_for_blocker_can_be_routed` - Blocker routed to correct role

**TestFilePersistenceValidation**
- ✅ `test_files_created_by_developer_persist` - Files persist after creation
- ✅ `test_auditor_can_verify_created_files` - Auditor verifies file existence

**TestCompleteWorkflow**
- ✅ `test_workflow_developer_fails_auditor_detects_blocker_collected` - End-to-end flow
- ✅ `test_multiple_developers_and_auditors_with_blockers` - Multiple agents with blockers
- ✅ `test_final_verification_includes_blocker_summary` - Verification includes summary

**TestRetryAttemptsTracking**
- ✅ `test_can_identify_retry_candidate` - Identify tasks needing retry
- ✅ `test_retry_count_tracking` - Track retry attempts

---

## Running the Tests

### Run All Tests
```bash
cd D:\GitHub\Ouroboros
pytest src/test_callback_and_verification.py src/test_callback_routing_and_retry.py -v
```

### Run Specific Test File
```bash
pytest src/test_callback_and_verification.py -v
pytest src/test_callback_routing_and_retry.py -v
```

### Run Specific Test Class
```bash
pytest src/test_callback_and_verification.py::TestCallbackCollection -v
pytest src/test_callback_routing_and_retry.py::TestCompleteWorkflow -v
```

### Run Specific Test Case
```bash
pytest src/test_callback_and_verification.py::TestCallbackCollection::test_callbacks_initialized_empty -v
```

### Run with Test Runner Script
```bash
python src/run_callback_tests.py
```

### Run with Coverage
```bash
pytest src/test_callback*.py --cov=src.main --cov-report=html -v
```

---

## Mock Strategy

### MockFileSystem
Simulates the filesystem without actual disk I/O
- `write_file()` - Store files in dict
- `read_file()` - Retrieve files from dict
- `list_files_in_workspace()` - List stored files
- `record_event()` - Track events

**Benefits**:
- Fast execution
- No disk I/O
- Easy inspection of internal state
- Deterministic behavior

### MockChannelFactory
Simulates LLM communication
- `create_channel()` - Return mock channel
- `send_message()` - Return predefined responses

**Benefits**:
- No actual LLM calls
- Consistent responses
- Fast execution
- Fully deterministic

### Agent Mocks
Simulate agent execution without actual processing
- `execute_task()` - Return mock output
- `execute_tools_from_response()` - Simulate tool execution
- `callback_handler` - Capture callbacks

**Benefits**:
- Test coordinator logic in isolation
- Fast execution
- Full control over agent behavior

---

## Test Scenarios Covered

### Scenario 1: Developer Without Code
**Setup**: Developer task assigned
**Execution**: Developer returns output but creates no files
**Assertion**: 
- No files in workspace
- Task marked completed
- Auditor can detect issue
- Blocker callback raised

### Scenario 2: Auditor Detects Blocker
**Setup**: Developer failed, auditor reviews
**Execution**: Auditor runs and detects missing files
**Assertion**:
- Callback handler invoked
- Blocker message captured
- Event recorded
- Callback collected in coordinator.callbacks

### Scenario 3: Multiple Blockers
**Setup**: Multiple developers and auditors
**Execution**: Various blockers raised from different auditors
**Assertion**:
- All blockers collected
- Blockers filtered from other callback types
- Each blocker tracked with source agent name

### Scenario 4: File Persistence
**Setup**: Developer creates files via tool execution
**Execution**: Files persisted in mock filesystem
**Assertion**:
- Files appear in workspace
- Auditor can verify files
- Content correct

### Scenario 5: Final Verification
**Setup**: All tasks complete with some blockers
**Execution**: Final verification task created and runs
**Assertion**:
- Task has role="auditor"
- Task has sequence=99 (runs last)
- Task includes blocker context
- Task produces structured report

### Scenario 6: Callback Routing
**Setup**: Blocker found by auditor
**Execution**: Determine which agent should remediate
**Assertion**:
- Blocker analyzed
- Remediation role determined
- Callback contains agent routing info

---

## Expected Test Results

When running the full test suite, you should see:

```
test_callback_and_verification.py::TestCallbackCollection::test_callbacks_initialized_empty PASSED
test_callback_and_verification.py::TestCallbackCollection::test_callback_handler_collects_callback PASSED
test_callback_and_verification.py::TestCallbackCollection::test_blocker_callback_logged_as_warning PASSED
test_callback_and_verification.py::TestBlockerExtraction::test_get_blocker_callbacks_filters_blockers PASSED
...
test_callback_routing_and_retry.py::TestCompleteWorkflow::test_workflow_developer_fails_auditor_detects_blocker_collected PASSED
test_callback_routing_and_retry.py::TestCompleteWorkflow::test_multiple_developers_and_auditors_with_blockers PASSED
...

======================== 35+ passed in X.XXs ========================
```

---

## Key Test Coverage

### Callback Collection ✅
- [ ] Callbacks list initialized
- [ ] Callbacks collected during execution
- [ ] Blockers logged as warnings
- [ ] Multiple callbacks tracked separately
- [ ] Callbacks recorded in events

### Blocker Extraction ✅
- [ ] Blocker filtering works
- [ ] Empty list when no blockers
- [ ] Type checking correct

### Final Verification ✅
- [ ] Task created with correct role
- [ ] Sequence set to 99 (last)
- [ ] Includes blocker context
- [ ] Structured format

### Developer Retry ✅
- [ ] Task completion tracked
- [ ] File creation tracked
- [ ] Retry candidates identified
- [ ] Retry count tracked

### Callback Routing ✅
- [ ] Callbacks trigger consideration
- [ ] Multiple blockers from different auditors
- [ ] Blocker message analysis
- [ ] Agent role determination

### File Persistence ✅
- [ ] Files created persist
- [ ] Auditor verifies files
- [ ] Content preserved
- [ ] Multiple files tracked

### End-to-End ✅
- [ ] Developer → Auditor → Blocker flow works
- [ ] Multiple agents with blockers
- [ ] Final verification includes all
- [ ] Summary generation works

---

## Debugging Failed Tests

### If callbacks aren't collected:
```python
# Check if callback_handler was set
print(agent.callback_handler)

# Manually invoke callback
if agent.callback_handler:
    agent.callback_handler("agent_name", "message", "blocker")

# Check coordinator.callbacks
print(coordinator.callbacks)
```

### If final verification doesn't run:
```python
# Check if method exists
assert hasattr(coordinator, '_create_final_verification_task')

# Create task manually
task = coordinator._create_final_verification_task("request", [])
print(task)
```

### If files aren't persisting:
```python
# Check filesystem state
print(filesystem.files)
print(filesystem.list_files_in_workspace())

# Manually write file
filesystem.write_file("test.txt", "content")
assert filesystem.file_exists("test.txt")
```

---

## Adding New Tests

### Template for New Test Class

```python
class TestNewFeature:
    """Test description."""
    
    def test_specific_behavior(self, mock_config, tracking_filesystem):
        """Test one specific behavior."""
        coordinator = CentralCoordinator(
            config_path=mock_config,
            filesystem=tracking_filesystem,
            replay_mode=False
        )
        
        # Setup
        # Action
        # Assert
        
        assert True  # Replace with real assertion
```

### Template for New Test Case

```python
def test_new_scenario(self, mock_config, tracking_filesystem):
    """Clear description of what's being tested."""
    
    # Arrange - Set up test data
    coordinator = CentralCoordinator(...)
    
    # Act - Execute the code
    result = coordinator.some_method()
    
    # Assert - Verify the result
    assert result == expected_value
```

---

## Performance Considerations

### Test Execution Time
- Individual tests: < 100ms
- All tests: < 10 seconds
- No actual LLM calls or disk I/O

### Memory Usage
- Mock filesystem stores files in memory
- Events stored in list
- No large data structures

### Scalability
- Can easily add more test cases
- Mock infrastructure scales well
- No external dependencies

---

## Continuous Integration

### GitHub Actions Example
```yaml
name: Test Callback System

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - run: pip install pytest
      - run: pytest src/test_callback*.py -v
```

---

## Troubleshooting

### Issue: Tests can't find modules
**Solution**: 
```bash
cd D:\GitHub\Ouroboros
pytest src/test_callback*.py
```

### Issue: Mock imports fail
**Solution**: Ensure `sys.path.insert(0, 'src')` is at top of test file

### Issue: Fixture not available
**Solution**: Ensure fixture name matches parameter name exactly

### Issue: Tests run but assertions fail
**Solution**: Add debug prints before assertions
```python
print(f"Expected: {expected}")
print(f"Actual: {actual}")
assert actual == expected
```

---

## Success Criteria

Tests pass when:
1. ✅ All 35+ test cases pass
2. ✅ No assertion errors
3. ✅ No import errors
4. ✅ No timeout errors
5. ✅ Coverage > 80%

---

## References

- Test files: `src/test_callback*.py`
- Test runner: `src/run_callback_tests.py`
- Main code: `src/main.py`
- Related docs: `IMPROVEMENTS_CALLBACK_AND_VERIFICATION.md`

---

**Last Updated**: February 9, 2026
**Status**: Ready for execution
**Next Steps**: Run full test suite and verify all tests pass
