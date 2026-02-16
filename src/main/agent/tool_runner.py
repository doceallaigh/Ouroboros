"""
Tool execution and definitions for agents.

This module is the canonical home for the agent-tool interface:
- ``AgentTools``: safe file-system, package-management, and git operations
- ``ToolError`` and subclasses: exception hierarchy
- ``TOOL_DEFINITIONS``: JSON schemas for structured tool calling (OpenAI format)
- ``get_tools_for_role()``: filter schemas by allowed tool list
- ``ToolEnvironment``: builds name -> callable mapping with output capture,
  file tracking, audit tracking, and task-completion signals
- ``execute_tools_from_response()``: parses agent output (code blocks,
  structured tool_calls, or inline calls) and executes them

The ``tools`` package re-exports the public symbols for backward compatibility.
"""

import ast
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Set

from fileio.audit_log import AuditLogManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_PAGE_LINES = 500
DEFAULT_MAX_SEARCH_RESULTS = 100
DEFAULT_WORKING_DIR = os.getcwd()
ALLOWED_PACKAGE_PREFIXES = []  # Empty = allow all (can be restricted)


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# AgentTools – safe file-system access for agents
# ---------------------------------------------------------------------------

class AgentTools:
    """
    Provides agents with safe file system tools.
    
    All operations are restricted to a designated working directory
    to prevent directory traversal attacks.
    """
    def __init__(self, working_dir: str = DEFAULT_WORKING_DIR, max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        """
        Initialize agent tools.
        
        Args:
            working_dir: Root directory for all operations (default: current directory)
            max_file_size: Maximum file size in bytes for read operations
            
        Raises:
            ToolError: If working directory doesn't exist
        """
        if not os.path.isdir(working_dir):
            raise ToolError(f"Working directory not found: {working_dir}")
        
        self.working_dir = os.path.abspath(working_dir)
        self.max_file_size = max_file_size
        logger.info(f"Initialized AgentTools with working_dir: {self.working_dir}")
    
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
    
    def list_directory(self, path: str = ".", depth: int = -1) -> Dict[str, Any]:
        """
        List contents of a directory as a recursive tree.
        
        Args:
            path: Directory path (relative to working_dir)
            depth: Maximum recursion depth (-1 for unlimited, 0 for immediate only)
            
        Returns:
            Dictionary with a recursive tree of directories and files
            
        Raises:
            PathError: If path is invalid
            ToolError: If directory doesn't exist
        """
        try:
            dir_path = self._validate_path(path)
            
            if not os.path.isdir(dir_path):
                raise ToolError(f"Not a directory: {path}")
            
            def _build_tree(current_path: str, current_depth: int) -> Dict[str, Any]:
                entries = os.listdir(current_path)
                directories = []
                files = []
                
                for entry in sorted(entries):
                    full_path = os.path.join(current_path, entry)
                    if os.path.isdir(full_path):
                        if depth == -1 or current_depth < depth:
                            subtree = _build_tree(full_path, current_depth + 1)
                            directories.append({"name": entry, **subtree})
                        else:
                            directories.append({"name": entry})
                    else:
                        files.append(entry)
                
                return {
                    "directories": directories,
                    "files": files,
                }
            
            tree = _build_tree(dir_path, 0)
            
            # Count totals recursively
            def _count(node: Dict[str, Any]) -> int:
                total = len(node.get("files", []))
                for d in node.get("directories", []):
                    total += 1  # count the directory itself
                    total += _count(d)
                return total
            
            total = _count(tree)
            
            logger.debug(f"Listed directory tree: {path} ({total} entries)")
            
            return {
                "path": path,
                **tree,
                "total": total,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to list directory {path}: {e}")
    
    def read_file(self, path: str, page: int = 1, encoding: str = "utf-8", page_size: int = DEFAULT_PAGE_LINES) -> Dict[str, Any]:
        """
        Read file contents with pagination.
        
        Args:
            path: File path (relative to working_dir)
            page: Page number to read (1-based, default: 1)
            encoding: Text encoding (default: utf-8)
            page_size: Lines per page (default: DEFAULT_PAGE_LINES)
            
        Returns:
            Dict with keys:
              - content: The text for the requested page
              - page: Current page number
              - total_pages: Total number of pages
              - total_lines: Total line count of the file
              - path: The file path requested
            
        Raises:
            PathError: If path is invalid
            ToolError: If read fails
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            with open(file_path, 'r', encoding=encoding) as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            total_pages = max(1, (total_lines + page_size - 1) // page_size)
            safe_page = max(1, min(page, total_pages))
            start = (safe_page - 1) * page_size
            end = start + page_size
            content = "".join(lines[start:end])
            
            # Remove trailing newline added by join for consistency
            if content.endswith("\n") and total_lines > 0 and not lines[-1].endswith("\n") and end >= total_lines:
                pass  # keep as-is; file didn't end with newline originally only on last page
            
            file_size = os.path.getsize(file_path)
            logger.debug(f"Read file: {path} (page {safe_page}/{total_pages}, {file_size} bytes total)")
            
            return {
                "content": content,
                "page": safe_page,
                "total_pages": total_pages,
                "total_lines": total_lines,
                "path": path,
            }
        
        except PathError:
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
    
    def edit_file(self, path: str, diff: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Edit file by applying a unified diff.
        
        Args:
            path: File path (relative to working_dir)
            diff: Unified diff string (single-file) to apply
            encoding: Text encoding (default: utf-8)
            
        Returns:
            Dictionary with path, hunks applied, and result
            
        Raises:
            PathError: If path is invalid
            ToolError: If patch fails or does not match file contents
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            # Read file
            with open(file_path, 'r', encoding=encoding) as f:
                original_lines = f.read().splitlines(keepends=True)
            
            new_lines, stats = self._apply_unified_diff(original_lines, diff)
            
            if not stats["hunks"]:
                return {
                    "path": path,
                    "hunks": 0,
                    "added": 0,
                    "removed": 0,
                    "success": False,
                    "message": "No hunks applied",
                }
            
            # Write back
            with open(file_path, 'w', encoding=encoding) as f:
                f.write("".join(new_lines))
            
            logger.info(
                f"Edited file: {path} (hunks={stats['hunks']}, added={stats['added']}, removed={stats['removed']})"
            )
            
            return {
                "path": path,
                "hunks": stats["hunks"],
                "added": stats["added"],
                "removed": stats["removed"],
                "success": True,
            }
        
        except PathError:
            raise
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to edit file {path}: {e}")

    def _apply_unified_diff(self, original_lines: List[str], diff: str) -> (List[str], Dict[str, int]):
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
                info["lines"] = sum(1 for _ in open(full_path, 'r', encoding='utf-8', errors='ignore'))
            
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
        import re as re_mod
        if not re_mod.match(r'^[\w\-\.]+$', name):
            return False
        
        return True
    
    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    def run_python(self, code: str, timeout: int = 30, log_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute Python code in a subprocess and return the result.

        Delegates to :class:`tools.code_runner.CodeRunner`.

        Args:
            code: Python source code to execute
            timeout: Maximum execution time in seconds (default: 30)
            log_path: Optional path (relative to working_dir) to write stdout/stderr

        Returns:
            Dict with stdout, stderr, exit_code, timed_out, duration_ms, success, log_path

        Raises:
            PathError: If log_path escapes working directory
            ToolError: If execution setup fails
        """
        from tools.code_runner import CodeRunner

        abs_log = None
        if log_path:
            abs_log = self._validate_path(log_path)

        runner = CodeRunner()
        result = runner.run_python(
            code, cwd=self.working_dir, timeout=timeout, log_path=abs_log,
        )
        result["success"] = result.get("exit_code") == 0
        return result

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def clone_repo(
        self,
        repo_url: str,
        dest_dir: Optional[str] = None,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Clone a git repository into the working directory.

        Args:
            repo_url: HTTPS or SSH URL of the repository
            dest_dir: Destination directory name (default: derived from URL)
            branch: Branch to checkout after cloning
            depth: Shallow clone depth (must be >= 1)

        Returns:
            Dict with success flag and cloned path

        Raises:
            ToolError: If clone fails or destination is non-empty
        """
        if depth is not None and depth < 1:
            raise ToolError(f"Depth must be >= 1, got {depth}")

        if dest_dir is None:
            # Derive directory name from repo URL
            dest_dir = repo_url.rstrip("/").rsplit("/", 1)[-1]
            if dest_dir.endswith(".git"):
                dest_dir = dest_dir[:-4]

        abs_dest = self._validate_path(dest_dir)

        # Reject non-empty destination
        if os.path.isdir(abs_dest) and os.listdir(abs_dest):
            raise ToolError(f"Destination directory is not empty: {dest_dir}")

        cmd = ["git", "clone"]
        if branch:
            cmd += ["--branch", branch, "--single-branch"]
        if depth is not None:
            cmd += ["--depth", str(depth)]
        cmd += [repo_url, abs_dest]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            raise ToolError(f"git clone failed: {exc.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise ToolError("git clone timed out after 120s")

        return {"success": True, "path": dest_dir}

    def checkout_branch(
        self,
        repo_dir: str,
        branch_name: str,
        create: bool = True,
    ) -> Dict[str, Any]:
        """
        Checkout (or create) a branch in a local git repository.

        Args:
            repo_dir: Repository directory (relative to working_dir)
            branch_name: Branch name
            create: If True (default) creates the branch with ``-b``

        Returns:
            Dict with success, branch_name, created

        Raises:
            ToolError: Invalid branch name or repo dir
            GitError: Not a git repository
        """
        # Validate branch name
        if not re.match(r'^[\w\-/\.]+$', branch_name):
            raise ToolError(f"Invalid branch name: {branch_name}")

        abs_repo = self._validate_path(repo_dir)
        if not os.path.isdir(abs_repo):
            raise ToolError(f"Repository directory not found: {repo_dir}")
        if not os.path.isdir(os.path.join(abs_repo, ".git")):
            raise GitError(f"Not a git repository: {repo_dir}")

        cmd = ["git", "checkout"]
        if create:
            cmd.append("-b")
        cmd.append(branch_name)

        try:
            subprocess.run(cmd, cwd=abs_repo, check=True, capture_output=True, text=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            raise GitError(f"git checkout failed: {exc.stderr.strip()}")

        return {"success": True, "branch_name": branch_name, "created": create}

    def push_branch(
        self,
        repo_dir: str,
        branch_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Push the current (or specified) branch to its remote.

        Args:
            repo_dir: Repository directory (relative to working_dir)
            branch_name: Branch to push (default: current branch)

        Returns:
            Dict with success, branch_name, remote

        Raises:
            GitError: No remote configured or push fails
        """
        abs_repo = self._validate_path(repo_dir)
        if not os.path.isdir(os.path.join(abs_repo, ".git")):
            raise GitError(f"Not a git repository: {repo_dir}")

        if branch_name is None:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=abs_repo, capture_output=True, text=True, timeout=10,
            )
            branch_name = res.stdout.strip()

        # Discover remote
        res = subprocess.run(
            ["git", "remote"],
            cwd=abs_repo, capture_output=True, text=True, timeout=10,
        )
        remote = res.stdout.strip().splitlines()[0] if res.stdout.strip() else ""
        if not remote:
            raise GitError("No remote configured for this repository")

        try:
            subprocess.run(
                ["git", "push", "-u", remote, branch_name],
                cwd=abs_repo, check=True, capture_output=True, text=True, timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            raise GitError(f"git push failed: {exc.stderr.strip()}")

        return {"success": True, "branch_name": branch_name, "remote": remote}

    def create_pull_request(
        self,
        repo_dir: str,
        base_branch: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a pull request using the GitHub CLI (``gh``).

        Args:
            repo_dir: Repository directory (relative to working_dir)
            base_branch: Base branch for the PR (default: repo default)
            title: PR title (default: auto from branch)
            body: PR body text

        Returns:
            Dict with success, pr_url, already_exists

        Raises:
            GitError: ``gh`` not found or PR creation fails
        """
        abs_repo = self._validate_path(repo_dir)
        if not os.path.isdir(os.path.join(abs_repo, ".git")):
            raise GitError(f"Not a git repository: {repo_dir}")

        # Check gh availability
        try:
            subprocess.run(
                ["gh", "--version"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError:
            raise GitError("GitHub CLI (gh) is not installed")

        # Current branch
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=abs_repo, capture_output=True, text=True, timeout=10,
        )
        head_branch = res.stdout.strip()

        cmd = ["gh", "pr", "create", "--head", head_branch]
        if base_branch:
            cmd += ["--base", base_branch]
        if title:
            cmd += ["--title", title]
        if body:
            cmd += ["--body", body]
        if not title:
            cmd += ["--fill"]

        try:
            result = subprocess.run(
                cmd, cwd=abs_repo, capture_output=True, text=True, timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            raise GitError(f"gh pr create failed: {exc.stderr.strip()}")

        if result.returncode != 0:
            if "already exists" in result.stderr.lower():
                return {"success": True, "already_exists": True, "pr_url": ""}
            raise GitError(f"gh pr create failed: {result.stderr.strip()}")

        return {"success": True, "pr_url": result.stdout.strip(), "already_exists": False}


# Helper functions for direct use
def get_tools(working_dir: str = DEFAULT_WORKING_DIR) -> AgentTools:
    """
    Factory function to create an AgentTools instance.

    Args:
        working_dir: Root directory for operations

    Returns:
        AgentTools instance
    """
    return AgentTools(working_dir)


# ---------------------------------------------------------------------------
# Tool definitions – OpenAI JSON Schema format
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: Dict[str, Any] = {
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
                                "role": {"type": "string", "description": "The role to assign the task to"},
                                "task": {"type": "string", "description": "Task description"},
                                "sequence": {"type": "integer", "description": "Execution order"}
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
                    "path": {"type": "string", "description": "File path relative to working directory"},
                    "content": {"type": "string", "description": "Content to write to the file"}
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
                    "path": {"type": "string", "description": "File path relative to working directory"},
                    "page": {"type": "integer", "description": "Page number to read (1-based, default 1). Each page contains 500 lines."}
                },
                "required": ["path"]
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
                    "path": {"type": "string", "description": "File path relative to working directory"},
                    "diff": {"type": "string", "description": "Diff showing changes to make"}
                },
                "required": ["path", "diff"]
            }
        }
    },
    "list_directory": {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List contents of a directory as a recursive tree. Returns nested directories and files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to working directory"},
                    "depth": {"type": "integer", "description": "Maximum recursion depth (-1 for unlimited, 0 for immediate only). Default: -1"}
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
                    "path": {"type": "string", "description": "Directory path relative to working directory"},
                    "extensions": {"type": "array", "description": "Optional list of file extensions to filter by", "items": {"type": "string"}}
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
                    "pattern": {"type": "string", "description": "File pattern to search for (e.g., '*.py', 'test_*.py')"},
                    "path": {"type": "string", "description": "Directory to search in, defaults to current directory"}
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
                    "path": {"type": "string", "description": "File path to delete relative to working directory"}
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
                    "path": {"type": "string", "description": "File path relative to working directory"}
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
                    "repo_url": {"type": "string", "description": "Repository URL to clone"},
                    "dest_dir": {"type": "string", "description": "Destination directory for the clone"},
                    "branch": {"type": "string", "description": "Branch to check out"},
                    "depth": {"type": "integer", "description": "Shallow clone depth"}
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
                    "repo_dir": {"type": "string", "description": "Repository directory"},
                    "branch_name": {"type": "string", "description": "Branch name to checkout"},
                    "create": {"type": "boolean", "description": "Whether to create the branch if it doesn't exist"}
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
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                    "log_path": {"type": "string", "description": "Optional path to log output"}
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
                    "message": {"type": "string", "description": "The callback message"},
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
                    "file_paths": {"type": "array", "description": "List of file paths to audit", "items": {"type": "string"}},
                    "description": {"type": "string", "description": "What to audit for (e.g., 'code quality', 'security issues')"},
                    "focus_areas": {"type": "array", "description": "Specific areas to focus the audit on", "items": {"type": "string"}}
                },
                "required": ["file_paths", "description"]
            }
        }
    },
    "confirm_task_complete": {
        "type": "function",
        "function": {
            "name": "confirm_task_complete",
            "description": "Confirm that the assigned task is complete",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of what was completed"},
                    "deliverables": {"type": "array", "description": "List of files or outputs created", "items": {"type": "string"}}
                }
            }
        }
    },
    "record_audit_success": {
        "type": "function",
        "function": {
            "name": "record_audit_success",
            "description": "Record successful audit of files or directories. Files/directories are recorded in the audit_log with current timestamp. Task is complete when all files in edit_log are audited with later timestamps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "description": "List of file paths that were audited",
                        "items": {"type": "string"}
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of the audit findings"
                    }
                },
                "required": ["file_paths"]
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
                    "name": {"type": "string", "description": "Package name to search for"},
                    "language": {"type": "string", "description": "Programming language (e.g., 'python', 'javascript')"}
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
                    "name": {"type": "string", "description": "Package name to install"},
                    "version": {"type": "string", "description": "Specific version to install"},
                    "language": {"type": "string", "description": "Programming language (e.g., 'python')"}
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
                    "name": {"type": "string", "description": "Package name to check"},
                    "language": {"type": "string", "description": "Programming language"}
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
                    "language": {"type": "string", "description": "Programming language (e.g., 'python')"}
                }
            }
        }
    },
}


def get_tools_for_role(allowed_tools: list) -> list:
    """
    Get tool definitions for a specific role.

    Args:
        allowed_tools: List of tool names allowed for this role

    Returns:
        List of tool definitions in OpenAI JSON schema format
    """
    return [TOOL_DEFINITIONS[name] for name in allowed_tools if name in TOOL_DEFINITIONS]


# ---------------------------------------------------------------------------
# Tool descriptions for prompt injection
# ---------------------------------------------------------------------------

def get_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
    """
    Get a formatted description of all available tools for injection into agent prompts.

    Returns:
        Multi-line string describing all tools and their signatures
    """
    description = """
Available tools (call these methods in your implementation):

File Reading:
  - read_file(path: str) -> str: Read file contents
  - get_file_info(path: str) -> dict: Get file metadata (size, type, lines, etc.)

File Writing:
  - write_file(path: str, content: str) -> dict: Create or overwrite file (auto-creates directories)
  - edit_file(path: str, diff: str) -> dict: Apply unified diff to file

Directory Operations:
  - list_directory(path: str, depth: int = -1) -> dict: List directory tree recursively (depth=-1 unlimited, 0 immediate only)
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

Task Completion:
  - confirm_task_complete(summary: str = "", deliverables: list = None) -> dict: Confirm task is complete and provide summary
  - record_audit_success(file_paths: list, summary: str = "") -> dict: Record successful audit of files with timestamp. Task complete when all edited files are audited.

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

Exception types: PathError (invalid path), FileSizeError (>10MB), PackageError (package operations failed), ToolError (general failures).
See docs/agents/AGENT_TOOLS_GUIDE.md for detailed examples and patterns.
""".strip()

    if allowed_tools is not None:
        allowed_line = "Allowed tools for your role: " + ", ".join(allowed_tools)
        return f"{description}\n\n{allowed_line}".strip()

    return description


def get_manager_tools_description(allowed_tools: Optional[List[str]] = None) -> str:
    """
    Get a formatted description of task assignment tools for the manager role.

    Returns:
        Multi-line string describing assignment tools and their usage
    """
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
# ---------------------------------------------------------------------------

class ToolEnvironment:
    """
    Builds and manages the tool execution environment for an agent.

    Responsibilities:
    - Constructs tool name -> callable mapping exactly once.
    - Wraps every callable to capture output and (for developers) track
      produced files via the wrapper rather than regex after the fact.
    - Tracks audit requests and task-completion signals.

    This replaces the three copies of ``exec_globals`` that previously existed.
    """

    def __init__(self, agent, working_dir: str = "."):
        allowed_tools = agent.config.get("allowed_tools")
        default_git_branch = agent.config.get("default_git_branch")

        self.tools = AgentTools(working_dir=working_dir)
        self.tool_outputs: List[Dict[str, Any]] = []
        self.files_produced: Set[str] = set()
        self.audit_requests: List[Dict[str, Any]] = []
        self.task_complete: bool = False
        self.total_calls: int = 0
        
        # Initialize audit log manager for tracking edits and audits
        self.audit_log_manager = AuditLogManager(working_dir=working_dir)

        self._agent = agent
        self._bindings: Dict[str, Any] = {}
        self._build_bindings(agent, allowed_tools, default_git_branch, working_dir)

    # -- public API ----------------------------------------------------------

    def get_bindings(self) -> Dict[str, Any]:
        """Return the tool-name -> callable mapping (same dict every time)."""
        return self._bindings

    # -- private construction ------------------------------------------------

    def _is_allowed(self, tool_name: str, allowed_tools) -> bool:
        return allowed_tools is None or tool_name in (allowed_tools or [])

    def _build_bindings(self, agent, allowed_tools, default_git_branch, working_dir):
        """Build the complete name -> callable mapping."""
        b = self._bindings
        tools = self.tools
        is_developer = agent.role == "developer"

        # ---- Core file tools (always wrapped for output capture) -----------
        CORE_TOOLS = {
            "read_file":      (tools.read_file,      False),
            "write_file":     (tools.write_file,     False),
            "edit_file":      (tools.edit_file,      False),
            "list_directory": (tools.list_directory, True),
            "list_all_files": (tools.list_all_files, True),
            "search_files":   (tools.search_files,   True),
            "get_file_info":  (tools.get_file_info,  True),
            "delete_file":    (tools.delete_file,    False),
        }

        WRITE_TOOLS = {"write_file", "edit_file", "delete_file"}

        for name, (func, supports_page) in CORE_TOOLS.items():
            track_file = is_developer and name in WRITE_TOOLS
            b[name] = self._wrap(name, func, supports_page=supports_page,
                                 track_file=track_file)

        # ---- Suppress print ------------------------------------------------
        b["print"] = lambda *a, **kw: None

        # ---- clone_repo (with default branch injection) --------------------
        if self._is_allowed("clone_repo", allowed_tools):
            def _clone(repo_url, dest_dir=None, branch=None, depth=None):
                effective_branch = branch or default_git_branch
                return tools.clone_repo(repo_url, dest_dir=dest_dir,
                                        branch=effective_branch, depth=depth)
            b["clone_repo"] = self._wrap("clone_repo", _clone)
        else:
            b["clone_repo"] = self._blocked("clone_repo")

        # ---- run_python ----------------------------------------------------
        if self._is_allowed("run_python", allowed_tools):
            b["run_python"] = self._wrap(
                "run_python", tools.run_python, supports_page=True)
        else:
            b["run_python"] = self._blocked("run_python")

        # ---- checkout_branch -----------------------------------------------
        if self._is_allowed("checkout_branch", allowed_tools):
            b["checkout_branch"] = self._wrap("checkout_branch",
                                              tools.checkout_branch)
        else:
            b["checkout_branch"] = self._blocked("checkout_branch")

        # ---- raise_callback ------------------------------------------------
        if self._is_allowed("raise_callback", allowed_tools):
            from main.agent.callbacks import raise_callback
            b["raise_callback"] = self._wrap(
                "raise_callback",
                lambda message, callback_type="query": raise_callback(
                    agent, message, callback_type),
            )
        else:
            b["raise_callback"] = self._blocked("raise_callback")

        # ---- audit_files ---------------------------------------------------
        if is_developer:
            def _audit_dev(file_paths, description="", focus_areas=None):
                if focus_areas is None:
                    focus_areas = []
                # Validate only produced files can be audited
                unproduced = [f for f in file_paths if f not in self.files_produced]
                if unproduced:
                    raise ToolError(
                        f"Cannot audit files that haven't been produced: {unproduced}. "
                        "Only audit files you created/modified with write_file or edit_file."
                    )
                # Validate files exist
                validated = []
                for fp in file_paths:
                    try:
                        abs_path = tools._validate_path(fp)
                        if os.path.isfile(abs_path):
                            validated.append(fp)
                        else:
                            logger.warning(f"File not found for audit: {fp}")
                    except Exception as e:
                        logger.warning(f"Invalid path for audit: {fp} - {e}")
                result = {
                    "status": "audit_requested",
                    "audit_type": "file_review",
                    "files": validated,
                    "invalid_files": [f for f in file_paths if f not in validated],
                    "description": description,
                    "focus_areas": focus_areas,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.audit_requests.append({
                    "files": file_paths,
                    "description": description,
                    "focus_areas": focus_areas,
                })
                return result
            b["audit_files"] = self._wrap("audit_files", _audit_dev,
                                          supports_page=True)
        else:
            def _audit_basic(file_paths, description="", focus_areas=None):
                if focus_areas is None:
                    focus_areas = []
                validated = []
                for fp in file_paths:
                    try:
                        abs_path = tools._validate_path(fp)
                        if os.path.isfile(abs_path):
                            validated.append(fp)
                    except Exception:
                        pass
                return {
                    "status": "audit_requested",
                    "audit_type": "file_review",
                    "files": validated,
                    "invalid_files": [f for f in file_paths if f not in validated],
                    "description": description,
                    "focus_areas": focus_areas,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            b["audit_files"] = self._wrap("audit_files", _audit_basic,
                                          supports_page=True)

        # ---- confirm_task_complete -----------------------------------------
        def _confirm(summary="", deliverables=None):
            if deliverables is None:
                deliverables = []
            self.task_complete = True
            return {
                "status": "complete",
                "task_complete": True,
                "summary": summary,
                "deliverables": deliverables,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        b["confirm_task_complete"] = self._wrap(
            "confirm_task_complete", _confirm)

        # ---- record_audit_success ------------------------------------------
        def _record_audit(file_paths, summary=""):
            """Record successful audit of files."""
            # Record audit in the audit log manager
            self.audit_log_manager.record_audit(file_paths)
            
            # Check if task is complete
            task_complete = self.audit_log_manager.is_task_complete()
            unaudited = self.audit_log_manager.get_unaudited_files()
            
            result = {
                "status": "audit_recorded",
                "audited_files": file_paths,
                "summary": summary,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "task_complete": task_complete,
            }
            
            if task_complete:
                self.task_complete = True
                result["message"] = "All edited files have been audited. Task is complete."
            else:
                result["message"] = f"Audit recorded. {len(unaudited)} file(s) still need auditing: {', '.join(unaudited)}"
                result["unaudited_files"] = unaudited
                result["action_required"] = f"Please audit the following files: {', '.join(unaudited)}"
            
            return result

        b["record_audit_success"] = self._wrap(
            "record_audit_success", _record_audit)


    # -- wrapper helpers -----------------------------------------------------

    def _wrap(self, name: str, func, *, supports_page: bool = False,
              track_file: bool = False):
        """Return a wrapper that captures output and optionally tracks files."""
        env = self  # closure ref

        def wrapper(*args, **kwargs):
            page = None
            if supports_page and isinstance(kwargs, dict):
                page = kwargs.pop("page", None)
            result = func(*args, **kwargs)
            env.total_calls += 1

            # Track file produced (path can be positional or keyword)
            if track_file:
                path = kwargs.get("path") if kwargs and "path" in kwargs else (args[0] if args else None)
                if path:
                    env.files_produced.add(path)
                    # Also record edit in audit log manager
                    env.audit_log_manager.record_edit(path)

            # Capture output
            page_index = page if isinstance(page, int) and page > 0 else 1
            entry = _format_tool_output(name, args, kwargs, result, page_index)
            if entry:
                env.tool_outputs.append(entry)
            return result

        return wrapper

    @staticmethod
    def _blocked(tool_name: str):
        """Return a callable that raises ToolError for disallowed tools."""
        def _raise(*_a, **_kw):
            raise ToolError(f"Tool not allowed for this role: {tool_name}")
        return _raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def execute_tools_from_response(
    agent,
    response: str,
    working_dir: str = ".",
    message: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract and execute tool calls from an agent's response.

    Looks for (in order of precedence):
    1. Structured ``tool_calls`` in *message*
    2. Python code blocks (```python ... ```)
    3. Inline plain-text function calls

    Returns a dict compatible with all existing callers.
    """
    # Parse inputs
    code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
    structured_tool_calls: list = []
    if isinstance(message, dict):
        structured_tool_calls = message.get("tool_calls", []) or []

    allowed_tools = agent.config.get("allowed_tools")
    inline_calls: List[Tuple[str, list, dict]] = []
    if not code_blocks and not structured_tool_calls:
        inline_calls = _extract_inline_calls(response, allowed_tools)
        if not inline_calls:
            logger.debug(f"No tool calls found in response from {agent.name}")
            return {
                "tools_executed": False,
                "message": "No tool calls found in response",
            }

    # Build environment once
    env = ToolEnvironment(agent, working_dir)
    bindings = env.get_bindings()
    results: List[Dict[str, Any]] = []

    # --- Execute code blocks ------------------------------------------------
    for code_block in code_blocks:
        try:
            exec(code_block, bindings, {})
            results.append({"success": True, "code_executed": len(code_block)})
            logger.info(f"Agent {agent.name} executed tools successfully")
        except Exception as e:
            logger.error(f"Tool execution failed for {agent.name}: {e}")
            results.append({
                "success": False,
                "error": str(e),
                "code": code_block[:200],
            })

    # --- Execute structured tool_calls --------------------------------------
    for tc in structured_tool_calls:
        if tc.get("type") != "function":
            continue
        func = tc.get("function", {})
        func_name = func.get("name")
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}

        if not func_name or func_name not in bindings:
            results.append({"success": False, "tool": func_name,
                            "error": f"Unknown tool: {func_name}"})
            continue

        try:
            bindings[func_name](**(args or {}))
            results.append({"success": True, "tool": func_name})
            logger.info(f"Agent {agent.name} executed tool call: {func_name}")
        except Exception as e:
            logger.error(f"Tool execution failed for {agent.name}: {e}")
            results.append({"success": False, "tool": func_name,
                            "error": str(e)})

    # --- Execute inline calls (fallback) ------------------------------------
    if not code_blocks and not structured_tool_calls:
        for func_name, i_args, i_kwargs in inline_calls:
            if func_name not in bindings:
                results.append({"success": False, "tool": func_name,
                                "error": f"Unknown tool: {func_name}"})
                continue
            try:
                bindings[func_name](*i_args, **i_kwargs)
                results.append({"success": True, "tool": func_name})
                logger.info(
                    f"Agent {agent.name} executed inline tool call: {func_name}")
            except Exception as e:
                logger.error(
                    f"Inline tool execution failed for {agent.name}: {e}")
                results.append({"success": False, "tool": func_name,
                                "error": str(e)})

    # --- Build result dict --------------------------------------------------
    result_dict: Dict[str, Any] = {
        "tools_executed": True,
        "code_blocks_found": len(code_blocks),
        "code_blocks_executed": len([r for r in results if r.get("success")]),
        "estimated_tool_calls": env.total_calls,
        "results": results,
        "task_complete": env.task_complete,
        "tool_outputs": env.tool_outputs,
    }

    if agent.role == "developer":
        result_dict["files_produced"] = list(env.files_produced)
        result_dict["audit_requests"] = env.audit_requests
        if env.audit_requests and not env.files_produced:
            logger.warning(
                f"Developer {agent.name} requested audits but produced no files")

    return result_dict


# ---------------------------------------------------------------------------
# Helpers (unchanged public interface for imports)
# ---------------------------------------------------------------------------

def _capture_output_wrapper(
    tool_outputs: List[Dict[str, Any]],
    tool_name: str,
    func,
    supports_page: bool = False,
):
    """Legacy wrapper – kept for any external callers."""
    def wrapper(*args, **kwargs):
        page = None
        if supports_page and isinstance(kwargs, dict):
            page = kwargs.pop("page", None)
        result = func(*args, **kwargs)
        page_index = page if isinstance(page, int) and page > 0 else 1
        output_entry = _format_tool_output(tool_name, args, kwargs, result,
                                           page_index)
        if output_entry:
            tool_outputs.append(output_entry)
        return result
    return wrapper


def _format_tool_output(
    tool_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    result: Any,
    page_index: int,
) -> Optional[Dict[str, Any]]:
    text = _stringify_tool_output(result)
    if text is None:
        return None
    page_text, total_pages = _paginate_text(text, page_index, DEFAULT_PAGE_LINES)
    return {
        "tool": tool_name,
        "args": list(args),
        "kwargs": kwargs,
        "page": page_index,
        "total_pages": total_pages,
        "page_lines": DEFAULT_PAGE_LINES,
        "content": page_text,
    }


def _stringify_tool_output(result: Any) -> Optional[str]:
    if result is None:
        return None
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, indent=2, ensure_ascii=True)
    except (TypeError, ValueError):
        return str(result)


def _paginate_text(text: str, page: int, lines_per_page: int) -> Tuple[str, int]:
    lines = text.splitlines()
    if not lines:
        return "", 1
    total_pages = max(1, (len(lines) + lines_per_page - 1) // lines_per_page)
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * lines_per_page
    end = start + lines_per_page
    return "\n".join(lines[start:end]), total_pages


def _extract_inline_calls(
    response: str, allowed_tools: Optional[list],
) -> List[Tuple[str, List[Any], Dict[str, Any]]]:
    allowed_names = set(allowed_tools or [])
    calls: List[Tuple[str, list, dict]] = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        if not allowed_names or any(
            line.startswith(f"{name}(") for name in allowed_names
        ):
            try:
                node = ast.parse(line, mode="eval")
            except SyntaxError:
                continue
            call = node.body
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                func_name = call.func.id
                if allowed_names and func_name not in allowed_names:
                    continue
                args: list = []
                kwargs: dict = {}
                try:
                    for arg in call.args:
                        args.append(ast.literal_eval(arg))
                    for kw in call.keywords:
                        if kw.arg:
                            kwargs[kw.arg] = ast.literal_eval(kw.value)
                except (ValueError, SyntaxError):
                    continue
                calls.append((func_name, args, kwargs))
    return calls
