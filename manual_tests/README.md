# Manual Test Scripts

This directory contains manual test scripts for demonstrating and testing the Ouroboros system.

## Available Scripts

### run_long_task.ps1 (Windows)
PowerShell script for running a long-running AI development task that demonstrates multi-agent collaboration.

**Usage**:
```powershell
.\run_long_task.ps1
```

### run_long_task.sh (Unix/Linux/macOS)
Bash script equivalent for Unix-like systems.

**Usage**:
```bash
./run_long_task.sh
```

### run_long_task_impl.py
Python implementation of the long-running task. Demonstrates:
- Multi-agent collaboration
- Complex task decomposition
- Real-time task execution and monitoring

**Usage**:
```bash
python run_long_task_impl.py
```

## Purpose

These scripts are used for:
- Demonstrating the system's multi-agent capabilities
- Testing complex task execution workflows
- Validating the callback and verification mechanisms
- Manual integration testing

## Notes

- These are manual test scripts, not part of the automated test suite
- They may take several minutes to complete
- Output is written to the shared_repo directory for analysis
