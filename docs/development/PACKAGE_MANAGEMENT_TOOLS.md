# Package Management Tools

## Overview
Added comprehensive package management tools to allow agents to search for and install dependencies during task execution. Supports Python (pip/PyPI) and JavaScript (npm/npm registry).

## Features

### 1. **Search Packages** (`search_package`)
Search for available packages in repositories.

**Usage:**
```python
# Search for a Python package
result = search_package("requests", language="python")

# Search for an npm package
result = search_package("express", language="javascript")
```

**Returns:**
- Package name, version, summary/description
- Available versions (last 10)
- Home page, author, license (where available)
- `found: bool` indicates if package exists

### 2. **Install Packages** (`install_package`)
Install a package with optional version specification.

**Usage:**
```python
# Install latest version
result = install_package("requests", language="python")

# Install specific version
result = install_package("numpy", version="1.21.0", language="python")

# Install version range
result = install_package("pandas", version=">=1.0.0", language="python")

# Install npm package
result = install_package("express", version="4.17.1", language="javascript")
```

**Returns:**
- Installation success status
- Installed version
- Package details

**Security Features:**
- Package names are validated (alphanumeric, hyphens, underscores, dots only)
- Rejects malicious patterns (paths, shell commands, etc.)
- 120-second timeout per installation
- Proper error handling and reporting

### 3. **Check Installation** (`check_package_installed`)
Check if a package is installed and get its version.

**Usage:**
```python
result = check_package_installed("requests", language="python")
# Returns: {installed: bool, installed_version: str, ...}
```

### 4. **List Installed Packages** (`list_installed_packages`)
Get a list of all installed packages for a language.

**Usage:**
```python
result = list_installed_packages(language="python")
# Returns: {packages: [{name: str, version: str}, ...], count: int}

result = list_installed_packages(language="javascript")
```

## Supported Languages

### Python
- Uses PyPI (Python Package Index)
- Installed via `pip`
- Queries `https://pypi.org/pypi/{package}/json`

### JavaScript/Node
- Uses npm registry
- Installed via `npm`
- Queries `https://registry.npmjs.org/{package}`

## Security Considerations

### Package Name Validation
All package names are validated to prevent injection attacks:

❌ Rejected:
- Paths: `../../package`, `/etc/package`
- Shell characters: `;`, `|`, `&`, `` ` ``, `$`
- Wildcards and escapes

✅ Allowed:
- `requests`, `numpy`, `my-package`, `my_package`, `my.package`

### Installation Safety
- Packages are installed with `--quiet` flag to reduce noise
- Installation success is verified after completion
- Timeouts prevent hanging on large installations
- Subprocess output is captured to prevent output pollution

## Example: Dependency Installation Workflow

```python
# 1. Search for a package
search_result = search_package("flask", language="python")
print(f"Found: {search_result['found']}")
print(f"Latest version: {search_result['version']}")

# 2. Install the package
install_result = install_package("flask", version="2.0.0", language="python")
print(f"Installed: {install_result['success']}")

# 3. Verify installation
check_result = check_package_installed("flask", language="python")
print(f"Installed version: {check_result['installed_version']}")

# 4. List all installed packages
all_packages = list_installed_packages(language="python")
print(f"Total packages: {all_packages['count']}")
```

## Error Handling

All package management operations raise `PackageError` on failure:

```python
from agent_tools import PackageError

try:
    install_package("requests", language="python")
except PackageError as e:
    print(f"Installation failed: {e}")
```

Common errors:
- Package not found in repository
- Network timeout (10 seconds for search, 120 for install)
- Installation failure (returned by pip/npm)
- Tool not found (npm not installed for JavaScript packages)

## Tool Integration

The package management tools are automatically available to developer and auditor roles. They appear in the injected tools description:

```
Package Management:
  - search_package(name: str, language: str = "python") -> dict
  - install_package(name: str, version: str = None, language: str = "python") -> dict
  - check_package_installed(name: str, language: str = "python") -> dict
  - list_installed_packages(language: str = "python") -> dict
```

## Tests

All package management functionality is tested in `test_agent_tools.py` with 7 tests covering:

- ✅ Package name validation (valid and invalid cases)
- ✅ Checking installed packages
- ✅ Listing installed packages
- ✅ Error handling for invalid language
- ✅ Security rejection of malicious package names

Run tests with:
```bash
python -m unittest test_agent_tools.TestPackageManagement -v
```

## Future Enhancements

Possible extensions:
- Conda support for Python
- Docker container support
- Requirements file parsing and bulk installation
- Dependency resolution and conflict detection
- Version pinning and lock file support
- Pre-approved package whitelist
- Installation size limits
- Automatic cleanup/uninstall
