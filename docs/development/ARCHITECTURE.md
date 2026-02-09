# Ouroboros Architecture Documentation

## System Overview

Ouroboros is a collaborative multi-agent framework designed to harness the power of multiple AI agents working together to develop complex software products. The system itself can iterate on and improve the communication harness.

### Core Philosophy
- **Separation of Concerns**: Each module has a single, well-defined responsibility
- **Composability**: Agents can be easily added, removed, or modified
- **Reproducibility**: Replay mode enables exact reconstruction of previous runs
- **Transparency**: Comprehensive logging and data storage for full audit trail

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│          (Coordination & Orchestration Layer)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  CentralCoordinator                                  │   │
│  │  - Request decomposition                            │   │
│  │  - Agent assignment                                 │   │
│  │  - Parallel execution management                    │   │
│  │  - Result aggregation                               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         ↑                              ↑
         │                              │
┌────────┴────────────────────┬────────┴──────────────────────┐
│                             │                               │
│      comms.py               │       filesystem.py           │
│  (Communication Layer)      │  (Storage & Retrieval Layer)  │
│  ┌────────────────────┐    │  ┌────────────────────────┐   │
│  │ Channel            │    │  │ FileSystem             │   │
│  │ - APIChannel       │    │  │ - Session Management   │   │
│  │ - ReplayChannel    │    │  │ - Data Storage         │   │
│  │                    │    │  │ - Replay Data Loading  │   │
│  │ Sanitization       │    │  │ - ReadOnlyFileSystem   │   │
│  │ - sanitize_input   │    │  │                        │   │
│  │ - sanitize_output  │    │  └────────────────────────┘   │
│  │ - extract_content  │    │                               │
│  └────────────────────┘    │                               │
└────────────────────────────┴───────────────────────────────┘
         ↑                              ↑
         │                              │
┌────────┴────────────────────┬────────┴──────────────────────┐
│                             │                               │
│   Agent                     │     config.py                 │
│  (Execution Unit)           │  (Configuration)              │
│  - Task execution           │  - Config loading             │
│  - Prompt building          │  - Value retrieval            │
│  - Response processing      │  - Validation                 │
└─────────────────────────────┴───────────────────────────────┘
```

---

## Data Flow Diagrams

### 1. Normal Execution Flow

```
User Request
    │
    ↓
CentralCoordinator.assign_and_execute()
    │
    ├─→ Manager Agent (decompose_request)
    │       │
    │       ├─→ APIChannel.send_message()
    │       ├─→ APIChannel.receive_message()
    │       └─→ extract_content_from_response()
    │
    ├─→ Parse Decomposition
    │
    ├─→ ThreadPoolExecutor
    │       │
    │       ├─→ Agent 1 (execute_task)
    │       │       ├─→ Channel.send_message()
    │       │       ├─→ Channel.receive_message()
    │       │       └─→ FileSystem.write_data()
    │       │
    │       ├─→ Agent 2 (execute_task)
    │       │       └─→ ...
    │       │
    │       └─→ Agent N (execute_task)
    │               └─→ ...
    │
    └─→ Aggregate Results
            │
            ↓
        Return Results
```

### 2. Replay Flow

```
CentralCoordinator.__init__(replay_mode=True)
    │
    ├─→ FileSystem._get_latest_session_id()
    │       └─→ Lists shared_repo and finds latest timestamp
    │
    ├─→ ChannelFactory(replay_mode=True)
    │       └─→ Creates ReplayChannel instead of APIChannel
    │
    └─→ assign_and_execute("same request")
            │
            ├─→ Manager Agent
            │       └─→ ReplayChannel.receive_message()
            │               └─→ FileSystem.get_recorded_output()
            │
            ├─→ Worker Agents
            │       └─→ ReplayChannel.receive_message()
            │               └─→ FileSystem.get_recorded_output()
            │
            └─→ Results (identical to original run)
```

### 3. Message Validation Flow

```
sanitize_input(message)
    │
    ├─→ Check is dict
    ├─→ Check has 'messages' field
    ├─→ Check messages is non-empty list
    │
    └─→ For each message:
            ├─→ Check is dict
            ├─→ Check has 'role' and 'content'
            ├─→ sanitize_output(content)
            │       ├─→ Check is string
            │       ├─→ Truncate if > max_length
            │       ├─→ Remove null bytes
            │       └─→ Strip whitespace
            │
            └─→ Update message with sanitized content
```

---

## Component Interactions

### Agent Lifecycle

```
1. INITIALIZATION
   Agent(config, channel_factory, filesystem)
       ├─→ Store configuration
       ├─→ Create channel via factory
       └─→ Log initialization

2. TASK EXECUTION
   agent.execute_task(task)
       ├─→ Build payload (system + user messages)
       ├─→ Validate with sanitize_input()
       ├─→ Channel.send_message(payload)
       ├─→ asyncio.run(Channel.receive_message())
       ├─→ extract_content_from_response()
       ├─→ FileSystem.write_data() [for replay]
       └─→ Return result

3. STORAGE
   FileSystem.write_data(agent_name, result)
       ├─→ Create filename: {agent_name}.txt
       ├─→ Write with UTF-8 encoding
       └─→ Log operation
```

### Channel Decision Tree

```
ChannelFactory.create_channel(config)
    │
    ├─→ If replay_mode == True
    │       └─→ ReplayChannel
    │           ├─→ send_message() → no-op
    │           └─→ receive_message() → load from disk
    │
    └─→ If replay_mode == False
            └─→ APIChannel
                ├─→ send_message() → queue message
                ├─→ receive_message() → post HTTP request
                ├─→ Handle timeout (120s default)
                └─→ Return HTTPXResponse
```

---

## Module Dependencies

```
main.py
├── imports comms.py
│   ├── Channel, ChannelFactory
│   ├── extract_content_from_response()
│   └── CommunicationError
├── imports filesystem.py
│   ├── FileSystem, ReadOnlyFileSystem
│   └── FileSystemError
└── imports config.py
    └── (optional for advanced use)

comms.py
├── imports httpx
└── (no internal imports)

filesystem.py
├── imports os, json, logging
└── (no internal imports)

config.py
├── imports json, logging
└── (no internal imports)
```

**Dependency Graph:**
```
config.py ←─ (optional)
            ↑
           /
comms.py ─┘
  ↑
  │
main.py ←───── filesytem.py
```

---

## Configuration Structure

```
roles.json (Agent Definitions)
├── agent_1
│   ├── name: string (display name)
│   ├── role: string (unique identifier)
│   ├── system_prompt: string (instructions)
│   ├── model: string (model identifier)
│   ├── temperature: float (0-2)
│   ├── max_tokens: int (-1 for unlimited)
│   ├── endpoint: string (API URL)
│   └── timeout: int (seconds)
│
├── agent_2
│   └── ...
│
└── manager (required)
    ├── role: "manager"
    └── system_prompt: (includes task decomposition logic)
```

---

## Error Hierarchy

```
Exception
├── CommunicationError (comms.py)
│   ├── ValidationError
│   │   └── Invalid message structure
│   └── APIError
│       ├── HTTP request failures
│       ├── Timeouts
│       └── Response parsing failures
│
├── FileSystemError (filesystem.py)
│   ├── Initialization failures
│   ├── Read failures
│   └── Write failures
│
└── OrganizationError (main.py)
    ├── Coordinator initialization failures
    ├── Agent creation failures
    ├── Request processing failures
    └── Task execution failures
```

---

## State Management

### Session State

```
FileSystem Instance
├── session_id: str (timestamp-based)
├── shared_dir: str (root storage path)
├── working_dir: str (current session path)
└── Data Files
    ├── agent_name_1.txt (agent output)
    ├── agent_name_2.txt (agent output)
    ├── agent_name_1_structured.json (JSON data)
    ├── agent_name_1_history.json (conversation history)
    └── [other agent files...]
```

### Agent State

```
Agent Instance
├── config: Dict (agent configuration)
├── name: str
├── role: str
├── channel: Channel (APIChannel or ReplayChannel)
└── filesystem: FileSystem (reference)
```

### Coordinator State

```
CentralCoordinator Instance
├── config: Dict (all agents' configs from roles.json)
├── filesystem: FileSystem (shared storage)
├── replay_mode: bool
└── channel_factory: ChannelFactory
```

---

## Concurrency Model

### Threading

The system uses Python's `ThreadPoolExecutor` for parallel agent execution:

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {}
    for task in assignments:
        future = executor.submit(
            _execute_single_assignment,
            role, task, original_request
        )
        futures[task_id] = future
    
    # Wait for all to complete (blocking)
    for future in futures.values():
        result = future.result(timeout=300)
```

**Characteristics:**
- Thread pool: 4 concurrent workers (adjustable)
- Per-task timeout: 300 seconds (5 minutes)
- Blocking collection (waits for all to complete)
- Exception handling per task (one failure doesn't stop others)

### Async Operations

Individual API calls use async/await:

```python
async def receive_message(self):
    async with AsyncClient() as client:
        response = await client.post(...)
    return response
```

Called synchronously from synchronous code:
```python
response = asyncio.run(channel.receive_message())
```

---

## Extensibility Points

### 1. Custom Channel Types
Implement the `Channel` interface:
```python
class CustomChannel(Channel):
    def send_message(self, message: Dict[str, Any]) -> None:
        # Custom implementation
        pass
    
    async def receive_message(self) -> HTTPXResponse:
        # Custom implementation
        pass
```

### 2. Custom Agents
Subclass `Agent`:
```python
class SpecializedAgent(Agent):
    def execute_task(self, task):
        # Custom pre/post processing
        pass
```

### 3. Custom Coordinators
Subclass `CentralCoordinator`:
```python
class CustomCoordinator(CentralCoordinator):
    def decompose_request(self, user_request):
        # Custom decomposition logic
        pass
```

### 4. Custom Filesystems
Subclass `FileSystem`:
```python
class DatabaseFileSystem(FileSystem):
    def write_data(self, agent_name, data):
        # Write to database instead
        pass
```

---

## Performance Considerations

### Bottlenecks
1. **API Response Time**: Typically 2-30 seconds per agent
2. **Parallel Task Count**: Limited to 4 concurrent workers
3. **Message Size**: Truncated at 50,000 characters
4. **Session Loading**: Disk I/O for large session histories

### Optimization Strategies
1. Increase ThreadPoolExecutor max_workers (with caution)
2. Implement caching for repeated requests
3. Use streaming for large responses
4. Implement rate limiting for API endpoints
5. Use async I/O for filesystem operations

---

## Security Considerations

### Input Validation
- Message structure validated before sending
- Content length enforced (truncation)
- Null bytes and problematic characters removed

### Output Sanitization
- Response content truncated at max length
- Special characters handled safely
- Encoding-safe file I/O

### Replay Safety
- ReadOnlyFileSystem prevents accidental data corruption
- No write operations in replay mode

### Configuration
- API keys managed externally (in config.json)
- Not logged or stored in code
- Consider environment variables for sensitive data

---

## Monitoring and Observability

### Logging Strategy

The system provides comprehensive logging:
- **DEBUG**: Detailed execution flow, channel operations
- **INFO**: Agent initialization, task completion, session creation
- **WARNING**: Non-standard responses, missing data
- **ERROR**: Failures and exceptions

Configure via:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Key Metrics
- Session ID (for traceability)
- Agent execution times
- Success/failure rates
- API response times
- Response sizes

### Debugging Tips
1. Enable DEBUG logging
2. Check working_dir for stored outputs
3. Use replay mode to reproduce issues
4. Review exception messages and stack traces

---

## Future Architecture Enhancements

### Phase 2: Persistence
- Database backend for session storage
- Agent feedback tracking
- Performance metrics database

### Phase 3: Advanced Orchestration
- Task dependency graphs
- Dynamic agent pool management
- Load balancing and scaling

### Phase 4: Self-Improvement (Ouroboros Loop)
- Agents analyzing their own work
- Harness improvement suggestions
- Automated prompt optimization

### Phase 5: Distributed Execution
- Remote agent execution
- Multi-machine coordination
- Result streaming and aggregation
