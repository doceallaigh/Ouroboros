# 🤖 AI Agent Documentation

**Audience**: AI agents executing tasks within the Ouroboros system

**Purpose**: Provide clear, precise specifications and examples for agents to understand their capabilities and how to use them

---

## 📄 Documents in This Category

### Agent Tools Guide
Complete reference for all available methods, signatures, parameters, return values, and examples.
- **Read if**: You are an agent needing to understand available capabilities
- **Contains**: All 10 tool methods with detailed signatures, examples, error types, and security constraints
- **Time**: 10-15 minutes for overview, reference as needed during execution

### Tool Injection Summary
How tools are made available to agents at runtime through dynamic injection and static references.
- **Read if**: You want to understand how tools become available in your system prompt
- **Contains**: Technical details about tool discovery, initialization, and availability
- **Time**: 5 minutes

### Best Practices
Recommended patterns, error handling approaches, and proven strategies for agent task execution.
- **Read if**: You want to execute tasks effectively and handle edge cases gracefully
- **Contains**: Common patterns, error recovery, efficiency tips, security considerations
- **Time**: 10 minutes for overview, reference as needed

---

## 🎯 Quick Start

**Just activated?** Read: [`AGENT_TOOLS_GUIDE.md`](AGENT_TOOLS_GUIDE.md) - Methods section

**Need to understand how tools work?** Read: [`TOOL_INJECTION_SUMMARY.md`](TOOL_INJECTION_SUMMARY.md)

**About to execute a task?** Review: [`BEST_PRACTICES.md`](BEST_PRACTICES.md)

**Need a specific method's details?** Check: [`AGENT_TOOLS_GUIDE.md`](AGENT_TOOLS_GUIDE.md) - Reference section

---

## 📚 Available Tools Summary

Your available methods are organized in these categories:

### File Operations
- `read_file(path)` - Read and return file contents
- `write_file(path, content)` - Create or overwrite a file
- `append_file(path, content)` - Add to end of file
- `edit_file(path, old_text, new_text)` - Replace text within file

### File Information
- `get_file_info(path)` - Get file metadata (size, type, modified time, line count)

### Directory Operations
- `list_directory(path)` - List immediate directory contents
- `list_all_files(path, extensions)` - Recursively list all files, optionally filtered by extension

### Search
- `search_files(pattern, path)` - Find files matching glob pattern (supports `**` for recursion)

### Deletion
- `delete_file(path)` - Delete a file

---

## ⚠️ Important Constraints

All paths must be **relative to your working directory**:
- ✅ Allowed: `config/settings.json`, `src/main.py`, `data/output.txt`
- ❌ Blocked: `/etc/passwd`, `C:\Windows\System32\config`

File size limit: **10MB maximum** for read operations

**Security validation**: Absolute paths and parent directory traversal (`../`) are blocked

---

## 🚨 Exception Types

Your tools can raise three exception types:

1. **PathError** - Invalid path, traversal attempt, or permission issue
2. **FileSizeError** - File exceeds 10MB limit
3. **ToolError** - General operation failure (bad parameters, disk I/O, etc.)

Always wrap tool calls in try/except blocks to handle these gracefully.

---

## 🔗 Related Documentation

- **How humans operate the system**: See [`docs/human/`](../human/)
- **How developers built this**: See [`docs/development/`](../development/)
- **Technical specifications**: See [`docs/reference/`](../reference/)

---

## 📝 Format Notes

All methods return **structured data** (typically dicts) with:
- `success` (bool) - Whether operation succeeded
- `path` (str) - Path operated on
- `message` (str) - Human-readable result description
- Additional fields based on operation type

All methods accept **relative paths** and validate them for security.

---

**Last Updated**: February 8, 2026
