# Long-running AI development task for Windows
# Demonstrates multi-agent collaboration on building a machine learning system

$ErrorActionPreference = "Stop"

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Run the Python implementation
python.exe run_long_task_impl.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Task failed with exit code: $LASTEXITCODE"
    exit $LASTEXITCODE
}
