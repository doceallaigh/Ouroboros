# Audit Workflow Documentation

## Overview

The Ouroboros framework now includes a comprehensive audit workflow that tracks file edits and audits. This replaces the simple `confirm_task_complete` flow with a more robust `record_audit_success` workflow.

## Key Components

### 1. AuditLogManager

Located in `src/fileio/audit_log.py`, the `AuditLogManager` class manages two logs:

- **edit_log**: Records all files that are edited, deleted, or changed with timestamps
- **audit_log**: Records all files that have been audited with timestamps

### 2. Log Files

The system creates two JSON files in the working directory:

- `edit_log.json`: Contains mapping of file paths to edit timestamps
- `audit_log.json`: Contains mapping of file paths to audit timestamps

### 3. Task Completion Logic

A task is considered complete when:
- All files in the `edit_log` also appear in the `audit_log`
- Each audit timestamp is **later than** the corresponding edit timestamp

## Workflow

### For Developers

Developers don't need to do anything special. When they use the following tools, files are automatically tracked in the `edit_log`:

- `write_file(path, content)` - Creates or overwrites a file
- `edit_file(path, diff)` - Edits an existing file
- `delete_file(path)` - Deletes a file

Each of these operations automatically records the file path and timestamp in the `edit_log`.

### For Auditors

Auditors use the new `record_audit_success()` tool to record their audits:

```python
record_audit_success(
    file_paths=["app.py", "utils.py"],
    summary="Reviewed code for security and correctness"
)
```

This function:
1. Records each file path with current timestamp in the `audit_log`
2. Checks if all edited files have been audited
3. Returns status indicating whether the task is complete
4. Sets `task_complete = True` if all edits are audited

### Return Value

The `record_audit_success()` function returns:

```python
{
    "status": "audit_recorded",
    "audited_files": ["app.py", "utils.py"],
    "summary": "Reviewed code...",
    "timestamp": "2026-02-16T01:30:00+00:00",
    "task_complete": True,  # or False
    "message": "All edited files have been audited. Task is complete.",
    # If task is not complete:
    "unaudited_files": ["config.py"]  # List of files still needing audit
}
```

## Example Scenario

1. **Developer creates files:**
   ```python
   write_file("app.py", "print('hello')")
   write_file("utils.py", "def helper(): pass")
   ```
   → Both files recorded in `edit_log`

2. **Auditor reviews one file:**
   ```python
   record_audit_success(file_paths=["app.py"], summary="Looks good")
   ```
   → `app.py` recorded in `audit_log`
   → Task not complete (utils.py not audited)
   → Returns `task_complete=False` with `unaudited_files=["utils.py"]`

3. **Auditor reviews remaining file:**
   ```python
   record_audit_success(file_paths=["utils.py"], summary="All clear")
   ```
   → `utils.py` recorded in `audit_log`
   → All edits are now audited
   → Returns `task_complete=True`

## Configuration

### roles.json

The auditor role now includes both tools:

```json
{
  "auditor": {
    "allowed_tools": [
      "read_file",
      "list_directory",
      "list_all_files",
      "search_files",
      "get_file_info",
      "run_python",
      "raise_callback",
      "confirm_task_complete",  // Legacy support
      "record_audit_success"     // New workflow
    ]
  }
}
```

## Backward Compatibility

The original `confirm_task_complete()` function is still available for backward compatibility. However, new audits should use `record_audit_success()` to take advantage of the timestamp-based tracking.

## Implementation Details

### Timestamp Comparison

Timestamps are in ISO 8601 format (e.g., `2026-02-16T01:30:00+00:00`) and are compared lexicographically. Since ISO 8601 is designed to be sortable, this works correctly:

- `"2026-02-16T01:30:00+00:00"` < `"2026-02-16T01:31:00+00:00"` ✓
- `"2026-02-16T01:30:00+00:00"` == `"2026-02-16T01:30:00+00:00"` (not later) ✗

### File Tracking

File tracking happens in the `_wrap()` method of `ToolEnvironment`:

```python
if track_file:
    path = kwargs.get("path") if kwargs and "path" in kwargs else (args[0] if args else None)
    if path:
        env.files_produced.add(path)
        env.audit_log_manager.record_edit(path)  # New!
```

### Persistence

Logs are persisted to disk immediately after each edit or audit operation, ensuring durability across system restarts.

## Testing

Comprehensive test coverage is provided:

- **fileio/test_audit_log.py**: 18 tests for AuditLogManager
- **main/agent/test_tool_runner.py**: 4 additional tests for integration

All tests pass successfully.

## Benefits

1. **Transparency**: Clear record of what was edited and when it was audited
2. **Accountability**: Timestamps prove audits happened after edits
3. **Traceability**: JSON log files can be reviewed at any time
4. **Completeness**: System ensures all edits are reviewed before completion
5. **Persistence**: Logs survive across system restarts
