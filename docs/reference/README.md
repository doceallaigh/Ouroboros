# 📚 Reference Documentation

**Audience**: Anyone needing technical specifications, detailed specifications, or troubleshooting information

**Purpose**: Provide exhaustive technical reference materials for implementation details and problem-solving

---

## 📄 Documents in This Category

### Callback Mechanism
Agent callback system enabling inter-agent communication.
- **Read if**: You need to understand how agents communicate back to their task assigners
- **Contains**: Architecture, usage examples, event logging, and future enhancements
- **Time**: 10-15 minutes

### Duplicate Response Fix
Fix for duplicate manager file creation issue.
- **Read if**: You're investigating historical bug fixes or duplicate agent issues
- **Contains**: Root cause analysis, solution implementation, and verification
- **Time**: 5 minutes

### Network Mocking
Network test infrastructure and mocking implementation.
- **Read if**: You're writing tests or understanding test isolation
- **Contains**: Mock implementation, test utilities, and usage patterns
- **Time**: 10 minutes

### API Documentation
Function signatures, parameters, return values, exceptions, and examples.
- **Read if**: You need precise technical specifications for a specific function/method
- **Contains**: Complete API reference for all public functions
- **Time**: Variable, used as reference as needed

### Configuration Reference
All configurable parameters, their meaning, valid values, and examples.
- **Read if**: You need to configure the system or understand configuration options
- **Contains**: All config parameters with descriptions and examples
- **Time**: Reference as needed for specific settings

### Troubleshooting
Common issues, error codes, error messages, and solutions.
- **Read if**: You encounter an error or unexpected behavior
- **Contains**: Error catalog with causes and solutions
- **Time**: 5-10 minutes per issue

### Implementation Details
Low-level technical specifications and internal design patterns.
- **Read if**: You need to understand internal implementation
- **Contains**: Data structures, algorithms, internal patterns
- **Time**: Reference as needed for specific components

---

## 🎯 Quick Start

**Understanding agent communication?** Check: [`CALLBACK_MECHANISM.md`](CALLBACK_MECHANISM.md)

**Got an error message?** Check: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

**Need exact function signatures?** See: [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)

**Configuring the system?** Read: [`CONFIGURATION_REFERENCE.md`](CONFIGURATION_REFERENCE.md)

**Understanding internals?** Review: [`IMPLEMENTATION_DETAILS.md`](IMPLEMENTATION_DETAILS.md)

**Writing tests?** See: [`NETWORK_MOCKING_COMPLETE.md`](NETWORK_MOCKING_COMPLETE.md)

---

## 🔍 Exception Reference

### Communication Exceptions
- `CommunicationError` - Base exception for all communication issues
- `APIError` - API communication failed
- `ValidationError` - Message validation failed

### Filesystem Exceptions
- `FileSystemError` - Filesystem operation failed
- `SessionError` - Session management issue

### Tool Exceptions
- `ToolError` - Tool operation failed
- `PathError` - Invalid or unsafe path
- `FileSizeError` - File exceeds size limit

### Configuration Exceptions
- `ConfigError` - Configuration invalid or missing

### Organization Exceptions
- `OrganizationError` - Agent coordination failed

---

## 🛠️ Common Tasks (Quick Reference)

### Reading File Contents
```python
tools.read_file("path/to/file.txt")
# Returns: file contents as string
```

### Writing to File
```python
tools.write_file("path/to/file.txt", "content")
# Returns: dict with success status and metadata
```

### Searching Files
```python
tools.search_files("*.py", "src/")
# Returns: dict with list of matching files
```

### Getting File Info
```python
tools.get_file_info("path/to/file.txt")
# Returns: dict with size, type, modified time, line count, etc.
```

For complete reference, see [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)

---

## 🔗 Related Documentation

- **For Project Managers**: See [`docs/human/`](../human/)
- **For AI Agents**: See [`docs/agents/`](../agents/)
- **For Developers**: See [`docs/development/`](../development/)

---

## 📊 System Specifications

### Performance Characteristics
- **Message processing**: <100ms latency in live mode
- **File operations**: Limited by disk I/O, typically <1s
- **Retry attempts**: Up to 3 retries with exponential backoff
- **Timeout**: Configurable per agent (default 120s)

### Constraints
- **Max file size**: 10MB for read operations
- **Max agents**: Limited by ThreadPoolExecutor (default 5)
- **Session storage**: JSONL-based, unlimited (disk space dependent)

### Supported Modes
- **Live Mode**: Real-time agent-LLM communication
- **Replay Mode**: Read-only replay from stored sessions

---

**Last Updated**: February 8, 2026
