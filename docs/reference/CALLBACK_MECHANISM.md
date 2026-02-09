# Callback Mechanism

## Overview

The callback mechanism enables agents to raise issues, request clarification, or query the agent that assigned them work. This creates a hierarchical communication pattern where subordinate agents can communicate back to their task assigners.

## Architecture

### Components

1. **Agent.callback_handler** - Optional callback handler function set by the coordinator
2. **Agent.raise_callback()** - Method for agents to invoke callbacks
3. **Task 'caller' field** - Identifies which agent assigned the task
4. **Callback handler function** - Set in `_execute_single_assignment` when caller is specified

### Data Flow

```
Manager assigns task with "caller": "manager"
    ↓
CentralCoordinator sets callback_handler on developer agent
    ↓
Developer executes task, encounters issue
    ↓
Developer calls raise_callback("Need clarification", "clarification")
    ↓
Callback handler logs event to _events.jsonl
    ↓
(Future: Route callback to manager agent for response)
```

## Usage

### Manager Assigning Tasks

The manager must include a `caller` field in each task assignment:

```json
[
  {
    "role": "developer",
    "task": "Create authentication module",
    "sequence": 1,
    "caller": "manager"
  }
]
```

### Developer Using Callbacks

Developers can use `raise_callback()` in their tool execution code:

```python
# Check if required file exists
if not list_directory('.').count('config.py'):
    raise_callback(
        "Cannot find config.py required for authentication module", 
        "blocker"
    )
```

### Callback Types

- **query** - General questions (default)
- **blocker** - Issues preventing task completion
- **clarification** - Requests for additional information
- **error** - Error conditions requiring attention

## Implementation Details

### Agent Class

```python
class Agent:
    def __init__(self, config, channel_factory, filesystem, instance_number=1):
        # ... existing initialization ...
        self.callback_handler = None  # Set by coordinator when needed
    
    def raise_callback(self, message: str, callback_type: str = "query") -> Optional[str]:
        """
        Raise a callback to the calling agent.
        
        Returns:
            Response from caller if available, None otherwise
        """
        if not self.callback_handler:
            logger.warning(f"Agent {self.name} attempted callback but no handler set")
            return None
        
        try:
            response = self.callback_handler(self.name, message, callback_type)
            return response
        except Exception as e:
            logger.error(f"Callback failed for {self.name}: {e}")
            return None
```

### CentralCoordinator

In `_execute_single_assignment`, the coordinator:

1. Extracts `caller` field from task
2. Creates a callback handler function
3. Sets `agent.callback_handler` before execution
4. Handler logs callbacks to `_events.jsonl` with event type `AGENT_CALLBACK`

### Tool Execution

The `execute_tools_from_response` method includes `raise_callback` in the execution environment:

```python
exec_globals = {
    'read_file': tools.read_file,
    'write_file': tools.write_file,
    # ... other tools ...
    'raise_callback': self.raise_callback,  # Available to agent code
}
```

## Event Logging

Callbacks are logged to `_events.jsonl`:

```json
{
  "timestamp": "2026-02-08T20:45:30.123Z",
  "event_type": "AGENT_CALLBACK",
  "data": {
    "from": "developer01",
    "to": "manager",
    "type": "blocker",
    "message": "Cannot find config.py required..."
  }
}
```

## Future Enhancements

### Callback Response Routing

Currently, callbacks are logged but don't route back to the caller agent for a response. Future enhancement:

```python
def callback_handler(agent_name: str, message: str, callback_type: str) -> Optional[str]:
    # Find caller agent instance
    caller_agent = self._get_agent_by_name(caller)
    
    # Route callback to caller for response
    response = caller_agent.handle_callback(agent_name, message, callback_type)
    
    return response
```

### Callback Context

Future callbacks could include execution context:

```python
raise_callback(
    message="Missing required file",
    callback_type="blocker",
    context={
        "task": current_task,
        "attempted_operation": "read_file('config.py')",
        "working_directory": os.getcwd()
    }
)
```

### Callback Priority

Add priority levels for urgent callbacks:

```python
raise_callback(
    message="Critical security vulnerability detected",
    callback_type="blocker",
    priority="critical"
)
```

## Testing

Tests verify:

1. ✅ `callback_handler` is set when task includes `caller` field
2. ✅ `raise_callback` method exists on Agent class
3. ✅ `raise_callback` handles missing handler gracefully (returns None)
4. ✅ Callbacks are logged to event stream
5. ✅ Tool execution environment includes `raise_callback`

See `src/test_main.py::TestCallbackMechanism` for implementation.

## Configuration

### System Prompts

Developer prompt includes callback instructions:

```
If you encounter blockers or need clarification:
- Use raise_callback('message', 'blocker') to report issues that prevent task completion
- Use raise_callback('message', 'clarification') to request additional information
- Use raise_callback('message', 'query') for general questions to the task assigner
```

Manager prompt requires `caller` field in JSON:

```
Structure your response as ONLY a JSON array with objects containing 
'role', 'task', 'sequence', and 'caller' fields. The 'caller' field 
should always be set to 'manager' to indicate who assigned the task.
```

## Error Handling

- Missing callback handler: logs warning, returns None
- Callback execution error: logs error, returns None
- Invalid callback type: processed normally (no validation)
- Missing caller field: no callback handler set (agent executes normally)

## Performance Considerations

- Callbacks are synchronous - they block task execution
- No timeout on callback handler execution
- Callbacks don't retry on failure
- Future: Consider async callbacks for long-running operations
