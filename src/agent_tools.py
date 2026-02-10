"""
Agent tools module for file and directory operations.

Responsibilities:
- Provide agents with safe file system access
- Directory exploration and traversal
- File reading, writing, and editing
- File search and filtering
- Metadata retrieval
- Package management (search and install dependencies)

Security:
- All paths are validated to prevent directory traversal
- Operations are restricted to designated working directories
- File sizes are limited to prevent memory issues
- Package installations are validated and restricted
"""

import os
import logging
import subprocess
import json
import sys
import re
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from code_runner import CodeRunner, CodeRunError

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_SEARCH_RESULTS = 100
DEFAULT_WORKING_DIR = os.getcwd()
ALLOWED_PACKAGE_PREFIXES = []  # Empty = allow all (can be restricted)


class ToolError(Exception):
    """Base exception for tool-related errors."""
    pass


class PathError(ToolError):
    """Raised when path validation fails."""
    pass


class FileSizeError(ToolError):
    """Raised when file size exceeds limits."""
    pass


class PackageError(ToolError):
    """Raised when package operations fail."""
    pass


class GitError(ToolError):
    """Raised when git operations fail."""
    pass


class AgentTools:
    """
    Provides agents with safe file system tools.
    
    All operations are restricted to a designated working directory
    to prevent directory traversal attacks.
    """
    TOOL_METHODS = {
        "list_directory",
        "read_file",
        "write_file",
        "append_file",
        "edit_file",
        "search_files",
        "get_file_info",
        "delete_file",
        "list_all_files",
        "search_package",
        "install_package",
        "check_package_installed",
        "list_installed_packages",
        "clone_repo",
        "checkout_branch",
        "push_branch",
        "create_pull_request",
        "run_python",
        "run_tests",
        "confirm_task_complete",
        "audit_files",
    }
    
    def __init__(self, working_dir: str = DEFAULT_WORKING_DIR, max_file_size: int = DEFAULT_MAX_FILE_SIZE, allowed_tools: Optional[List[str]] = None):
        """
        Initialize agent tools.
        
        Args:
            working_dir: Root directory for all operations (default: current directory)
            max_file_size: Maximum file size in bytes for read operations
            allowed_tools: Optional list of tool names allowed for the role
            allowed_tools: Optional list of tool names allowed for the role
            
        Raises:
            ToolError: If working directory doesn't exist
        """
        if not os.path.isdir(working_dir):
            raise ToolError(f"Working directory not found: {working_dir}")
        
        self.working_dir = os.path.abspath(working_dir)
        self.max_file_size = max_file_size
        self.allowed_tools = set(allowed_tools) if allowed_tools is not None else None
        self.code_runner = CodeRunner()
        logger.info(f"Initialized AgentTools with working_dir: {self.working_dir}")

    def __getattribute__(self, name: str):
        tool_methods = object.__getattribute__(self, "TOOL_METHODS")
        if name in tool_methods:
            allowed_tools = object.__getattribute__(self, "allowed_tools")
            if allowed_tools is not None and name not in allowed_tools:
                def _blocked(*_args, **_kwargs):
                    raise ToolError(f"Tool not allowed for this role: {name}")
                return _blocked
        return object.__getattribute__(self, name)

    def __getattribute__(self, name: str):
        tool_methods = object.__getattribute__(self, "TOOL_METHODS")
        if name in tool_methods:
            allowed_tools = object.__getattribute__(self, "allowed_tools")
            if allowed_tools is not None and name not in allowed_tools:
                def _blocked(*_args, **_kwargs):
                    raise ToolError(f"Tool not allowed for this role: {name}")
                return _blocked
        return object.__getattribute__(self, name)
    
    def _validate_path(self, path: str) -> str:
        """
        Validate and normalize a path.
        
        Ensures the path is within the working directory to prevent
        directory traversal attacks.
        
        Args:
            path: Path to validate (relative or absolute)
            
        Returns:
            Absolute validated path
            
        Raises:
            PathError: If path escapes working directory
        """
        # If absolute path, use it; otherwise, treat as relative to working_dir
        if os.path.isabs(path):
            full_path = os.path.abspath(path)
        else:
            full_path = os.path.abspath(os.path.join(self.working_dir, path))
        
        # Ensure path is within working directory
        real_path = os.path.realpath(full_path)
        real_working = os.path.realpath(self.working_dir)
        
        if not real_path.startswith(real_working):
            raise PathError(f"Path escapes working directory: {path}")
        
        return real_path
    
    def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """
        List contents of a directory.
        
        Args:
            path: Directory path (relative to working_dir)
            
        Returns:
            Dictionary with directories, files, and total count
            
        Raises:
            PathError: If path is invalid
            ToolError: If directory doesn't exist
        """
        try:
            dir_path = self._validate_path(path)
            
            if not os.path.isdir(dir_path):
                raise ToolError(f"Not a directory: {path}")
            
            entries = os.listdir(dir_path)
            
            directories = []
            files = []
            
            for entry in entries:
                full_path = os.path.join(dir_path, entry)
                if os.path.isdir(full_path):
                    directories.append(entry)
                else:
                    files.append(entry)
            
            logger.debug(f"Listed directory: {path} ({len(directories)} dirs, {len(files)} files)")
            
            return {
                "path": path,
                "directories": sorted(directories),
                "files": sorted(files),
                "total": len(directories) + len(files),
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to list directory {path}: {e}")
    
    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """
        Read file contents.
        
        Args:
            path: File path (relative to working_dir)
            encoding: Text encoding (default: utf-8)
            
        Returns:
            File contents as string
            
        Raises:
            PathError: If path is invalid
            FileSizeError: If file exceeds max_file_size
            ToolError: If read fails
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                raise FileSizeError(
                    f"File too large: {file_size} bytes (limit: {self.max_file_size})"
                )
            
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            logger.debug(f"Read file: {path} ({file_size} bytes)")
            return content
        
        except (PathError, FileSizeError):
            raise
        except Exception as e:
            raise ToolError(f"Failed to read file {path}: {e}")
    
    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Write content to a file.
        
        Creates the file if it doesn't exist. Overwrites if it does.
        
        Args:
            path: File path (relative to working_dir)
            content: Content to write
            encoding: Text encoding (default: utf-8)
            
        Returns:
            Dictionary with path, size, and created flag
            
        Raises:
            PathError: If path is invalid
            ToolError: If write fails
        """
        try:
            file_path = self._validate_path(path)
            
            # Ensure parent directory exists
            parent_dir = os.path.dirname(file_path)
            os.makedirs(parent_dir, exist_ok=True)
            
            # Check if file already exists
            already_exists = os.path.exists(file_path)
            
            # Write file
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            
            file_size = os.path.getsize(file_path)
            
            logger.info(f"Wrote file: {path} ({file_size} bytes, created={not already_exists})")
            
            return {
                "path": path,
                "size": file_size,
                "created": not already_exists,
                "encoding": encoding,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to write file {path}: {e}")
    
    def append_file(self, path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Append content to a file.
        
        Creates the file if it doesn't exist.
        
        Args:
            path: File path (relative to working_dir)
            content: Content to append
            encoding: Text encoding (default: utf-8)
            
        Returns:
            Dictionary with path, size, and lines added
            
        Raises:
            PathError: If path is invalid
            ToolError: If append fails
        """
        try:
            file_path = self._validate_path(path)
            
            # Ensure parent directory exists
            parent_dir = os.path.dirname(file_path)
            os.makedirs(parent_dir, exist_ok=True)
            
            # Count lines being appended
            lines_added = content.count('\n')
            if content and not content.endswith('\n'):
                lines_added += 1
            
            # Append to file
            with open(file_path, 'a', encoding=encoding) as f:
                f.write(content)
            
            file_size = os.path.getsize(file_path)
            
            logger.info(f"Appended to file: {path} ({lines_added} lines, total size: {file_size})")
            
            return {
                "path": path,
                "size": file_size,
                "lines_added": lines_added,
                "encoding": encoding,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to append to file {path}: {e}")
    
    def edit_file(self, path: str, diff: str, encoding: str = "utf-8") -> Dict[str, Any]:
    def edit_file(self, path: str, diff: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Edit file by applying a unified diff.
        Edit file by applying a unified diff.
        
        Args:
            path: File path (relative to working_dir)
            diff: Unified diff string (single-file) to apply
            diff: Unified diff string (single-file) to apply
            encoding: Text encoding (default: utf-8)
            
        Returns:
            Dictionary with path, hunks applied, and result
            Dictionary with path, hunks applied, and result
            
        Raises:
            PathError: If path is invalid
            ToolError: If patch fails or does not match file contents
            ToolError: If patch fails or does not match file contents
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            # Read file
            with open(file_path, 'r', encoding=encoding) as f:
                original_lines = f.read().splitlines(keepends=True)
                original_lines = f.read().splitlines(keepends=True)
            
            new_lines, stats = self._apply_unified_diff(original_lines, diff)
            new_lines, stats = self._apply_unified_diff(original_lines, diff)
            
            if not stats["hunks"]:
            if not stats["hunks"]:
                return {
                    "path": path,
                    "hunks": 0,
                    "added": 0,
                    "removed": 0,
                    "hunks": 0,
                    "added": 0,
                    "removed": 0,
                    "success": False,
                    "message": "No hunks applied",
                    "message": "No hunks applied",
                }
            
            # Write back
            with open(file_path, 'w', encoding=encoding) as f:
                f.write("".join(new_lines))
                f.write("".join(new_lines))
            
            logger.info(
                f"Edited file: {path} (hunks={stats['hunks']}, added={stats['added']}, removed={stats['removed']})"
            )
            logger.info(
                f"Edited file: {path} (hunks={stats['hunks']}, added={stats['added']}, removed={stats['removed']})"
            )
            
            return {
                "path": path,
                "hunks": stats["hunks"],
                "added": stats["added"],
                "removed": stats["removed"],
                "hunks": stats["hunks"],
                "added": stats["added"],
                "removed": stats["removed"],
                "success": True,
            }
        
        except PathError:
            raise
        except ToolError:
            raise
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to edit file {path}: {e}")

    def _apply_unified_diff(self, original_lines: List[str], diff: str) -> tuple[List[str], Dict[str, int]]:
        """
        Apply a unified diff to a list of lines.
        
        Args:
            original_lines: Original file lines with newline characters
            diff: Unified diff string
            
        Returns:
            Tuple of (new_lines, stats)
            stats includes: hunks, added, removed
        """
        diff_lines = diff.splitlines()
        output_lines: List[str] = []
        orig_index = 0
        hunks = 0
        added = 0
        removed = 0
        
        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            
            if line.startswith("diff ") or line.startswith("---") or line.startswith("+++"):
                i += 1
                continue
            
            if line.startswith("@@"):
                match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if not match:
                    raise ToolError(f"Invalid diff hunk header: {line}")
                orig_start = int(match.group(1))
                
                # Append unchanged lines before the hunk
                while orig_index < orig_start - 1:
                    output_lines.append(original_lines[orig_index])
                    orig_index += 1
                
                i += 1
                while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                    hunk_line = diff_lines[i]
                    if hunk_line.startswith(" "):
                        expected = hunk_line[1:]
                        if orig_index >= len(original_lines) or original_lines[orig_index].rstrip("\n") != expected:
                            raise ToolError("Diff context does not match file contents")
                        output_lines.append(original_lines[orig_index])
                        orig_index += 1
                    elif hunk_line.startswith("-"):
                        expected = hunk_line[1:]
                        if orig_index >= len(original_lines) or original_lines[orig_index].rstrip("\n") != expected:
                            raise ToolError("Diff removal does not match file contents")
                        orig_index += 1
                        removed += 1
                    elif hunk_line.startswith("+"):
                        output_lines.append(hunk_line[1:] + "\n")
                        added += 1
                    elif hunk_line.startswith("\\"):
                        if output_lines:
                            output_lines[-1] = output_lines[-1].rstrip("\n")
                    else:
                        raise ToolError(f"Invalid diff line: {hunk_line}")
                    i += 1
                
                hunks += 1
                continue
            
            i += 1
        
        # Append remaining original lines
        output_lines.extend(original_lines[orig_index:])
        
        return output_lines, {"hunks": hunks, "added": added, "removed": removed}
    
    def search_files(self, pattern: str, path: str = ".") -> Dict[str, Any]:
        """
        Search for files matching a pattern.
        
        Supports glob patterns (*, ?, [seq], [!seq]).
        
        Args:
            pattern: Glob pattern to match
            path: Directory to search in (default: working_dir root)
            
        Returns:
            Dictionary with matched files and count
            
        Raises:
            PathError: If path is invalid
            ToolError: If search fails
        """
        try:
            dir_path = self._validate_path(path)
            
            if not os.path.isdir(dir_path):
                raise ToolError(f"Not a directory: {path}")
            
            from glob import glob
            
            # Build full pattern
            full_pattern = os.path.join(dir_path, pattern)
            matches = glob(full_pattern, recursive=True)
            
            # Validate all matches are within working directory
            valid_matches = []
            for match in matches:
                try:
                    self._validate_path(match)
                    valid_matches.append(os.path.relpath(match, self.working_dir))
                except PathError:
                    logger.warning(f"Skipping invalid match: {match}")
            
            valid_matches.sort()
            
            # Limit results
            if len(valid_matches) > DEFAULT_MAX_SEARCH_RESULTS:
                valid_matches = valid_matches[:DEFAULT_MAX_SEARCH_RESULTS]
                truncated = True
            else:
                truncated = False
            
            logger.debug(f"Searched for {pattern} in {path} ({len(valid_matches)} matches)")
            
            return {
                "pattern": pattern,
                "search_path": path,
                "matches": valid_matches,
                "total_matches": len(valid_matches),
                "truncated": truncated,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to search files: {e}")
    
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        Get file metadata and information.
        
        Args:
            path: File or directory path
            
        Returns:
            Dictionary with file info (size, type, modified time, permissions)
            
        Raises:
            PathError: If path is invalid
            ToolError: If stat fails
        """
        try:
            full_path = self._validate_path(path)
            
            if not os.path.exists(full_path):
                raise ToolError(f"Path does not exist: {path}")
            
            stat_info = os.stat(full_path)
            
            info = {
                "path": path,
                "exists": True,
                "is_file": os.path.isfile(full_path),
                "is_dir": os.path.isdir(full_path),
                "size": stat_info.st_size,
                "modified": stat_info.st_mtime,
                "permissions": oct(stat_info.st_mode)[-3:],
            }
            
            # Add file-specific info
            if os.path.isfile(full_path):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as handle:
                    info["lines"] = sum(1 for _ in handle)
            
            # Add directory-specific info
            if os.path.isdir(full_path):
                try:
                    entries = os.listdir(full_path)
                    info["entry_count"] = len(entries)
                except:
                    info["entry_count"] = None
            
            logger.debug(f"Got file info for {path}")
            
            return info
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to get file info for {path}: {e}")
    
    def delete_file(self, path: str) -> Dict[str, Any]:
        """
        Delete a file.
        
        Args:
            path: File path to delete
            
        Returns:
            Dictionary with path and deletion status
            
        Raises:
            PathError: If path is invalid
            ToolError: If deletion fails
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            os.remove(file_path)
            
            logger.info(f"Deleted file: {path}")
            
            return {
                "path": path,
                "deleted": True,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to delete file {path}: {e}")
    
    def list_all_files(self, path: str = ".", extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Recursively list all files in a directory.
        
        Args:
            path: Directory path (default: working_dir root)
            extensions: Filter by file extensions (e.g., ['.py', '.txt']), None for all
            
        Returns:
            Dictionary with file list and total count
            
        Raises:
            PathError: If path is invalid
            ToolError: If traversal fails
        """
        try:
            dir_path = self._validate_path(path)
            
            if not os.path.isdir(dir_path):
                raise ToolError(f"Not a directory: {path}")
            
            all_files = []
            
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    # Check extension filter
                    if extensions:
                        if not any(file.endswith(ext) for ext in extensions):
                            continue
                    
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.working_dir)
                    all_files.append(rel_path)
            
            all_files.sort()
            
            logger.debug(f"Listed all files in {path} ({len(all_files)} files)")
            
            return {
                "path": path,
                "extensions_filter": extensions,
                "files": all_files,
                "total": len(all_files),
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to list files in {path}: {e}")
    
    def search_package(self, name: str, language: str = "python") -> Dict[str, Any]:
        """
        Search for a package/dependency in package repositories.
        
        Args:
            name: Package name to search for
            language: Programming language ('python', 'javascript', etc.)
            
        Returns:
            Dictionary with search results (description, versions available, etc.)
            
        Raises:
            PackageError: If search fails
        """
        try:
            if language.lower() == "python":
                return self._search_python_package(name)
            elif language.lower() in ["javascript", "js", "node"]:
                return self._search_npm_package(name)
            else:
                raise PackageError(f"Unsupported language: {language}")
        except PackageError:
            raise
        except Exception as e:
            raise PackageError(f"Failed to search for package '{name}': {e}")
    
    def _search_python_package(self, name: str) -> Dict[str, Any]:
        """Search for a Python package on PyPI."""
        try:
            import urllib.request
            import json as json_module
            
            # Query PyPI JSON API
            url = f"https://pypi.org/pypi/{name}/json"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json_module.loads(response.read().decode('utf-8'))
            
            package_info = data.get('info', {})
            releases = data.get('releases', {})
            
            return {
                "language": "python",
                "name": package_info.get('name', name),
                "version": package_info.get('version'),
                "summary": package_info.get('summary', ''),
                "home_page": package_info.get('home_page', ''),
                "available_versions": sorted(releases.keys(), reverse=True)[:10],  # Last 10 versions
                "author": package_info.get('author', ''),
                "license": package_info.get('license', ''),
                "found": True,
            }
        except Exception as e:
            logger.warning(f"PyPI search for '{name}' failed: {e}")
            return {
                "language": "python",
                "name": name,
                "found": False,
                "error": str(e),
            }
    
    def _search_npm_package(self, name: str) -> Dict[str, Any]:
        """Search for an npm package."""
        try:
            import urllib.request
            import json as json_module
            
            # Query npm registry
            url = f"https://registry.npmjs.org/{name}"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json_module.loads(response.read().decode('utf-8'))
            
            latest_version = data.get('dist-tags', {}).get('latest', 'unknown')
            versions = list(data.get('versions', {}).keys())
            
            return {
                "language": "javascript",
                "name": data.get('name', name),
                "version": latest_version,
                "description": data.get('description', ''),
                "repository": data.get('repository', {}),
                "available_versions": sorted(versions, reverse=True)[:10],
                "author": data.get('author', ''),
                "found": True,
            }
        except Exception as e:
            logger.warning(f"npm search for '{name}' failed: {e}")
            return {
                "language": "javascript",
                "name": name,
                "found": False,
                "error": str(e),
            }
    
    def install_package(self, name: str, version: Optional[str] = None, 
                       language: str = "python") -> Dict[str, Any]:
        """
        Install a package/dependency.
        
        Args:
            name: Package name to install
            version: Optional version (e.g., "1.2.3", ">=1.0", "latest")
            language: Programming language ('python', 'javascript', etc.)
            
        Returns:
            Dictionary with installation status and details
            
        Raises:
            PackageError: If installation fails
        """
        try:
            if language.lower() == "python":
                return self._install_python_package(name, version)
            elif language.lower() in ["javascript", "js", "node"]:
                return self._install_npm_package(name, version)
            else:
                raise PackageError(f"Unsupported language: {language}")
        except PackageError:
            raise
        except Exception as e:
            raise PackageError(f"Failed to install package '{name}': {e}")
    
    def _install_python_package(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Install a Python package using pip."""
        try:
            # Validate package name (basic security check)
            if not self._validate_package_name(name):
                raise PackageError(f"Invalid package name: {name}")
            
            # Build package spec
            if version:
                package_spec = f"{name}=={version}" if not any(c in version for c in "=!<>~") else f"{name}{version}"
            else:
                package_spec = name
            
            logger.info(f"Installing Python package: {package_spec}")
            
            # Install using pip
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", package_spec],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Verify installation
                installed = self.check_package_installed(name, language="python")
                return {
                    "language": "python",
                    "package": name,
                    "version": version or "latest",
                    "success": True,
                    "installed_version": installed.get("installed_version"),
                }
            else:
                error_msg = result.stderr or result.stdout
                raise PackageError(f"pip install failed: {error_msg}")
        
        except PackageError:
            raise
        except subprocess.TimeoutExpired:
            raise PackageError(f"Installation timeout for {name}")
        except Exception as e:
            raise PackageError(f"Failed to install Python package '{name}': {e}")
    
    def _install_npm_package(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Install an npm package."""
        try:
            # Validate package name
            if not self._validate_package_name(name):
                raise PackageError(f"Invalid package name: {name}")
            
            # Build package spec
            if version:
                package_spec = f"{name}@{version}"
            else:
                package_spec = name
            
            logger.info(f"Installing npm package: {package_spec}")
            
            # Try npm first, fall back to yarn if available
            result = subprocess.run(
                ["npm", "install", "--silent", "--save", package_spec],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.working_dir
            )
            
            if result.returncode == 0:
                installed = self.check_package_installed(name, language="javascript")
                return {
                    "language": "javascript",
                    "package": name,
                    "version": version or "latest",
                    "success": True,
                    "installed_version": installed.get("installed_version"),
                }
            else:
                error_msg = result.stderr or result.stdout
                raise PackageError(f"npm install failed: {error_msg}")
        
        except PackageError:
            raise
        except subprocess.TimeoutExpired:
            raise PackageError(f"Installation timeout for {name}")
        except FileNotFoundError:
            raise PackageError("npm not found. Please install Node.js to use npm packages.")
        except Exception as e:
            raise PackageError(f"Failed to install npm package '{name}': {e}")
    
    def check_package_installed(self, name: str, language: str = "python") -> Dict[str, Any]:
        """
        Check if a package is installed and get its version.
        
        Args:
            name: Package name to check
            language: Programming language ('python', 'javascript', etc.)
            
        Returns:
            Dictionary with installed status and version
        """
        try:
            if language.lower() == "python":
                return self._check_python_package(name)
            elif language.lower() in ["javascript", "js", "node"]:
                return self._check_npm_package(name)
            else:
                raise PackageError(f"Unsupported language: {language}")
        except Exception as e:
            return {
                "name": name,
                "language": language,
                "installed": False,
                "error": str(e),
            }
    
    def _check_python_package(self, name: str) -> Dict[str, Any]:
        """Check if a Python package is installed."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Parse pip show output
                info = {}
                for line in result.stdout.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        info[key.strip().lower()] = value.strip()
                
                return {
                    "name": name,
                    "language": "python",
                    "installed": True,
                    "installed_version": info.get('version', 'unknown'),
                    "location": info.get('location', ''),
                }
            else:
                return {
                    "name": name,
                    "language": "python",
                    "installed": False,
                }
        except Exception as e:
            logger.debug(f"Failed to check Python package '{name}': {e}")
            return {
                "name": name,
                "language": "python",
                "installed": False,
                "error": str(e),
            }
    
    def _check_npm_package(self, name: str) -> Dict[str, Any]:
        """Check if an npm package is installed."""
        try:
            result = subprocess.run(
                ["npm", "ls", name, "--depth=0"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.working_dir
            )
            
            if result.returncode == 0 and f"{name}@" in result.stdout:
                # Parse version from output like: "package@1.2.3"
                for line in result.stdout.split('\n'):
                    if name in line and '@' in line:
                        parts = line.split('@')
                        if len(parts) >= 2:
                            version = parts[-1].strip()
                            return {
                                "name": name,
                                "language": "javascript",
                                "installed": True,
                                "installed_version": version,
                            }
            
            return {
                "name": name,
                "language": "javascript",
                "installed": False,
            }
        except FileNotFoundError:
            return {
                "name": name,
                "language": "javascript",
                "installed": False,
                "error": "npm not found",
            }
        except Exception as e:
            logger.debug(f"Failed to check npm package '{name}': {e}")
            return {
                "name": name,
                "language": "javascript",
                "installed": False,
                "error": str(e),
            }
    
    def list_installed_packages(self, language: str = "python") -> Dict[str, Any]:
        """
        List all installed packages for a language.
        
        Args:
            language: Programming language ('python', 'javascript', etc.)
            
        Returns:
            Dictionary with list of installed packages and versions
        """
        try:
            if language.lower() == "python":
                return self._list_python_packages()
            elif language.lower() in ["javascript", "js", "node"]:
                return self._list_npm_packages()
            else:
                raise PackageError(f"Unsupported language: {language}")
        except Exception as e:
            logger.error(f"Failed to list installed packages for {language}: {e}")
            return {
                "language": language,
                "packages": [],
                "error": str(e),
            }

    def clone_repo(self, repo_url: str, dest_dir: Optional[str] = None, branch: Optional[str] = None,
                   depth: Optional[int] = None) -> Dict[str, Any]:
        """
        Clone a git repository into the working directory.

        Args:
            repo_url: Git repository URL or local path
            dest_dir: Destination directory (relative to working_dir). If omitted, derive from repo_url.
            branch: Optional branch name to clone
            depth: Optional shallow clone depth (e.g., 1)

        Returns:
            Dictionary with clone status and paths

        Raises:
            ToolError: If inputs are invalid or clone fails
            PathError: If destination escapes working directory
        """
        try:
            if not repo_url or not isinstance(repo_url, str):
                raise ToolError("Repository URL must be a non-empty string")

            target_dir = dest_dir or self._derive_repo_dir_name(repo_url)
            if not target_dir:
                raise ToolError("Destination directory is required when it cannot be derived from repo URL")

            target_path = self._validate_path(target_dir)
            parent_dir = os.path.dirname(target_path)
            os.makedirs(parent_dir, exist_ok=True)

            if os.path.exists(target_path) and os.listdir(target_path):
                raise ToolError(f"Destination directory is not empty: {target_dir}")

            cmd = ["git", "clone"]
            if depth is not None:
                if not isinstance(depth, int) or depth <= 0:
                    raise ToolError("Depth must be a positive integer when provided")
                cmd.extend(["--depth", str(depth)])
            if branch:
                cmd.extend(["--branch", branch, "--single-branch"])
            cmd.extend([repo_url, target_path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.working_dir,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise GitError(f"git clone failed: {error_msg}")

            return {
                "repo_url": repo_url,
                "path": os.path.relpath(target_path, self.working_dir),
                "absolute_path": target_path,
                "branch": branch,
                "depth": depth,
                "success": True,
            }
        except (PathError, ToolError, GitError):
            raise
        except FileNotFoundError:
            raise GitError("git not found. Please install Git to use clone_repo.")
        except subprocess.TimeoutExpired:
            raise GitError("git clone timed out")
        except Exception as e:
            raise GitError(f"Failed to clone repository: {e}")

    def run_python(self, code: str, timeout: int = 30, log_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run Python code and return stdout/stderr plus execution metadata.

        Args:
            code: Python source code to execute
            timeout: Timeout in seconds
            log_path: Optional log file path (relative to working_dir)

        Returns:
            Dict with stdout, stderr, exit_code, timed_out, duration_ms, log_path
        """
        try:
            log_full_path = None
            if log_path:
                log_full_path = self._validate_path(log_path)
                log_dir = os.path.dirname(log_full_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)

            result = self.code_runner.run_python(
                code=code,
                cwd=self.working_dir,
                timeout=timeout,
                log_path=log_full_path,
            )

            if log_full_path:
                result["log_path"] = os.path.relpath(log_full_path, self.working_dir)
                result["log_path_abs"] = log_full_path

            result["success"] = (not result.get("timed_out")) and result.get("exit_code") == 0
            return result
        except PathError:
            raise
        except CodeRunError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to run Python code: {e}")

    def run_tests(
        self,
        framework: str = "pytest",
        args: Optional[List[str]] = None,
        timeout: int = 300,
        log_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run tests using the specified framework.

        Args:
            framework: Test framework to run ("pytest" or "unittest")
            args: Additional arguments to pass to the test runner
            timeout: Timeout in seconds
            log_path: Optional log file path (relative to working_dir)

        Returns:
            Dict with stdout, stderr, exit_code, timed_out, duration_ms, log_path
        """
        if framework not in {"pytest", "unittest"}:
            raise ToolError(f"Unsupported test framework: {framework}")
        if args is None:
            args = []
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ToolError("args must be a list of strings")

        try:
            log_full_path = None
            if log_path:
                log_full_path = self._validate_path(log_path)
                log_dir = os.path.dirname(log_full_path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)

            command = [sys.executable, "-m", framework]
            command.extend(args)

            result = self.code_runner.run_tests(
                command=command,
                cwd=self.working_dir,
                timeout=timeout,
                log_path=log_full_path,
            )

            if log_full_path:
                result["log_path"] = os.path.relpath(log_full_path, self.working_dir)
                result["log_path_abs"] = log_full_path

            result["success"] = (not result.get("timed_out")) and result.get("exit_code") == 0
            return result
        except PathError:
            raise
        except CodeRunError as e:
            raise ToolError(str(e))
        except Exception as e:
            raise ToolError(f"Failed to run tests: {e}")
    
    def checkout_branch(self, repo_dir: str, branch_name: str, create: bool = True) -> Dict[str, Any]:
        """
        Checkout a git branch in a repository directory.
        
        Creates a new branch and checks it out if create=True (default).
        Switches to an existing branch if create=False.
        
        Args:
            repo_dir: Repository directory (relative to working_dir)
            branch_name: Branch name to create/checkout
            create: Whether to create a new branch (default: True)
            
        Returns:
            Dictionary with checkout status and branch name
            
        Raises:
            ToolError: If inputs are invalid or checkout fails
            PathError: If repo_dir escapes working directory
            GitError: If git operation fails
        """
        try:
            if not branch_name or not isinstance(branch_name, str):
                raise ToolError("Branch name must be a non-empty string")
            
            # Validate branch name format (git-friendly)
            if not re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_/-]*$', branch_name):
                raise ToolError(
                    f"Invalid branch name: {branch_name}. "
                    "Use only alphanumeric, underscore, hyphen, and forward slash. "
                    "Cannot start with hyphen or slash."
                )
            
            repo_path = self._validate_path(repo_dir)
            
            if not os.path.isdir(repo_path):
                raise ToolError(f"Repository directory not found: {repo_dir}")
            
            # Check if it's a git repository
            git_dir = os.path.join(repo_path, ".git")
            if not os.path.exists(git_dir):
                raise GitError(f"Not a git repository: {repo_dir}")
            
            # Build git checkout command
            if create:
                cmd = ["git", "checkout", "-b", branch_name]
            else:
                cmd = ["git", "checkout", branch_name]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise GitError(f"git checkout failed: {error_msg}")
            
            logger.info(f"Checked out branch '{branch_name}' in {repo_dir}")
            
            return {
                "repo_dir": repo_dir,
                "branch_name": branch_name,
                "created": create,
                "success": True,
            }
        
        except (PathError, ToolError, GitError):
            raise
        except FileNotFoundError:
            raise GitError("git not found. Please install Git to use checkout_branch.")
        except subprocess.TimeoutExpired:
            raise GitError("git checkout timed out")
        except Exception as e:
            raise GitError(f"Failed to checkout branch: {e}")

    def push_branch(self, repo_dir: str, branch_name: Optional[str] = None, set_upstream: bool = True) -> Dict[str, Any]:
            """
            Push a git branch to the remote repository.
        
            Args:
                repo_dir: Repository directory (relative to working_dir)
                branch_name: Branch name to push (default: current branch)
                set_upstream: Whether to set upstream tracking (default: True)
            
            Returns:
                Dictionary with push status, branch name, and remote info
            
            Raises:
                ToolError: If inputs are invalid or push fails
                PathError: If repo_dir escapes working directory
                GitError: If git operation fails
            """
            try:
                repo_path = self._validate_path(repo_dir)
            
                if not os.path.isdir(repo_path):
                    raise ToolError(f"Repository directory not found: {repo_dir}")
            
                # Check if it's a git repository
                git_dir = os.path.join(repo_path, ".git")
                if not os.path.exists(git_dir):
                    raise GitError(f"Not a git repository: {repo_dir}")
            
                # Get current branch if not specified
                if not branch_name:
                    result = subprocess.run(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=repo_path,
                    )
                    if result.returncode != 0:
                        raise GitError("Failed to get current branch name")
                    branch_name = result.stdout.strip()
            
                # Check if remote exists
                result = subprocess.run(
                    ["git", "remote"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=repo_path,
                )
            
                if result.returncode != 0 or not result.stdout.strip():
                    raise GitError("No git remote configured")
            
                remote_name = result.stdout.strip().split()[0]  # Use first remote (typically 'origin')
            
                # Build push command
                if set_upstream:
                    cmd = ["git", "push", "-u", remote_name, branch_name]
                else:
                    cmd = ["git", "push", remote_name, branch_name]
            
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=repo_path,
                )
            
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    raise GitError(f"git push failed: {error_msg}")
            
                logger.info(f"Pushed branch '{branch_name}' to {remote_name}")
            
                return {
                    "repo_dir": repo_dir,
                    "branch_name": branch_name,
                    "remote": remote_name,
                    "set_upstream": set_upstream,
                    "success": True,
                }
        
            except (PathError, ToolError, GitError):
                raise
            except FileNotFoundError:
                raise GitError("git not found. Please install Git to use push_branch.")
            except subprocess.TimeoutExpired:
                raise GitError("git push timed out")
            except Exception as e:
                raise GitError(f"Failed to push branch: {e}")
    
    def create_pull_request(self, repo_dir: str, title: Optional[str] = None, 
                           body: Optional[str] = None, base_branch: str = "main") -> Dict[str, Any]:
            """
            Create a pull request using GitHub CLI (gh).
        
            Requires GitHub CLI to be installed and authenticated.
        
            Args:
                repo_dir: Repository directory (relative to working_dir)
                title: PR title (default: uses branch name)
                body: PR description (default: empty)
                base_branch: Target branch for PR (default: "main")
            
            Returns:
                Dictionary with PR URL and status
            
            Raises:
                ToolError: If inputs are invalid or PR creation fails
                PathError: If repo_dir escapes working directory
                GitError: If git/gh operation fails
            """
            try:
                repo_path = self._validate_path(repo_dir)
            
                if not os.path.isdir(repo_path):
                    raise ToolError(f"Repository directory not found: {repo_dir}")
            
                # Check if it's a git repository
                git_dir = os.path.join(repo_path, ".git")
                if not os.path.exists(git_dir):
                    raise GitError(f"Not a git repository: {repo_dir}")
            
                # Check if gh CLI is available
                try:
                    subprocess.run(
                        ["gh", "--version"],
                        capture_output=True,
                        timeout=10,
                    )
                except FileNotFoundError:
                    raise GitError(
                        "GitHub CLI (gh) not found. Install from https://cli.github.com/ "
                        "and authenticate with 'gh auth login'"
                    )
            
                # Get current branch name
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=repo_path,
                )
                if result.returncode != 0:
                    raise GitError("Failed to get current branch name")
                branch_name = result.stdout.strip()
            
                # Use branch name as title if not provided
                if not title:
                    title = branch_name.replace('_', ' ').replace('-', ' ').title()
            
                # Build gh pr create command
                cmd = [
                    "gh", "pr", "create",
                    "--base", base_branch,
                    "--head", branch_name,
                    "--title", title,
                ]
            
                if body:
                    cmd.extend(["--body", body])
                else:
                    cmd.append("--body=")  # Empty body
            
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=repo_path,
                )
            
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    # Check for common errors
                    if "already exists" in error_msg.lower():
                        logger.info(f"Pull request already exists for branch '{branch_name}'")
                        return {
                            "repo_dir": repo_dir,
                            "branch_name": branch_name,
                            "base_branch": base_branch,
                            "already_exists": True,
                            "success": True,
                        }
                    raise GitError(f"gh pr create failed: {error_msg}")
            
                # Extract PR URL from output
                pr_url = result.stdout.strip().split()[-1] if result.stdout else "unknown"
            
                logger.info(f"Created pull request: {pr_url}")
            
                return {
                    "repo_dir": repo_dir,
                    "branch_name": branch_name,
                    "base_branch": base_branch,
                    "title": title,
                    "pr_url": pr_url,
                    "success": True,
                }
        
            except (PathError, ToolError, GitError):
                raise
            except subprocess.TimeoutExpired:
                raise GitError("gh pr create timed out")
            except Exception as e:
                raise GitError(f"Failed to create pull request: {e}")
    
    
    def _list_python_packages(self) -> Dict[str, Any]:
        """List installed Python packages."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return {
                    "language": "python",
                    "packages": packages,
                    "count": len(packages),
                }
            else:
                raise PackageError("pip list failed")
        except json.JSONDecodeError:
            raise PackageError("Failed to parse pip list output")
    
    def _list_npm_packages(self) -> Dict[str, Any]:
        """List installed npm packages."""
        try:
            result = subprocess.run(
                ["npm", "ls", "--depth=0", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.working_dir
            )
            
            if result.returncode in [0, 1]:  # npm ls returns 1 if packages missing, but still has output
                data = json.loads(result.stdout)
                packages = data.get('dependencies', {})
                
                package_list = [
                    {"name": name, "version": info.get("version", "unknown")}
                    for name, info in packages.items()
                ]
                
                return {
                    "language": "javascript",
                    "packages": package_list,
                    "count": len(package_list),
                }
            else:
                raise PackageError("npm ls failed")
        except FileNotFoundError:
            return {
                "language": "javascript",
                "packages": [],
                "error": "npm not found",
            }
        except json.JSONDecodeError:
            raise PackageError("Failed to parse npm ls output")
    
    @staticmethod
    def _validate_package_name(name: str) -> bool:
        """
        Validate package name for security.
        
        Args:
            name: Package name to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Reject obviously malicious patterns
        if not name or not isinstance(name, str):
            return False
        
        # Reject paths and shell commands
        if any(c in name for c in ['/', '\\', ';', '|', '&', '`', '$']):
            return False
        
        # Allow alphanumeric, hyphens, underscores, dots
        import re
        if not re.match(r'^[\w\-\.]+$', name):
            return False
        
        return True

    @staticmethod
    def _derive_repo_dir_name(repo_url: str) -> str:
        """
        Derive a repository directory name from a URL or path.

        Examples:
            https://github.com/org/repo.git -> repo
            git@github.com:org/repo.git -> repo
            /path/to/repo -> repo
        """
        if not repo_url or not isinstance(repo_url, str):
            return ""

        cleaned = repo_url.rstrip("/")
        base = os.path.basename(cleaned)
        if base.endswith(".git"):
            base = base[:-4]
        return base
    
    def confirm_task_complete(self, summary: str = "", deliverables: List[str] = None) -> Dict[str, Any]:
        """
        Confirm that the assigned task is complete.
        
        Call this when you have completed all work for the assigned task.
        Provide a summary and list any deliverables created.
        
        Args:
            summary: Brief summary of what was completed (optional)
            deliverables: List of files or outputs created (optional)
            
        Returns:
            Confirmation dict with completion status
        """
        from datetime import datetime, timezone
        
        if deliverables is None:
            deliverables = []
        
        return {
            "status": "complete",
            "task_complete": True,
            "summary": summary,
            "deliverables": deliverables,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def audit_files(self, file_paths: List[str], description: str = "", focus_areas: List[str] = None, produced_files: List[str] = None) -> Dict[str, Any]:
        """
        Request an auditor to review specific files.
        
        Use this to trigger a direct audit of files you've created or modified,
        rather than waiting for the manager to assign an audit task.
        
        RESTRICTION: Can only audit files that have been produced during this task execution.
        Audit requests must come AFTER the files have been created/modified with write_file,
        append_file, or edit_file calls.
        
        Args:
            file_paths: List of relative file paths to audit
            description: Description of what to audit and why (e.g., "Check for security issues", "Verify implementation matches spec")
            focus_areas: Optional list of specific areas to focus on (e.g., ["error_handling", "performance", "security"])
            produced_files: Internal parameter - list of files produced during this task execution
            
        Returns:
            Audit request dict with files and audit details
            
        Raises:
            ToolError: If auditing files that haven't been produced yet
        """
        from datetime import datetime, timezone
        
        if focus_areas is None:
            focus_areas = []
        
        if produced_files is None:
            produced_files = []
        
        # Validate that audit_files only references files that were produced
        unproduced_files = [f for f in file_paths if f not in produced_files]
        if unproduced_files:
            error_msg = f"Cannot audit files that haven't been produced: {unproduced_files}. Only audit files you created/modified with write_file, append_file, or edit_file."
            logger.error(error_msg)
            raise ToolError(error_msg)
        
        # Validate that files exist
        validated_files = []
        for file_path in file_paths:
            try:
                abs_path = self._validate_path(file_path)
                if os.path.isfile(abs_path):
                    validated_files.append(file_path)
                else:
                    logger.warning(f"File not found for audit: {file_path}")
            except PathError as e:
                logger.warning(f"Invalid path for audit: {file_path} - {e}")
        
        return {
            "status": "audit_requested",
            "audit_type": "file_review",
            "files": validated_files,
            "invalid_files": [f for f in file_paths if f not in validated_files],
            "description": description,
            "focus_areas": focus_areas,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Helper functions for direct use
def get_tools(working_dir: str = DEFAULT_WORKING_DIR, allowed_tools: Optional[List[str]] = None) -> AgentTools:
def get_tools(working_dir: str = DEFAULT_WORKING_DIR, allowed_tools: Optional[List[str]] = None) -> AgentTools:
    """
    Factory function to create an AgentTools instance.

    
    Args:
        working_dir: Root directory for operations
        allowed_tools: Optional list of tool names allowed for the role
        allowed_tools: Optional list of tool names allowed for the role
        
    Returns:
        AgentTools instance
    """
    return AgentTools(working_dir, allowed_tools=allowed_tools)
    return AgentTools(working_dir, allowed_tools=allowed_tools)


def get_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
def get_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
    """
    Get a formatted description of all available tools for injection into agent prompts.
    
    Returns:
        Multi-line string describing all tools and their signatures
    """
    description = """
    description = """
Available tools (call these methods in your implementation):

File Reading:
  - read_file(path: str) -> str: Read file contents
  - get_file_info(path: str) -> dict: Get file metadata (size, type, lines, etc.)

File Writing:
  - write_file(path: str, content: str) -> dict: Create or overwrite file (auto-creates directories)
  - append_file(path: str, content: str) -> dict: Append to file or create if missing
    - edit_file(path: str, diff: str) -> dict: Apply unified diff to file
    - edit_file(path: str, diff: str) -> dict: Apply unified diff to file

Directory Operations:
  - list_directory(path: str) -> dict: List immediate contents (non-recursive)
  - list_all_files(path: str, extensions: list = None) -> dict: Recursively list files with optional extension filter

Search:
  - search_files(pattern: str, path: str = ".") -> dict: Search with glob patterns (supports ** for recursion)

Deletion:
  - delete_file(path: str) -> dict: Delete a file

Package Management:
  - search_package(name: str, language: str = "python") -> dict: Search for a package in repositories (PyPI, npm, etc.)
  - install_package(name: str, version: str = None, language: str = "python") -> dict: Install a package/dependency
  - check_package_installed(name: str, language: str = "python") -> dict: Check if a package is installed and get version
  - list_installed_packages(language: str = "python") -> dict: List all installed packages for a language

Execution:
    - run_python(code: str, timeout: int = 30, log_path: str = None) -> dict: Execute Python code and return output
    - run_tests(framework: str = "pytest", args: list = None, timeout: int = 300, log_path: str = None) -> dict: Run tests via pytest or unittest

Git Operations:
  - clone_repo(repo_url: str, dest_dir: str = None, branch: str = None, depth: int = None) -> dict: Clone a git repo into working_dir
  - checkout_branch(repo_dir: str, branch_name: str, create: bool = True) -> dict: Create and checkout a new branch (or switch to existing)

Task Completion:
  - confirm_task_complete(summary: str = "", deliverables: list = None) -> dict: Confirm task is complete and provide summary

Auditing:
  - audit_files(file_paths: list, description: str = "", focus_areas: list = None) -> dict: Request an auditor to review specific files
    * file_paths: List of relative paths to files that need review
    * description: What to audit and why (e.g., "Check for security issues", "Verify implementation")
    * focus_areas: Optional list of areas to focus on (e.g., ["error_handling", "performance", "security"])
    * Use this directly rather than waiting for manager to assign audit tasks

Supported Languages:
  - "python" (uses PyPI and pip)
  - "javascript" or "node" (uses npm registry)

Security:
- All paths must be relative to the working directory (no absolute paths or ../)
- Package names are validated to prevent injection attacks
- Installation has a 120 second timeout
- Only alphanumeric, hyphens, underscores, and dots allowed in package names

Exception types: PathError (invalid path), FileSizeError (>10MB), PackageError (package operations failed), GitError (git operations failed), ToolError (general failures).
See docs/agents/AGENT_TOOLS_GUIDE.md for detailed examples and patterns.
""".strip()

    if allowed_tools is not None:
        allowed_line = "Allowed tools for your role: " + ", ".join(allowed_tools)
        return f"{description}\n\n{allowed_line}".strip()
    if allowed_tools is not None:
        allowed_line = "Allowed tools for your role: " + ", ".join(allowed_tools)
        return f"{description}\n\n{allowed_line}".strip()

    return description


def get_manager_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
    return description


def get_manager_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
    """
    Get a formatted description of task assignment tools for the manager role.
    
    Returns:
        Multi-line string describing assignment tools and their usage
    """
    description = """
    description = """
Available task assignment tools:

Task Assignment:
  - assign_task(role: str, task: str, sequence: int) -> dict: Assign a single task to a role
    * role: One of 'developer', 'auditor'
    * task: Detailed task description (include context about dependencies)
    * sequence: Execution order (0=first, 1=second, etc.; same sequence runs in parallel)
    * Returns: {success: bool, task_id: str}

  - assign_tasks(assignments: list) -> dict: Assign multiple tasks at once
    * assignments: List of objects with 'role', 'task', 'sequence' fields
    * Each assignment object must have all three fields
    * Returns: {success: bool, task_ids: list, errors: list}

Examples:
  1. Sequential tasks (execute one after another):
     - assign_task('developer', 'Create auth.py with User class', sequence=0)
     - assign_task('developer', 'Add login() method to User class', sequence=1)

  2. Parallel tasks (execute simultaneously, then move to next sequence):
     - assign_tasks([
         {role: 'developer', task: 'Create module A', sequence: 0},
         {role: 'developer', task: 'Create module B', sequence: 0},
         {role: 'auditor', task: 'Review both modules', sequence: 1}
       ])

IMPORTANT:
- Use assign_task() for single tasks or assign_tasks() for batches
- Set sequence=0 for independent parallel tasks, sequence=1 for dependent tasks
- Include ALL necessary context in task descriptions since developers cannot see each other
- The 'auditor' role should typically come AFTER developer tasks (higher sequence number)
- Call assign_task/assign_tasks multiple times to build your task plan
""".strip()

    if allowed_tools is not None:
        allowed_line = "Allowed tools for your role: " + ", ".join(allowed_tools)
        return f"{description}\n\n{allowed_line}".strip()

    return description

    if allowed_tools is not None:
        allowed_line = "Allowed tools for your role: " + ", ".join(allowed_tools)
        return f"{description}\n\n{allowed_line}".strip()

    return description
