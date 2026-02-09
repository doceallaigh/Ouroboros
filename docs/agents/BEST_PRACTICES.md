# Ouroboros Best Practices Guide

## Communication Patterns

### 1. Message Validation
Always ensure messages follow the correct structure:
```python
from comms import sanitize_input

message = {
    "messages": [
        {"role": "system", "content": "You are helpful..."},
        {"role": "user", "content": "Do something..."}
    ],
    "model": "model-name",
    "temperature": 0.7,
}

try:
    validated = sanitize_input(message)
except ValidationError as e:
    logger.error(f"Invalid message: {e}")
```

### 2. Response Parsing
Always use the provided parsing function:
```python
from comms import extract_content_from_response

try:
    content = extract_content_from_response(response)
except APIError as e:
    logger.error(f"Failed to parse response: {e}")
```

### 3. Channel Selection
Use ChannelFactory to create appropriate channels:
```python
from comms import ChannelFactory

# Live mode
factory_live = ChannelFactory(replay_mode=False)
channel = factory_live.create_channel(agent_config)

# Replay mode
factory_replay = ChannelFactory(
    replay_mode=True,
    replay_data_loader=filesystem.get_recorded_output
)
channel = factory_replay.create_channel(agent_config)
```

---

## Filesystem Patterns

### 1. Session Management
```python
from filesystem import FileSystem

# Create new session
fs = FileSystem(shared_dir="./shared_repo", replay_mode=False)
print(f"Session ID: {fs.session_id}")
print(f"Working Dir: {fs.working_dir}")

# Load existing session for replay
fs_replay = FileSystem(shared_dir="./shared_repo", replay_mode=True)
```

### 2. Data Storage
```python
# Store agent output
fs.write_data("agent_name", "response_text")

# Store structured data
fs.write_structured_data("agent_name", {
    "result": "value",
    "metadata": "info"
})

# Store conversation history
fs.save_conversation_history("agent_name", [
    {"role": "user", "content": "question"},
    {"role": "assistant", "content": "answer"}
])
```

### 3. Replay Data Retrieval
```python
# In replay mode
data = fs.get_recorded_output("agent_name")
if data:
    logger.info(f"Loaded recorded output: {data}")
else:
    logger.warning("No recorded output found")
```

### 4. Read-Only Safety
```python
from filesystem import ReadOnlyFileSystem

# In replay mode, prevent accidental writes
fs = ReadOnlyFileSystem(shared_dir="./shared_repo", replay_mode=True)

# This will be logged but not executed
fs.write_data("agent", "data")  # Safe - no-op
```

---

## Coordination Patterns

### 1. Simple Request Processing
```python
from main import CentralCoordinator
from filesystem import FileSystem

filesystem = FileSystem(shared_dir="./shared_repo")
coordinator = CentralCoordinator("roles.json", filesystem=filesystem)

results = coordinator.assign_and_execute("Your request here")
```

### 2. Request Decomposition
```python
# Get manager's breakdown of a request
decomposition = coordinator.decompose_request("Complex task description")
print(f"Tasks: {decomposition}")
```

### 3. Manual Task Assignment
```python
# If you want to manually execute specific tasks
assignments = [
    {"role": "developer", "task": "Write the main function"},
    {"role": "reviewer", "task": "Review the code"}
]

results = coordinator._execute_assignments(assignments, original_request)
```

### 4. Single Agent Execution
```python
# Create and use a single agent directly
agent = coordinator._create_agent_for_role("developer")

result = agent.execute_task({
    "user_prompt": "Specific instruction for this agent"
})

print(result)
```

---

## Error Handling

### 1. Communication Errors
```python
from comms import CommunicationError, APIError, ValidationError

try:
    coordinator.assign_and_execute(request)
except ValidationError as e:
    logger.error(f"Invalid input: {e}")
except APIError as e:
    logger.error(f"API communication failed: {e}")
except CommunicationError as e:
    logger.error(f"Communication error: {e}")
```

### 2. Filesystem Errors
```python
from filesystem import FileSystemError

try:
    fs = FileSystem(shared_dir="./shared_repo")
except FileSystemError as e:
    logger.error(f"Filesystem error: {e}")
    # Handle gracefully
```

### 3. Organizational Errors
```python
from main import OrganizationError

try:
    coordinator = CentralCoordinator("roles.json", filesystem)
except OrganizationError as e:
    logger.error(f"Coordinator error: {e}")
    # Handle gracefully
```

---

## Configuration Best Practices

### 1. Agent Configuration
Ensure each agent in `roles.json` has:
```json
{
  "agent_name": {
    "name": "Descriptive Name",
    "role": "unique_role_identifier",
    "system_prompt": "Clear instructions for the agent",
    "model": "model/identifier",
    "temperature": 0.7,
    "max_tokens": -1,
    "endpoint": "http://api.endpoint/v1/...",
    "timeout": 120
  }
}
```

### 2. Role Naming
- Use lowercase, snake_case for role names
- Make role names descriptive (e.g., "code_reviewer" not "reviewer")
- Ensure manager role exists for decomposition

### 3. System Prompts
- Be specific about agent responsibilities
- Include context about available roles/tools
- Provide output format expectations
- Keep prompts concise but comprehensive

---

## Logging and Debugging

### 1. Enable Debug Logging
```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 2. Important Log Points
- `Agent initialization`: Confirms agent readiness
- `Message queueing`: Tracks communication start
- `Response parsing`: Identifies parsing issues
- `Replay mode activation`: Confirms test mode
- `Session creation`: Identifies output directory

### 3. Troubleshooting
```python
# Check filesystem state
metadata = fs.get_session_metadata()
logger.info(f"Session: {metadata}")

# Verify agent configuration
agent = coordinator._create_agent_for_role("role_name")
logger.debug(f"Agent config: {agent.config}")

# Test communication channel
channel = channel_factory.create_channel(agent_config)
logger.debug(f"Channel type: {type(channel).__name__}")
```

---

## Performance Optimization

### 1. Parallel Execution
The coordinator uses ThreadPoolExecutor with default max_workers=4.
To adjust:
```python
# In CentralCoordinator._execute_assignments()
with ThreadPoolExecutor(max_workers=8) as executor:  # Increase for more parallelism
    # ... execution code ...
```

### 2. Timeout Management
Agent timeout is configurable per agent in config:
```json
{
  "agent": {
    "timeout": 300  // 5 minutes
  }
}
```

### 3. Response Truncation
Default max content length is 50,000 characters.
Adjust in `comms.py`:
```python
extract_content_from_response(response, max_length=100000)
```

---

## Replay Mode Workflow

### 1. Record Session
```bash
python main.py  # Records agent responses
# Session stored in shared_repo/20260207_163220333/
```

### 2. Replay Session
```bash
python main.py --replay  # Uses most recent session
```

### 3. Comparing Runs
```python
# Record run 1
results_1 = coordinator.assign_and_execute("request")

# Replay run 1
fs_replay = FileSystem(shared_dir="./shared_repo", replay_mode=True)
coordinator_replay = CentralCoordinator("roles.json", fs_replay)
results_replay = coordinator_replay.assign_and_execute("request")

# Compare results
assert results_1 == results_replay  # Should be identical
```

---

## Advanced Patterns

### 1. Custom Agent Implementations
Extend the Agent class for specialized behavior:
```python
from main import Agent

class SpecializedAgent(Agent):
    def execute_task(self, task):
        # Custom logic before execution
        task["user_prompt"] = self.enhance_prompt(task["user_prompt"])
        return super().execute_task(task)
    
    def enhance_prompt(self, prompt):
        # Add context or formatting
        return f"[SPECIALIZED] {prompt}"
```

### 2. Custom Channel Implementation
Implement specialized communication:
```python
from comms import Channel

class CustomChannel(Channel):
    async def receive_message(self):
        # Custom receive logic
        pass
```

### 3. Callback-Based Processing
Monitor agent execution:
```python
class ObservingCoordinator(CentralCoordinator):
    def _execute_single_assignment(self, role, task, original_request):
        logger.info(f"[STARTING] {role}: {task}")
        result = super()._execute_single_assignment(role, task, original_request)
        logger.info(f"[COMPLETED] {role}: {result.get('status')}")
        return result
```

---

## Common Issues and Solutions

### Issue: "No agent configured for role: X"
**Solution**: Verify role exists in `roles.json` and matches exactly (case-sensitive)

### Issue: "No previous sessions found for replay mode"
**Solution**: Run in normal mode first to create a session, then use --replay

### Issue: "Response missing standard 'choices' structure"
**Solution**: API returned non-standard response. Check endpoint configuration and logs for raw response.

### Issue: Timeout errors
**Solution**: Increase timeout in agent config or increase max_tokens wait time

### Issue: Out of memory with large responses
**Solution**: Reduce max_length in sanitize_output() or adjust max_tokens in agent config

---

## Testing Checklist

- [ ] All agents initialize successfully
- [ ] Message validation catches invalid structures
- [ ] API communication works in live mode
- [ ] Replay mode loads previous session
- [ ] Output sanitization handles edge cases
- [ ] Parallel execution completes without race conditions
- [ ] Error handling recovers gracefully
- [ ] Logging provides sufficient debugging info
- [ ] Session directories created correctly
- [ ] ReadOnlyFileSystem prevents writes
