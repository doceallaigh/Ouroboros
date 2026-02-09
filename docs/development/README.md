# 🛠️ Development Documentation

**Audience**: Developers building, extending, and maintaining the Ouroboros system

**Purpose**: Provide technical details about system architecture, design decisions, and modification procedures

---

## 📄 Documents in This Category

### Architecture Guide
System design, component overview, data flow, and high-level structure.
- **Read if**: You need to understand how the system works internally
- **Contains**: Component descriptions, interaction patterns, module responsibilities
- **Time**: 15-20 minutes

### Refactoring Changes
Recent refactoring work, patterns applied, and lessons learned.
- **Read if**: You want to understand recent changes and patterns to follow
- **Contains**: Specific refactoring details, rationale, code patterns
- **Time**: 10-15 minutes

### Verification Checklist
Testing and validation procedures for changes and new features.
- **Read if**: You are submitting changes and need to verify correctness
- **Contains**: Test procedures, validation steps, quality criteria
- **Time**: 5-10 minutes per change

### Change Log
Detailed history of modifications, improvements, and fixes.
- **Read if**: You need to understand what has changed and when
- **Contains**: Chronological record of all modifications with details
- **Time**: Variable depending on scope of interest

---

## 🎯 Quick Start

**Starting a new feature?** Read: [`ARCHITECTURE.md`](ARCHITECTURE.md) - Design section

**Making modifications?** Review: [`REFACTORING_CHANGES.md`](REFACTORING_CHANGES.md) - Patterns section

**About to commit changes?** Use: [`VERIFICATION_CHECKLIST.md`](VERIFICATION_CHECKLIST.md)

**Understanding history?** Check: [`CHANGE_LOG.md`](CHANGE_LOG.md)

---

## 🏗️ System Architecture Overview

The Ouroboros system consists of these key components:

### Core Modules

**comms.py** - Communication layer
- Handles agent-LLM communication
- Manages request/response formatting
- Supports live and replay modes
- Exception: `CommunicationError` hierarchy

**filesystem.py** - Session and data management
- Stores session outputs and conversation history
- Event sourcing via JSONL logs
- Two modes: write (live) and read-only (replay)
- Exception: `FileSystemError`

**agent_tools.py** - Agent capability layer
- Provides 10 filesystem access methods to agents
- Security validation (path checking, file size limits)
- Comprehensive error handling
- Exceptions: `PathError`, `FileSizeError`, `ToolError`

**config.py** - Configuration management
- Loads and validates agent configurations
- Provides typed access to nested config values
- Exception: `ConfigError`

**main.py** - Orchestration layer
- Multi-agent coordination and task execution
- Request decomposition and result aggregation
- Retry logic with exponential backoff
- Exception: `OrganizationError`

### Data Flow

```
User Request
    ↓
CentralCoordinator.execute_request()
    ↓
[Request decomposition by manager agent]
    ↓
[Parallel task execution by worker agents]
    ↓
[Tool invocations via agent_tools.py]
    ↓
[Result aggregation]
    ↓
FileSystem.write_data() + Event logging
    ↓
Agent Response
```

---

## 🔧 Development Workflow

### 1. Understanding Existing Code

Start with [`ARCHITECTURE.md`](ARCHITECTURE.md):
- Module responsibilities
- Component interactions
- Data structures
- Exception hierarchies

### 2. Planning Changes

Check [`REFACTORING_CHANGES.md`](REFACTORING_CHANGES.md):
- Approved patterns
- Design decisions
- Code style guidelines
- Testing requirements

### 3. Implementation

Follow module documentation:
- Use existing patterns
- Maintain backward compatibility
- Add comprehensive error handling
- Document your code

### 4. Verification

Use [`VERIFICATION_CHECKLIST.md`](VERIFICATION_CHECKLIST.md):
- Run test suite
- Validate against acceptance criteria
- Check for regressions
- Update documentation

### 5. Integration

Record your changes:
- Update [`CHANGE_LOG.md`](CHANGE_LOG.md)
- Add migration notes if needed
- Update related documentation

---

## 🧪 Testing Requirements

All changes must include:

1. **Unit Tests** - Test individual functions/methods
2. **Integration Tests** - Test component interactions
3. **Regression Tests** - Ensure existing functionality still works
4. **Documentation Tests** - Verify examples in docs work as written

**Test Command**:
```bash
cd src/
python -m unittest discover -v
```

All tests must pass before merging.

---

## 📋 Quality Standards

- **Code Coverage**: Aim for >80% test coverage
- **Type Hints**: Use type annotations where practical
- **Error Handling**: All exceptions should be caught and logged
- **Documentation**: Code should have docstrings and comments where needed
- **Backward Compatibility**: Don't break existing APIs

---

## 🔗 Related Documentation

- **For Project Managers**: See [`docs/human/`](../human/)
- **For AI Agents**: See [`docs/agents/`](../agents/)
- **Technical Specifications**: See [`docs/reference/`](../reference/)

---

## 📚 Key Files to Know

### Source Code
- `src/main.py` - Main orchestration (687 lines)
- `src/comms.py` - Communication layer (500+ lines)
- `src/filesystem.py` - Data management (400+ lines)
- `src/agent_tools.py` - Agent tools (558+ lines)
- `src/config.py` - Configuration (100+ lines)

### Tests
- `src/test_main.py` - Coordinator tests
- `src/test_comms.py` - Communication tests
- `src/test_filesystem.py` - Filesystem tests
- `src/test_agent_tools.py` - Tools tests (30 tests)
- `src/test_config.py` - Configuration tests

### Configuration
- `src/roles.json` - Agent role definitions and prompts

---

**Last Updated**: February 8, 2026
