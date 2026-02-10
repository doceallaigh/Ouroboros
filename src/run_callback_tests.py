"""
Test execution and reporting for callback and verification tests.

This module provides utilities to run the component tests and generate reports.
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, List, Any


def run_tests(test_file: str = None, verbose: bool = True) -> Dict[str, Any]:
    """
    Run tests and collect results.
    
    Args:
        test_file: Specific test file to run (None for all)
        verbose: Enable verbose output
        
    Returns:
        Test results dictionary
    """
    
    test_files = [
        "src/test_callback_and_verification.py",
        "src/test_callback_routing_and_retry.py"
    ]
    
    if test_file:
        test_files = [test_file]
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "test_files": []
    }
    
    for test_f in test_files:
        print(f"\n{'='*80}")
        print(f"Running: {test_f}")
        print(f"{'='*80}\n")
        
        cmd = [sys.executable, "-m", "pytest", test_f]
        
        if verbose:
            cmd.append("-v")
        
        cmd.extend(["-x", "--tb=short"])  # Stop on first failure
        
        try:
            result = subprocess.run(cmd, capture_output=False)
            results["total"] += 1
            
            if result.returncode == 0:
                results["passed"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            print(f"Error running {test_f}: {e}")
            results["errors"] += 1
    
    return results


def print_summary(results: Dict[str, Any]):
    """Print test summary."""
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    print(f"Total test files: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Errors: {results['errors']}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    print("Component and Integration Test Suite")
    print("Testing: Callback Collection, Verification, and Retry Mechanisms")
    print()
    
    results = run_tests()
    print_summary(results)
    
    sys.exit(0 if results["failed"] == 0 else 1)
