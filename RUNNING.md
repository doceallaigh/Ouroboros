# Running the Ouroboros Agent Harness

This document explains how to run the Ouroboros multi-agent coordination system.

## Prerequisites

Ensure you have the following files in the `src/` directory:
- `main.py` - Main coordinator module
- `comms.py` - Communication module
- `filesystem.py` - Filesystem storage module
- `config.py` - Configuration utilities
- `roles.json` - Agent role configurations

## Running from the `src` Directory

Run the coordinator in **replay mode** (uses recorded agent responses):
```bash
cd src
python main.py --replay
```

Or equivalently:
```bash
cd src
python main.py run --replay
```

Run the coordinator in **live mode** (connects to real APIs):
```bash
cd src
python main.py
```

**Note:** Live mode requires actual API endpoints configured in `roles.json`. The default configuration attempts to connect to `https://localhost:12345/v1/chat/completions`, which will fail unless an API server is running.

## Running from the Parent Directory

Run from the repository root (one level up from `src`):
```bash
python .\src\main.py run --replay
```

Or in live mode:
```bash
python .\src\main.py
```

## Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `run` | Execute the coordinator (optional, runs by default) |
| `--replay` | Run in replay mode using recorded responses from previous sessions |

## Example Outputs

### Successful Replay Mode Execution

```
INFO - Using roles.json from: D:\GitHub\Ouroboros\src\roles.json
INFO - Using shared directory: D:\GitHub\Ouroboros\shared_repo
INFO - Initialized coordinator with 2 agent roles
INFO - Operating in REPLAY mode
INFO - Processing request: Build a collaborative task management app with real-time sync
INFO - Initialized agent: Project Manager (role: manager)
INFO - Agent Project Manager completed task
INFO - Initialized agent: Code Developer (role: developer)
...
INFO - Request processing complete with 5 results
INFO - Execution Results:
{
  "role": "developer",
  "task": "Set up the project structure...",
  "status": "completed",
  "output": "I've successfully implemented..."
}
```

### Exit Codes

- **0**: Successful execution
- **1**: Fatal error (missing files, initialization failed, etc.)
- **Interrupt**: User pressed Ctrl+C

## Configuration

Agent roles are defined in `roles.json`:

```json
{
  "manager": {
    "name": "Project Manager",
    "role": "manager",
    "system_prompt": "...",
    "model": "deepseek/deepseek-r1-0528-qwen3-8b",
    "endpoint": "https://localhost:12345/v1/chat/completions",
    "temperature": 0.7,
    "max_tokens": 2000
  },
  "developer": {
    "name": "Code Developer",
    "role": "developer",
    "system_prompt": "...",
    "model": "qwen/qwen3-coder-30b",
    "endpoint": "https://localhost:12345/v1/chat/completions",
    "temperature": 0.5,
    "max_tokens": -1
  }
}
```

## Replay Data

Replay data is stored in `shared_repo/` with timestamped session directories. Each agent's recorded responses are stored as JSON files:

```
shared_repo/
├── 20260207_213901486/
│   ├── Project Manager.txt      # Manager agent responses
│   └── Code Developer.txt        # Developer agent responses
```

When running in replay mode, responses are loaded from the latest session directory.

## Troubleshooting

### FileNotFoundError: roles.json not found
**Solution:** Ensure `roles.json` exists in the `src/` directory.

### SSL: WRONG_VERSION_NUMBER error (Live Mode)
**Solution:** This occurs when trying to connect to a non-HTTPS endpoint or when the API server is not running. Use `--replay` mode for testing without a live API server.

### No recorded output found for agent
**Solution:** Agent responses are stored during execution. The first execution (in live mode) generates replay data for subsequent replay-mode runs.

## Testing with Unit Tests

Run all unit tests:
```bash
cd src
python -m unittest discover -p "test_*.py" -v
```

Run tests for specific module:
```bash
python -m unittest test_main.py -v
python -m unittest test_comms.py -v
python -m unittest test_filesystem.py -v
python -m unittest test_config.py -v
```

## Architecture

The Ouroboros system consists of:

1. **CentralCoordinator** - Main orchestrator that decomposes requests and manages agent execution
2. **Agent** - Individual agents assigned to specific roles (manager, developer, etc.)
3. **Channels** - Communication abstractions (APIChannel for live requests, ReplayChannel for replay mode)
4. **FileSystem** - Stores and retrieves agent responses for replay capability

See `docs/` for comprehensive architecture documentation.
