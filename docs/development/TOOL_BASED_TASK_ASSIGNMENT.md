# Tool-Based Task Assignment System

## Overview
Implemented a tool-based task assignment system for the manager role, replacing JSON-based output parsing with structured tool calls. This provides more reliability, clarity, and consistency with the existing tool-injection pattern used for developer and auditor roles.

## Changes Made

### 1. **New Manager Tools** ([agent_tools.py](src/agent_tools.py))
Added `get_manager_tools_description()` function that documents two task assignment tools:

- **`assign_task(role, task, sequence)`** - Assign a single task to a role
  - `role`: One of 'developer', 'auditor'
  - `task`: Detailed task description (with context for dependencies)
  - `sequence`: Execution order (0=first parallel batch, 1=second, etc.)

- **`assign_tasks(assignments)`** - Assign multiple tasks at once
  - `assignments`: List of objects with 'role', 'task', 'sequence' fields
  - More efficient for batch assignments

### 2. **Manager System Prompt Update** ([roles.json](src/roles.json))
Updated the manager's system prompt to:
- Remove the requirement to output JSON
- Add clear examples of tool usage
- Emphasize parallel vs. sequential task execution patterns

**Before:**
```
Structure your response as ONLY a JSON array with objects containing...
```

**After:**
```
To assign tasks, use the available task assignment tools. Call assign_task() for individual tasks 
or assign_tasks() for multiple tasks at once. For example:
  - assign_task('developer', 'Create auth.py with User class...', sequence=0)
  - assign_task('auditor', 'Review auth.py implementation...', sequence=1)
```

### 3. **Tool Call Extraction** ([main.py](src/main.py))
Added `_extract_assignments_from_tool_calls()` method to `CentralCoordinator`:
- Uses regex patterns to find `assign_task()` and `assign_tasks()` calls in manager's response
- Extracts role, task description, and sequence number
- Parses both single calls and array-based calls
- Returns `None` if no tool calls found

### 4. **Dual Format Support** ([main.py](src/main.py))
Updated `decompose_request()` method to:
1. First try extracting tool calls from manager response
2. Fall back to JSON parsing for legacy format
3. Retry with feedback if neither format produces assignments
4. Maintains backward compatibility with existing JSON-based managers

### 5. **Tool Injection for Manager** ([main.py](src/main.py))
Updated `Agent.__init__()` to:
- Detect manager role
- Inject `get_manager_tools_description()` instead of generic `get_tools_description()`
- Preserve existing tool injection for developer/auditor roles

### 6. **Test Coverage** ([test_main.py](src/test_main.py))
Added `test_decompose_request_with_tool_calls()` test case:
- Verifies tool call extraction from manager response
- Validates that assignments are correctly parsed
- Ensures sequence numbers and roles are properly extracted
- Tests both `assign_task()` single calls and `assign_tasks()` array format

## Benefits

✅ **Reliability**: Tool calls are structured and unambiguous  
✅ **Consistency**: Aligns with file operation tools already used by developer/auditor  
✅ **Clarity**: System prompt is clearer without dense JSON structure  
✅ **Maintainability**: Easier to debug and trace tool calls  
✅ **Flexibility**: Manager can call tools multiple times, handle logic dynamically  
✅ **Backward Compatible**: Still supports legacy JSON format  

## Usage Examples

### Single Task Assignment
```python
assign_task('developer', 'Create auth.py with User class containing username and password fields', sequence=0)
assign_task('auditor', 'Review the auth.py implementation to verify it meets requirements', sequence=1)
```

### Batch Task Assignment
```python
assign_tasks([
    {"role": "developer", "task": "Create module A for database operations", "sequence": 0},
    {"role": "developer", "task": "Create module B for API endpoints", "sequence": 0},
    {"role": "auditor", "task": "Review both modules for code quality and security", "sequence": 1}
])
```

### Manager Decision Logic
The manager can now use conditional logic to decide tasks:
```python
if "database" in request:
    assign_task('developer', 'Design database schema', sequence=0)

if requires_audit:
    assign_task('auditor', 'Review implementation', sequence=1)
```

## Migration Guide

### For Existing Deployments
No action required - the system maintains full backward compatibility with JSON-based managers.

### For New Managers
Use the new tool-based approach for clearer, more maintainable task assignment logic.

### Monitoring
Tool calls are logged with debug-level information, making it easy to trace:
- What assignments were extracted
- How many assignments were found
- Whether fallback to JSON parsing occurred

## Testing
All existing tests pass, including:
- JSON-based task assignment (backward compatibility)
- Tool-based task assignment (new feature)
- Retry logic with corrective feedback
- Role validation
- Sequence-based task execution

Run tests with:
```bash
python -m unittest test_main.TestCentralCoordinator -v
```
