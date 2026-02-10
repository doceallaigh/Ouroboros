# Action Plan: Resolving Code Generation and Callback Issues

## Overview

This document outlines the complete action plan to resolve the issues identified in test run `20260208_222827785` and prevent recurrence.

## Issues Summary

| Issue | Severity | Status | Root Cause |
|-------|----------|--------|-----------|
| Developers don't produce code files | **CRITICAL** | Investigating | Tool execution or file persistence failure |
| Callbacks recorded but not used | **HIGH** | ✅ Fixed | Callback handler not collecting data |
| No final verification pass | **HIGH** | ✅ Fixed | Process flow didn't include quality gate |
| Missing blocker remediation | **MEDIUM** | Identified | No callback routing to manager |
| Error messages truncated | **MEDIUM** | Identified | 200-char limit hides details |

## Completed Improvements

### ✅ Callback Handling Enhancement
- Added `callbacks` list to `CentralCoordinator`
- Updated callback handler to collect all callbacks
- Added `_get_blocker_callbacks()` method
- Implemented blocker logging at WARNING level
- Integrated into final execution summary

### ✅ Final Verification Auditor Pass
- Created `_create_final_verification_task()` method
- Runs after all assignments complete (sequence 99)
- Comprehensive checklist for deliverables
- Produces structured PASS/FAIL report
- Includes context about previous blockers

### ✅ Blocker Summary Reporting
- Final callback analysis and logging
- Clear display of all blockers found
- Count of issues for management visibility

## Next Steps (Priority Order)

### Phase 1: Immediate (Week 1)

#### 1.1 Add File Validation to Task Results
**Objective**: Verify files are actually created after each developer task

**Implementation**:
```python
# After execute_tools_from_response() in _execute_single_assignment
if role == "developer":
    # List files to confirm creations
    files_after = self.filesystem.list_files_in_workspace()
    result["files_created"] = files_after  # For debugging
    result["file_count"] = len(files_after)
```

**Testing**: Run a task, verify "file_count" increases

#### 1.2 Improve Error Reporting
**Objective**: Capture full error details for debugging

**Implementation**:
```python
# In filesystem error handling
self.filesystem.record_event(
    "TOOL_EXECUTION_ERROR",
    {
        "role": role,
        "error": str(e),  # Full error, not truncated
        "error_type": type(e).__name__,
        "traceback": traceback.format_exc() if verbose else None,
        "tool_calls_made": tool_results.get("tool_calls", []) if tool_results else [],
    }
)
```

**Testing**: Introduce an error, verify full stack trace captured

#### 1.3 Document Current Tool Architecture
**Objective**: Understand how tools are supposed to work

**Deliverables**:
- [ ] Diagram showing: Agent → LLM → Tool extraction → File operations
- [ ] Trace through code: Agent → execute_tools_from_response → FileSystem
- [ ] Identify failure points

### Phase 2: Short-term (Week 1-2)

#### 2.1 Create Test Run with Verbose Logging
**Objective**: Capture actual execution to identify where files go missing

**Implementation**:
```bash
# Add verbose flag to run_long_task_impl.py
python -v run_long_task_impl.py 2>&1 | tee verbose_run.log
```

**Analysis**:
- Search for "write_file" in logs
- Search for created files
- Search for errors during tool execution
- Compare expected vs actual files created

#### 2.2 Implement File Integrity Checks
**Objective**: Ensure files persist and are accessible

**Implementation** in final verification auditor:
```python
# Verify previously created files
created_files = []
for task_result in all_results:
    if task_result.get("role") == "developer":
        files = task_result.get("files_created", [])
        for file in files:
            if not file_exists(file):
                raise_callback(f"File {file} created by {task_result['task'][:50]} was lost", "blocker")
            else:
                created_files.append(file)
```

#### 2.3 Add Audit Trail for File Operations
**Objective**: Track every file creation/modification

**Implementation**:
```python
# In FileSystem class
def write_file(self, path: str, content: str):
    self.record_event("FILE_OPERATION", {
        "operation": "write",
        "path": path,
        "size": len(content),
        "timestamp": time.time(),
    })
    # ... actual write ...
    # Verify write succeeded
    if not os.path.exists(path):
        raise FileSystemError(f"Write to {path} failed - file not created")
```

### Phase 3: Medium-term (Week 2-3)

#### 3.1 Implement Callback Routing
**Objective**: Manager receives blocker callbacks and creates remediation tasks

**Implementation**:
```python
def handle_blockers(self, blockers: List[Dict]) -> List[Dict]:
    """Create remediation tasks for blockers."""
    remediation_tasks = []
    for blocker in blockers:
        if "was not created" in blocker["message"]:
            # Create task to generate the missing file
            remediation_tasks.append({
                "role": "developer",
                "task": f"Create {blocker['message'][:100]}",
                "sequence": 100,  # Higher than initial tasks
                "retry_for": blocker["from"],
            })
    return remediation_tasks
```

#### 3.2 Add Tool Execution Validation
**Objective**: Verify tools actually execute

**Implementation**:
```python
class ToolExecutor:
    def execute_and_validate(self, tool_name: str, **kwargs):
        """Execute tool and validate result."""
        result = self.execute(tool_name, **kwargs)
        
        # Validate based on tool type
        if tool_name == "write_file":
            if not os.path.exists(kwargs["path"]):
                raise ToolExecutionError(f"write_file failed: {kwargs['path']} not created")
        
        return result
```

#### 3.3 Implement Retry Logic for Failed Tasks
**Objective**: Automatically retry failed developer tasks

**Implementation**:
```python
def should_retry_task(self, result: Dict) -> bool:
    return (
        result["status"] == "failed" and
        result.get("retry_count", 0) < 3 and
        "API request failed" not in result.get("error", "")
    )
```

### Phase 4: Long-term (Week 3+)

#### 4.1 Refactor Tool Infrastructure
**Objective**: Replace ad-hoc tool system with production framework

**Options**:
1. Use established framework (e.g., LangChain tools)
2. Build custom with built-in validation
3. Hybrid: direct API calls for filesystem

**Recommendation**: Direct filesystem API calls for MVP, then consider framework

#### 4.2 Implement Workspace Persistence
**Objective**: Make filesystem operations more reliable

**Changes**:
- Create actual project directories per session
- Don't delete files between tasks
- Make workspace visible and debuggable
- Add zip export for artifacts

#### 4.3 Add Integration Testing
**Objective**: Prevent regression

**Test cases**:
- [ ] Developer creates file, auditor reads it
- [ ] Multiple developers create different files
- [ ] Files persist through audit phase
- [ ] Final verification finds all deliverables
- [ ] Callbacks properly collected and reported

## Success Metrics

After implementing these changes, verify:

| Metric | Current | Target | How to Measure |
|--------|---------|--------|-----------------|
| Files created by developers | 0% | 100% | Count .py files in shared_repo |
| Callbacks collected | Partial | 100% | `len(coordinator.callbacks)` > 0 |
| Blocker remediation | 0% | 80%+ | Retry tasks for blockers |
| Final verification pass | N/A | Always runs | Look for "FINAL VERIFICATION PHASE" |
| Error details captured | Truncated | Full | Error messages in event log |

## Risk Mitigation

### Risk: Changes break existing functionality
**Mitigation**: 
- All changes are additive (collect callbacks, add verification)
- No breaking changes to method signatures
- Backward compatible with existing code

### Risk: Final verification takes too long
**Mitigation**:
- Auditor tasks have 5-minute timeout
- Configurable verification depth
- Can be skipped for replay mode if needed

### Risk: Callback handling adds overhead
**Mitigation**:
- Callback collection is O(1) append
- Only analysis happens at end
- Negligible performance impact

## Timeline

| Week | Deliverables | Metrics |
|------|--------------|---------|
| Week 1 | Phase 1 (3 items) | Improved error visibility |
| Week 1-2 | Phase 2 (3 items) | Identify root cause, fix basic issues |
| Week 2-3 | Phase 3 (3 items) | Automatic remediation working |
| Week 3+ | Phase 4 (3 items) | Production-ready solution |

## Acceptance Criteria

The issues are considered resolved when:

1. ✅ Code generation: Developers create files that persist
2. ✅ Callbacks: All callbacks collected and analyzed
3. ✅ Verification: Final auditor pass verifies all deliverables
4. ✅ Remediation: Blockers trigger remediation tasks
5. ✅ Visibility: Full error details visible in logs
6. ✅ Testing: Test runs show 100% file creation and persistence

## Dependencies

- Python 3.9+
- Existing agent framework (no new dependencies)
- Filesystem access (already available)

## Rollout Plan

1. **Dev Environment**: Test all changes locally
2. **Staging**: Run full test suite with new code
3. **Production**: Deploy incrementally (Phase 1 first)
4. **Monitoring**: Track metrics from section above
5. **Rollback**: Keep previous version available

## Communication

- **Daily**: Standup with status
- **Weekly**: Progress update to stakeholders
- **Post-completion**: Lessons learned document
- **Continuous**: Issue tracking and updates

## References

- [Analysis of Run 20260208_222827785](../investigations/ANALYSIS_RUN_20260208_222827785.md)
- [Root Cause Analysis](../investigations/ROOT_CAUSE_ANALYSIS_CODE_GENERATION.md)
- [Improvements Implemented](IMPROVEMENTS_CALLBACK_AND_VERIFICATION.md)
