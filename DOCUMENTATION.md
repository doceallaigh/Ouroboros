# Ouroboros Documentation Index

Welcome to Ouroboros! This directory contains comprehensive documentation for the multi-agent collaboration framework.

## 📚 Documentation Files

### Getting Started
1. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** ⭐ *Start here!*
   - Quick module reference with code examples
   - Common usage patterns
   - Configuration examples
   - Debugging checklist
   - Perfect for quick lookups while coding

### Understanding the System
2. **[ARCHITECTURE.md](ARCHITECTURE.md)**
   - System architecture and design
   - Component interactions
   - Data flow diagrams
   - State management
   - Extensibility points
   - Performance considerations

### Best Practices
3. **[BEST_PRACTICES.md](BEST_PRACTICES.md)**
   - Communication patterns
   - Filesystem patterns
   - Coordination patterns
   - Error handling strategies
   - Configuration best practices
   - Troubleshooting guide
   - Advanced patterns

### Refactoring Details
4. **[REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)**
   - Overview of refactoring goals
   - Module responsibilities
   - Cross-cutting improvements
   - Replay mode explanation
   - Future enhancements

5. **[REFACTORING_CHANGES.md](REFACTORING_CHANGES.md)**
   - Detailed changes by module
   - Before/after comparisons
   - Migration guide for existing code
   - Breaking changes documented
   - Quality improvements listed

6. **[VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)**
   - QA verification results
   - Testing readiness
   - Security verification
   - Performance benchmarks
   - Deployment readiness checklist

---

## 🎯 Quick Navigation

### For First-Time Users
1. Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md#typical-usage-patterns)
2. Run the basic example in main.py
3. Check [roles.json](src/roles.json) for configuration structure
4. Review error handling in [BEST_PRACTICES.md](BEST_PRACTICES.md#error-handling)

### For Understanding Architecture
1. Start with [ARCHITECTURE.md](ARCHITECTURE.md#system-overview)
2. Review component interaction diagrams
3. Understand data flow patterns
4. Study extensibility points

### For Advanced Users
1. Review [BEST_PRACTICES.md](BEST_PRACTICES.md#advanced-patterns)
2. Study custom implementations (channels, agents, coordinators)
3. Plan extensions based on [ARCHITECTURE.md](ARCHITECTURE.md#extensibility-points)
4. Implement specialized features

### For Debugging Issues
1. Check [QUICK_REFERENCE.md](QUICK_REFERENCE.md#common-debugging-steps)
2. Review [BEST_PRACTICES.md](BEST_PRACTICES.md#troubleshooting-checklist)
3. Enable logging and review [ARCHITECTURE.md](ARCHITECTURE.md#monitoring-and-observability)
4. Check [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md#edge-cases-handled)

---

## 📋 Module Overview

```
Ouroboros Project Structure
├── src/
│   ├── comms.py           # Communication with agents + sanitization + error handling
│   ├── filesystem.py      # Storage and retrieval of data
│   ├── main.py            # Coordination and orchestration
│   ├── config.py          # Configuration utilities
│   ├── roles.json         # Agent configurations
│   ├── config.json        # API keys and settings
│   └── __pycache__/
├── shared_repo/           # Session storage (auto-created)
│   └── YYYYMMDD_HHMMSSXXX/ # Individual session directories
├── Documentation files (this directory)
└── (other project files)
```

### Module Responsibilities

| Module | Primary Responsibility | Key Classes | Key Functions |
|--------|----------------------|-------------|----------------|
| **comms.py** | Communication & sanitization | Channel, APIChannel, ReplayChannel | sanitize_input, sanitize_output, extract_content |
| **filesystem.py** | Storage & retrieval | FileSystem, ReadOnlyFileSystem | write_data, get_recorded_output |
| **main.py** | Coordination | Agent, CentralCoordinator | assign_and_execute, decompose_request |
| **config.py** | Configuration | - | load_config, get_config_value |

---

## 🔄 Common Workflows

### Workflow 1: Running Your First Request
```python
from main import CentralCoordinator
from filesystem import FileSystem

# 1. Initialize filesystem
fs = FileSystem(shared_dir="./shared_repo")

# 2. Create coordinator
coordinator = CentralCoordinator("roles.json", filesystem=fs)

# 3. Execute request
results = coordinator.assign_and_execute("Your request here")

# 4. Review results
for result in results:
    print(result)
```

### Workflow 2: Replaying a Previous Run
```bash
# Option 1: Via command line
cd src/
python main.py --replay

# Option 2: Via Python
from main import CentralCoordinator
from filesystem import FileSystem

fs = FileSystem(shared_dir="./shared_repo", replay_mode=True)
coordinator = CentralCoordinator("roles.json", filesystem=fs, replay_mode=True)
results = coordinator.assign_and_execute("Same request as before")
```

### Workflow 3: Custom Agent Implementation
```python
from main import Agent

class MySpecialAgent(Agent):
    def execute_task(self, task):
        # Pre-process
        task["user_prompt"] = f"[CUSTOM] {task['user_prompt']}"
        
        # Execute
        result = super().execute_task(task)
        
        # Post-process
        return f"PROCESSED: {result}"
```

---

## ⚠️ Important Concepts

### Sessions
Each execution creates a timestamped session directory (e.g., `20260207_163220333/`).
- **Location**: `shared_repo/YYYYMMDD_HHMMSSXXX/`
- **Contains**: Agent outputs, structured data, conversation histories
- **Used for**: Replay mode, audit trail, debugging

### Roles
Unique identifiers for agent types. Defined in `roles.json`.
- **Examples**: `manager`, `developer`, `reviewer`, `architect`
- **Usage**: Agents assigned based on role
- **Important**: Must include at least one "manager" role for request decomposition

### Channels
Communication mechanisms for agents.
- **APIChannel**: Live communication with external APIs
- **ReplayChannel**: Retrieves previously recorded responses
- **Custom**: Implement Channel interface for specialized communication

### Replay Mode
Execute using previously recorded responses.
- **Use Cases**: Testing, debugging, CI/CD
- **Benefits**: Deterministic, fast, reproducible
- **Limitation**: Can't test new features without re-running

---

## 🛠️ Setting Up

### 1. Configuration
Edit `src/roles.json` with your agent definitions:
```json
{
  "agent_name": {
    "name": "Display Name",
    "role": "unique_role",
    "system_prompt": "Instructions for the agent",
    "model": "model/identifier",
    "endpoint": "http://api.endpoint/v1/...",
    "timeout": 120
  }
}
```

### 2. API Keys
Set up `src/config.json` with credentials:
```json
{
  "openai_api_key": "sk-..."
}
```

### 3. Run
```bash
cd src/
python main.py              # Run normally
python main.py --replay     # Run in replay mode
```

---

## 📖 Documentation Reading Guide

### 10-Minute Introduction
1. Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (5 min)
2. Review [ARCHITECTURE.md#system-overview](ARCHITECTURE.md#system-overview) (5 min)

### 30-Minute Deep Dive
1. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - 5 min
2. [ARCHITECTURE.md](ARCHITECTURE.md) - 15 min
3. [BEST_PRACTICES.md#communication-patterns](BEST_PRACTICES.md#communication-patterns) - 10 min

### 1-Hour Comprehensive Review
1. All quick reference sections - 15 min
2. [ARCHITECTURE.md](ARCHITECTURE.md) - 25 min
3. [BEST_PRACTICES.md](BEST_PRACTICES.md) - 15 min
4. [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - 5 min

### Complete Study
Read all documentation in this order:
1. [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [BEST_PRACTICES.md](BEST_PRACTICES.md)
4. [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)
5. [REFACTORING_CHANGES.md](REFACTORING_CHANGES.md)
6. [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)

---

## 🐛 Troubleshooting

| Issue | Quick Fix | Full Guide |
|-------|-----------|-----------|
| Agent not found | Check role name in roles.json | [QUICK_REFERENCE.md#debugging](QUICK_REFERENCE.md#debugging) |
| API timeout | Increase timeout value | [BEST_PRACTICES.md#timeout-management](BEST_PRACTICES.md#timeout-management) |
| Response parsing error | Check API response format | [comms.py#extract_content](src/comms.py) |
| Replay not working | Verify session directory exists | [BEST_PRACTICES.md#replay-mode-workflow](BEST_PRACTICES.md#replay-mode-workflow) |
| Out of memory | Reduce max_length | [BEST_PRACTICES.md#performance-optimization](BEST_PRACTICES.md#performance-optimization) |

For more issues, see:
- [QUICK_REFERENCE.md#common-debugging-steps](QUICK_REFERENCE.md#common-debugging-steps)
- [BEST_PRACTICES.md#common-issues-and-solutions](BEST_PRACTICES.md#common-issues-and-solutions)

---

## 📚 API Reference

### Quick Reference by Module
- **comms.py**: [QUICK_REFERENCE.md#comms-communication-layer](QUICK_REFERENCE.md#commspy---communication-layer)
- **filesystem.py**: [QUICK_REFERENCE.md#filesystempy---storage-layer](QUICK_REFERENCE.md#filesystempy---storage-layer)
- **main.py**: [QUICK_REFERENCE.md#mainpy---coordination-layer](QUICK_REFERENCE.md#mainpy---coordination-layer)
- **config.py**: [QUICK_REFERENCE.md#configpy---configuration](QUICK_REFERENCE.md#configpy---configuration)

### Detailed API Information
- All APIs documented in source code with docstrings
- Type hints throughout for IDE support
- Examples in [BEST_PRACTICES.md](BEST_PRACTICES.md)

---

## 🔐 Security Notes

1. **API Keys**: Keep in config.json, not in code
2. **Input Validation**: All message structures validated
3. **Output Sanitization**: All responses cleaned
4. **File Safety**: ReadOnlyFileSystem prevents accidental overwrites

See [BEST_PRACTICES.md](BEST_PRACTICES.md#security) for details.

---

## 🚀 Getting Help

### Finding Information
1. **Quick lookup**: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. **How-to guides**: [BEST_PRACTICES.md](BEST_PRACTICES.md)
3. **Understanding design**: [ARCHITECTURE.md](ARCHITECTURE.md)
4. **Troubleshooting**: [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)

### Code Examples
- [BEST_PRACTICES.md#typical-usage-patterns](BEST_PRACTICES.md#typical-usage-patterns)
- [QUICK_REFERENCE.md#typical-usage-patterns](QUICK_REFERENCE.md#typical-usage-patterns)
- Source code in `src/` with docstrings

### Common Tasks
| Task | Location |
|------|----------|
| Set up first run | [QUICK_REFERENCE.md#pattern-1-basic-execution](QUICK_REFERENCE.md#pattern-1-basic-execution) |
| Create custom agent | [BEST_PRACTICES.md#custom-agent-implementations](BEST_PRACTICES.md#custom-agent-implementations) |
| Debug issue | [BEST_PRACTICES.md#common-issues-and-solutions](BEST_PRACTICES.md#common-issues-and-solutions) |
| Configure API | [QUICK_REFERENCE.md#configuration-examples](QUICK_REFERENCE.md#configuration-examples) |
| Understand error | [QUICK_REFERENCE.md#exception-reference](QUICK_REFERENCE.md#exception-reference) |

---

## 📊 Documentation Statistics

| Document | Length | Topics |
|----------|--------|--------|
| QUICK_REFERENCE.md | ~400 lines | Module ref, patterns, debugging |
| ARCHITECTURE.md | ~600 lines | Design, data flow, extensibility |
| BEST_PRACTICES.md | ~500 lines | Patterns, tips, advanced usage |
| REFACTORING_SUMMARY.md | ~300 lines | Responsibilities, improvements |
| REFACTORING_CHANGES.md | ~400 lines | Detailed changes, migration |
| VERIFICATION_CHECKLIST.md | ~500 lines | QA, testing, deployment |
| **Total** | **~2,700 lines** | Comprehensive coverage |

---

## 📝 Document Maintenance

These documents are maintained alongside the codebase:
- **Updated during**: Code changes, new features, bug fixes
- **Sync method**: Keep docs and code in lockstep
- **Owner**: Development team
- **Review**: Part of PR process

---

## ⭐ Key Takeaways

1. **Ouroboros** is a multi-agent collaboration framework
2. **Modular design** keeps concerns separated
3. **Comprehensive error handling** ensures robustness
4. **Replay mode** enables deterministic testing
5. **Well-documented** for easy adoption and extension

---

## 🎓 Learning Path

### Level 1: User
- Read QUICK_REFERENCE
- Run basic example
- Configure own agents

### Level 2: Developer
- Understand ARCHITECTURE
- Read BEST_PRACTICES
- Create custom agents

### Level 3: Architect
- Study REFACTORING_CHANGES
- Review VERIFICATION_CHECKLIST
- Plan extensions and improvements

---

## 📞 Support Resources

In this order:
1. **QUICK_REFERENCE.md** - Fast answers
2. **Source code** - Detailed implementations
3. **BEST_PRACTICES.md** - Patterns and solutions
4. **ARCHITECTURE.md** - System design
5. **VERIFICATION_CHECKLIST.md** - Known issues and workarounds

---

**Last Updated**: February 2026
**Version**: 2.0 (Post-Refactoring)
**Status**: ✅ Production Ready
