# Developer Agent Tools Guide

## Overview

Developer agents have access to a suite of filesystem tools for safe file and directory operations. All tools operate within a sandboxed working directory to prevent escape attempts.

## Available Tools

### File Operations

#### `read_file(path: str) -> str`
Read the complete contents of a file.

**Example:**
```python
content = read_file("src/main.py")
# Returns file content as string
```

#### `write_file(path: str, content: str) -> dict`
Create or overwrite a file with content. Creates parent directories as needed.

**Example:**
```python
result = write_file("config.json", '{"setting": "value"}')
# Returns: {"path": "config.json", "size": 27, "created": True, "encoding": "utf-8"}
```

#### `append_file(path: str, content: str) -> dict`
Append content to the end of a file. Creates the file if it doesn't exist.

**Example:**
```python
result = append_file("log.txt", "New log entry\n")
# Returns: {"path": "log.txt", "size": 15, "lines_added": 1}
```

#### `edit_file(path: str, old_text: str, new_text: str) -> dict`
Replace all occurrences of old_text with new_text in a file.

**Example:**
```python
result = edit_file("config.py", "DEBUG = False", "DEBUG = True")
# Returns: {"path": "config.py", "replacements": 1, "success": True}
```

### Directory Operations

#### `list_directory(path: str) -> dict`
List the contents of a directory (non-recursive).

**Example:**
```python
result = list_directory(".")
# Returns: {"total": 5, "directories": ["src", "tests"], "files": ["README.md", "config.json"]}
```

#### `list_all_files(path: str, extensions: list = None) -> dict`
Recursively list all files in a directory, optionally filtering by extension.

**Example:**
```python
# List all Python files
result = list_all_files(".", extensions=[".py"])
# Returns: {"path": ".", "extensions_filter": [".py"], "files": [...], "total": 42}
```

### Search & Information

#### `search_files(pattern: str, path: str = ".") -> dict`
Search for files matching a glob pattern.

**Example:**
```python
result = search_files("**/*.py", ".")
# Returns: {"pattern": "**/*.py", "matches": [...], "total_matches": 42, "truncated": False}
```

#### `get_file_info(path: str) -> dict`
Get metadata about a file or directory.

**Example:**
```python
info = get_file_info("main.py")
# Returns: {"is_file": True, "is_dir": False, "size": 1024, "lines": 42, "modified": "2026-02-08T..."}
```

### File Deletion

#### `delete_file(path: str) -> dict`
Delete a file from the filesystem.

**Example:**
```python
result = delete_file("temp.txt")
# Returns: {"deleted": True}
```

## Security Features

All paths are validated to prevent directory traversal attacks:
- Absolute paths outside the working directory are blocked
- Parent directory references (`../`) are blocked
- All paths must resolve within the working directory

**Invalid operations (will raise `PathError`):**
```python
read_file("/etc/passwd")  # Absolute path outside working dir
read_file("../../secrets.txt")  # Parent directory traversal
```

**Valid operations:**
```python
read_file("config.json")  # Relative path
read_file("./config.json")  # Explicit relative path
read_file("subdir/file.txt")  # Nested relative path
```

## Error Handling

All tools can raise three types of errors:

- **`ToolError`**: Generic tool operation failure
- **`PathError`**: Invalid path or directory traversal attempt
- **`FileSizeError`**: File exceeds 10MB limit

**Example error handling:**
```python
try:
    content = read_file("data.txt")
except PathError as e:
    # Handle invalid path
    pass
except FileSizeError as e:
    # Handle file too large
    pass
except ToolError as e:
    # Handle generic tool error
    pass
```

## Common Patterns

### Safe File Reading with Fallback
```python
try:
    config = read_file("config.json")
except ToolError:
    config = '{}'  # Use default if file doesn't exist
```

### Bulk File Replacement
```python
# Find and replace across all Python files
files = search_files("**/*.py")
for file_path in files["matches"]:
    content = read_file(file_path)
    updated = content.replace("old_pattern", "new_pattern")
    write_file(file_path, updated)
```

### File Processing Pipeline
```python
# 1. Read
data = read_file("input.txt")

# 2. Process
processed = process_data(data)

# 3. Write result
write_file("output.txt", processed)

# 4. Get confirmation
info = get_file_info("output.txt")
print(f"Wrote {info['size']} bytes")
```

## Tips

1. **Always validate paths** - Use `get_file_info()` first if unsure
2. **Use glob patterns** - `search_files("**/*.py")` for recursive search
3. **Check file size first** - Use `get_file_info()` before reading large files
4. **Use append for logs** - More efficient than read-modify-write for log files
5. **Batch operations** - Search for files once, then process in a loop

## Examples

### Initialize a Python Project
```python
# Create project structure
write_file("src/__init__.py", "")
write_file("tests/__init__.py", "")
write_file("README.md", "# My Project\n")
write_file("setup.py", "from setuptools import setup\nsetup(name='myproject')\n")
```

### Parse and Update Configuration
```python
import json

# Read config
config_text = read_file("config.json")
config = json.loads(config_text)

# Modify
config["debug"] = True
config["version"] = "2.0"

# Write back
write_file("config.json", json.dumps(config, indent=2))
```

### Find and Fix Issues
```python
# Find deprecated function calls
matches = search_files("**/*.py")
for file_path in matches["matches"]:
    edit_file(file_path, "deprecated_func()", "new_func()")
```
