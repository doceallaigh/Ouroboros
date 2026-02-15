"""
Tool definitions in OpenAI JSON Schema format for use with structured tool calling.

This module provides tool definitions that match the OpenAI API specification
for structured tool calling, allowing LLMs to return tool_calls instead of
relying on text parsing.
"""

# Tool definitions in OpenAI JSON Schema format
TOOL_DEFINITIONS = {
    "assign_task": {
        "type": "function",
        "function": {
            "name": "assign_task",
            "description": "Assign a single task to a specific role",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "The role to assign the task to (e.g., 'developer', 'auditor')"
                    },
                    "task": {
                        "type": "string",
                        "description": "Detailed task description including context and dependencies"
                    },
                    "sequence": {
                        "type": "integer",
                        "description": "Execution order: 0 for first, 1 for second, etc. Same sequence runs in parallel."
                    }
                },
                "required": ["role", "task", "sequence"]
            }
        }
    },
    "assign_tasks": {
        "type": "function",
        "function": {
            "name": "assign_tasks",
            "description": "Assign multiple tasks at once for batch processing",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignments": {
                        "type": "array",
                        "description": "List of task assignments",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {
                                    "type": "string",
                                    "description": "The role to assign the task to"
                                },
                                "task": {
                                    "type": "string",
                                    "description": "Task description"
                                },
                                "sequence": {
                                    "type": "integer",
                                    "description": "Execution order"
                                }
                            },
                            "required": ["role", "task", "sequence"]
                        }
                    }
                },
                "required": ["assignments"]
            }
        }
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating or overwriting the file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to working directory"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Large files are paginated; use the page parameter to read subsequent pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to working directory"
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number to read (1-based, default 1). Each page contains 500 lines."
                    }
                },
                "required": ["path"]
            }
        }
    },
    "append_file": {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append content to the end of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to working directory"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to append"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    "edit_file": {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file with a diff operation",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to working directory"
                    },
                    "diff": {
                        "type": "string",
                        "description": "Diff showing changes to make"
                    }
                },
                "required": ["path", "diff"]
            }
        }
    },
    "list_directory": {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List contents of a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to working directory"
                    }
                },
                "required": ["path"]
            }
        }
    },
    "list_all_files": {
        "type": "function",
        "function": {
            "name": "list_all_files",
            "description": "Recursively list all files in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to working directory"
                    },
                    "extensions": {
                        "type": "array",
                        "description": "Optional list of file extensions to filter by",
                        "items": {"type": "string"}
                    }
                },
                "required": ["path"]
            }
        }
    },
    "search_files": {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files matching a pattern",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "File pattern to search for (e.g., '*.py', 'test_*.py')"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in, defaults to current directory"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    "delete_file": {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to delete relative to working directory"
                    }
                },
                "required": ["path"]
            }
        }
    },
    "get_file_info": {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Get information about a file (size, modified time, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to working directory"
                    }
                },
                "required": ["path"]
            }
        }
    },
    "clone_repo": {
        "type": "function",
        "function": {
            "name": "clone_repo",
            "description": "Clone a git repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "Repository URL to clone"
                    },
                    "dest_dir": {
                        "type": "string",
                        "description": "Destination directory for the clone"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch to check out"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Shallow clone depth"
                    }
                },
                "required": ["repo_url"]
            }
        }
    },
    "checkout_branch": {
        "type": "function",
        "function": {
            "name": "checkout_branch",
            "description": "Checkout a git branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_dir": {
                        "type": "string",
                        "description": "Repository directory"
                    },
                    "branch_name": {
                        "type": "string",
                        "description": "Branch name to checkout"
                    },
                    "create": {
                        "type": "boolean",
                        "description": "Whether to create the branch if it doesn't exist"
                    }
                },
                "required": ["repo_dir", "branch_name"]
            }
        }
    },
    "run_python": {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)"
                    },
                    "log_path": {
                        "type": "string",
                        "description": "Optional path to log output"
                    }
                },
                "required": ["code"]
            }
        }
    },
    "raise_callback": {
        "type": "function",
        "function": {
            "name": "raise_callback",
            "description": "Raise a callback for blocker issues, clarification requests, or queries",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The callback message"
                    },
                    "callback_type": {
                        "type": "string",
                        "enum": ["blocker", "clarification", "query"],
                        "description": "Type of callback: blocker (blocking issue), clarification (need info), or query (general question)"
                    }
                },
                "required": ["message", "callback_type"]
            }
        }
    },
    "audit_files": {
        "type": "function",
        "function": {
            "name": "audit_files",
            "description": "Audit files for quality, security, and correctness",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "description": "List of file paths to audit",
                        "items": {"type": "string"}
                    },
                    "description": {
                        "type": "string",
                        "description": "What to audit for (e.g., 'code quality', 'security issues')"
                    },
                    "focus_areas": {
                        "type": "array",
                        "description": "Specific areas to focus the audit on",
                        "items": {"type": "string"}
                    }
                },
                "required": ["file_paths", "description"]
            }
        }
    },
    "search_package": {
        "type": "function",
        "function": {
            "name": "search_package",
            "description": "Search for and get information about a package",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Package name to search for"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., 'python', 'javascript')"
                    }
                },
                "required": ["name"]
            }
        }
    },
    "install_package": {
        "type": "function",
        "function": {
            "name": "install_package",
            "description": "Install a package",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Package name to install"
                    },
                    "version": {
                        "type": "string",
                        "description": "Specific version to install"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., 'python')"
                    }
                },
                "required": ["name"]
            }
        }
    },
    "check_package_installed": {
        "type": "function",
        "function": {
            "name": "check_package_installed",
            "description": "Check if a package is installed",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Package name to check"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language"
                    }
                },
                "required": ["name"]
            }
        }
    },
    "list_installed_packages": {
        "type": "function",
        "function": {
            "name": "list_installed_packages",
            "description": "List all installed packages",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., 'python')"
                    }
                }
            }
        }
    }
}


def get_tools_for_role(allowed_tools: list) -> list:
    """
    Get tool definitions for a specific role.
    
    Args:
        allowed_tools: List of tool names allowed for this role
        
    Returns:
        List of tool definitions in OpenAI JSON schema format
    """
    tools = []
    for tool_name in allowed_tools:
        if tool_name in TOOL_DEFINITIONS:
            tools.append(TOOL_DEFINITIONS[tool_name])
    return tools
