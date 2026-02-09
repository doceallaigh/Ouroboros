# Duplicate Manager Fix - February 8, 2026

## Problem Identified

Multiple manager record files were being created when there should only be one manager call per request decomposition. Example files found:
- `manager01_1770612625549.txt`
- `manager02_1770612633341.txt`

Both files contained the same or similar query, indicating duplicate manager agent instantiation.

## Root Cause

In the `CentralCoordinator.decompose_request()` method (lines 327-427 in main.py), a new manager agent was being created **inside the retry loop**:

```python
for attempt in range(max_retries):
    try:
        manager = self._create_agent_for_role("manager")  # ❌ Created on EACH retry
        decomposition = manager.execute_task({...})
```

When role validation failed and the code retried with corrective feedback, it would:
1. Create manager01 for the first attempt
2. Create manager02 for the retry attempt
3. Both managers would record their queries to separate files

## Solution Implemented

Moved the manager creation **outside and before** the retry loop:

```python
# Create manager once outside the retry loop to avoid duplicate agents
manager = self._create_agent_for_role("manager")

for attempt in range(max_retries):
    try:
        decomposition = manager.execute_task({...})
```

Now the same manager instance is reused for retries, resulting in:
- Only one manager agent created per decompose_request call
- Only one manager file series (manager01_*.txt) per session
- Correct instance counting in the factory pattern

## Factory Pattern Enhancement

The existing factory pattern in `_create_agent_for_role()` already provides:
- **Unique agent identifiers**: `{role}{instance_number:02d}` (e.g., `developer01`, `developer02`, `manager01`)
- **Instance tracking**: `role_instance_counts` dictionary tracks how many instances of each role have been created
- **Sequential numbering**: Ensures agents get unique, sequential identifiers

## Testing

Added comprehensive test case `test_decompose_request_no_duplicate_managers` that:
- Tracks how many times a manager agent is created
- Simulates the retry logic with invalid roles
- Verifies only ONE manager is created despite retries
- Test passes ✓

## Files Modified

1. **src/main.py** (line ~350)
   - Moved manager creation outside retry loop in `decompose_request()`

2. **src/test_main.py** (line ~469)
   - Added `test_decompose_request_no_duplicate_managers()` test case

## Impact

- ✅ Eliminates duplicate manager files
- ✅ Reduces unnecessary API calls
- ✅ Correct instance counting
- ✅ More efficient retry logic
- ✅ Cleaner shared_repo directory structure

## Verification

Run the test suite to verify:
```bash
D:/GitHub/Ouroboros/.venv/Scripts/python.exe -m pytest src/test_main.py -k "duplicate_managers" -v
```

Result: `1 passed` ✓
