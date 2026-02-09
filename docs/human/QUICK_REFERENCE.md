# Ouroboros Quick Reference

## File Structure

```
Ouroboros/
├── src/
│   ├── main.py              # Coordination & orchestration
│   ├── comms.py             # Communication with agents
│   ├── filesystem.py        # Storage and retrieval
│   ├── config.py            # Configuration utilities
│   ├── roles.json           # Agent configurations
│   ├── config.json          # API keys and settings
│   └── __pycache__/
├── shared_repo/             # Session storage (auto-created)
│   └── YYYYMMDD_HHMMSSXXX/  # Session directories
│       ├── agent_name_1.txt
│       ├── agent_name_2.txt
│       └── ...
├── REFACTORING_SUMMARY.md   # This refactoring details
├── ARCHITECTURE.md          # System architecture
├── BEST_PRACTICES.md        # Usage patterns and tips
└── README.md                # Project overview
```

---

## Module Quick Reference

### comms.py - Communication Layer

```python
from comms import (
    sanitize_input,              # Validate message structure
    sanitize_output,             # Clean response content
    extract_content_from_response,  # Parse API response
    Channel,                      # Abstract base
    APIChannel,                   # Live communication
    ReplayChannel,                # Replay from disk
    ChannelFactory,               # Create appropriate channel
    CommunicationError,           # Base exception
    ValidationError,              # Invalid input
    APIError,                     # API call failed
)

# Common usage:
from comms import ChannelFactory, extract_content_from_response

factory = ChannelFactory(replay_mode=False)
channel = factory.create_channel(agent_config)
channel.send_message(payload)
response = await channel.receive_message()
content = extract_content_from_response(response)
```

### filesystem.py - Storage Layer

```python
from filesystem import (
    FileSystem,              # Create/manage sessions
    ReadOnlyFileSystem,      # Replay mode (no writes)
    FileSystemError,         # Storage error
)

# Common usage:
from filesystem import FileSystem

# Normal mode
fs = FileSystem(shared_dir="./shared_repo")

# Store output
fs.write_data("agent_name", "response_text")
fs.write_structured_data("agent_name", {"key": "value"})
fs.save_conversation_history("agent_name", messages)

# Replay mode
fs = FileSystem(shared_dir="./shared_repo", replay_mode=True)
output = fs.get_recorded_output("agent_name")
```

### main.py - Coordination Layer

```python
from main import (
    Agent,                   # Individual agent
    CentralCoordinator,      # Multi-agent orchestrator
    OrganizationError,       # Coordination error
)

# Common usage:
from main import CentralCoordinator
from filesystem import FileSystem

filesystem = FileSystem(shared_dir="./shared_repo")
coordinator = CentralCoordinator("roles.json", filesystem)

# Execute request
results = coordinator.assign_and_execute(
    "Your request description"
)

# Or decompose manually
tasks = coordinator.decompose_request("request")
```

### config.py - Configuration

```python
from config import (
    load_config,             # Load JSON config
    get_config_value,        # Get value with defaults
    validate_agent_config,   # Validate agent config
    ConfigError,             # Config error
)

# Common usage:
config = load_config("roles.json")
api_key = get_config_value(config, "api.key", "default")
validate_agent_config(config["agent_1"])
```

---

## Typical Usage Patterns

### Pattern 1: Basic Execution
```python
from main import CentralCoordinator
from filesystem import FileSystem

fs = FileSystem(shared_dir="./shared_repo")
coord = CentralCoordinator("roles.json", fs)
results = coord.assign_and_execute("Your request")
print(results)
```

### Pattern 2: Replay Previous Run
```bash
python main.py --replay
```

### Pattern 3: Custom Agent
```python
from main import Agent

class MyAgent(Agent):
    def execute_task(self, task):
        task["user_prompt"] = "PREFIX: " + task["user_prompt"]
        return super().execute_task(task)
```

### Pattern 4: Error Handling
```python
from comms import CommunicationError, APIError
from main import OrganizationError
from filesystem import FileSystemError

try:
    results = coordinator.assign_and_execute(request)
except ValidationError as e:
    print(f"Invalid input: {e}")
except APIError as e:
    print(f"API failed: {e}")
except FileSystemError as e:
    print(f"Storage failed: {e}")
except OrganizationError as e:
    print(f"Coordination failed: {e}")
```

---

## Configuration Examples

### roles.json Structure
```json
{
  "manager_agent": {
    "name": "Project Manager",
    "role": "manager",
    "system_prompt": "Decompose requests into tasks...",
    "model": "deepseek/deepseek-r1",
    "temperature": 0.7,
    "max_tokens": -1,
    "endpoint": "http://localhost:12345/v1/chat/completions",
    "timeout": 120
  },
  "dev_agent": {
    "name": "Code Developer",
    "role": "developer",
    "system_prompt": "You are a skilled developer...",
    "model": "qwen/qwen3-coder",
    "temperature": 0.5,
    "max_tokens": 8000,
    "endpoint": "http://localhost:12345/v1/chat/completions",
    "timeout": 180
  }
}
```

### config.json Structure
```json
{
  "openai_api_key": "sk-...",
  "api_endpoint": "http://localhost:12345",
  "max_retries": 3,
  "timeout": 120
}
```

---

## Command Reference

### Run Normal Mode
```bash
cd src/
python main.py
```

### Run Replay Mode
```bash
cd src/
python main.py --replay
```

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### List Sessions
```bash
ls shared_repo/
# Shows: 20260207_163210054, 20260207_163220333, etc.
```

### View Session Output
```bash
ls shared_repo/20260207_163220333/
# Shows: agent_name_1.txt, agent_name_2.txt, etc.
```

---

## Exception Reference

| Exception | Module | Cause | Solution |
|-----------|--------|-------|----------|
| `ValidationError` | comms | Invalid message structure | Check message has 'messages' array |
| `APIError` | comms | API request failed | Check endpoint, timeout, or API status |
| `CommunicationError` | comms | General communication issue | Check logs for details |
| `FileSystemError` | filesystem | Storage operation failed | Check disk space and permissions |
| `OrganizationError` | main | Coordination issue | Check agent configs, roles.json |
| `ConfigError` | config | Config file issue | Verify config.json syntax |

---

## Common Debugging Steps

### Issue: Agent not found
```python
# Check configured roles
coordinator.config.keys()

# Find specific role
coordinator._find_agent_config("developer")
```

### Issue: API timeout
```python
# Increase timeout in roles.json
"timeout": 300  # 5 minutes instead of 2
```

### Issue: Response parsing error
```python
# Enable debug logging to see raw response
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Issue: Replay session not found
```bash
# List available sessions
ls shared_repo/
# Ensure session directory exists before running replay
```

### Issue: Out of memory
```python
# Reduce max content length in comms.py
sanitize_output(content, max_length=25000)
```

---

## API Response Handling

### Supported Formats

**OpenAI Format (Primary)**
```json
{
  "choices": [
    {
      "message": {
        "content": "response text"
      }
    }
  ]
}
```

**Raw JSON**
```json
{
  "result": "response text"
}
```

**Plain Text**
```
response text
```

**With Thinking Tags**
```
<think>reasoning</think>
Final answer here
```
(Extracts text after `</think>` tag)

---

## Performance Tips

### Parallel Execution
- Default: 4 concurrent workers
- Increase in `main.py` `_execute_assignments()` for more parallelism
- Watch API rate limits when increasing

### Response Truncation
- Default: 50,000 characters
- Adjust in `comms.py` `sanitize_output()`
- Useful for preventing memory issues

### Timeout Configuration
- Global default: 120 seconds (2 minutes)
- Per-agent: Configure in roles.json
- Per-request: Adjust in coordinator

### Caching Opportunities
- Conversation history storage for context
- Structured data storage for reuse
- Consider caching agent responses

---

## File Format Reference

### Agent Output (.txt)
```
Raw text response from agent
May contain markdown, code, or plain text
Maximum 50,000 characters (default)
```

### Structured Data (.json)
```json
{
  "metadata": {
    "agent": "name",
    "timestamp": "2026-02-07T16:32:20",
    "task": "description"
  },
  "result": {
    "key": "value"
  }
}
```

### Conversation History (.json)
```json
[
  {
    "role": "system",
    "content": "system prompt"
  },
  {
    "role": "user",
    "content": "user message"
  },
  {
    "role": "assistant",
    "content": "agent response"
  }
]
```

---

## Environment Variables (Optional)

```bash
# API Configuration
export OPENAI_API_KEY="sk-..."
export API_ENDPOINT="http://localhost:12345"

# Application Configuration
export SHARED_REPO_DIR="./shared_repo"
export REPLAY_MODE="false"
export LOG_LEVEL="INFO"

# Execution Configuration
export MAX_WORKERS="4"
export AGENT_TIMEOUT="120"
export RESPONSE_MAX_LENGTH="50000"
```

---

## Troubleshooting Checklist

- [ ] roles.json exists and is valid JSON
- [ ] All required agent roles configured
- [ ] API endpoint is reachable
- [ ] Agent system prompts are clear and specific
- [ ] No API rate limiting issues
- [ ] Sufficient disk space for session storage
- [ ] Python version compatible (3.8+)
- [ ] Required packages installed (httpx, etc.)
- [ ] Logging enabled for debugging
- [ ] Session directories have correct permissions

---

## Key Concepts

**Session**: A timestamped directory containing all agent outputs for one execution run

**Role**: A unique identifier for an agent type (e.g., "developer", "reviewer")

**Channel**: Communication mechanism (APIChannel for live, ReplayChannel for recorded)

**Decomposition**: Breaking down a user request into individual agent tasks

**Replay Mode**: Re-execute using previously recorded agent responses for testing

**Sanitization**: Cleaning/validating message content before processing
