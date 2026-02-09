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
from typing import List, Dict, Any, Optional
from pathlib import Path

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
    
    def edit_file(self, path: str, old_text: str, new_text: str, 
                  encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Edit file by replacing text.
        
        Args:
            path: File path (relative to working_dir)
            old_text: Text to find and replace
            new_text: Replacement text
            encoding: Text encoding (default: utf-8)
            
        Returns:
            Dictionary with path, replacements count, and result
            
        Raises:
            PathError: If path is invalid
            ToolError: If edit fails
        """
        try:
            file_path = self._validate_path(path)
            
            if not os.path.isfile(file_path):
                raise ToolError(f"Not a file: {path}")
            
            # Read file
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            # Count replacements
            replacements = content.count(old_text)
            
            if replacements == 0:
                logger.warning(f"No matches found in {path} for edit")
                return {
                    "path": path,
                    "replacements": 0,
                    "success": False,
                    "message": "Text not found",
                }
            
            # Perform replacement
            new_content = content.replace(old_text, new_text)
            
            # Write back
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(new_content)
            
            logger.info(f"Edited file: {path} ({replacements} replacements)")
            
            return {
                "path": path,
                "replacements": replacements,
                "success": True,
            }
        
        except PathError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to edit file {path}: {e}")
    
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
        import re
        if not re.match(r'^[\w\-\.]+$', name):
            return False
        
        return True


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


def get_tools_description() -> str:
    """
    Get a formatted description of all available tools for injection into agent prompts.
    
    Returns:
        Multi-line string describing all tools and their signatures
    """
    return """
Available tools (call these methods in your implementation):

File Reading:
  - read_file(path: str) -> str: Read file contents
  - get_file_info(path: str) -> dict: Get file metadata (size, type, lines, etc.)

File Writing:
  - write_file(path: str, content: str) -> dict: Create or overwrite file (auto-creates directories)
  - append_file(path: str, content: str) -> dict: Append to file or create if missing
  - edit_file(path: str, old_text: str, new_text: str) -> dict: Replace text in file

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

Supported Languages:
  - "python" (uses PyPI and pip)
  - "javascript" or "node" (uses npm registry)

Security:
- All paths must be relative to the working directory (no absolute paths or ../)
- Package names are validated to prevent injection attacks
- Installation has a 120 second timeout
- Only alphanumeric, hyphens, underscores, and dots allowed in package names

Exception types: PathError (invalid path), FileSizeError (>10MB), PackageError (package operations failed), ToolError (general failures).
See agent_tools_guide.md for detailed examples and patterns.
""".strip()


def get_manager_tools_description() -> str:
    """
    Get a formatted description of task assignment tools for the manager role.
    
    Returns:
        Multi-line string describing assignment tools and their usage
    """
    return """
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
