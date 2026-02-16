"""
Final verification task creation for coordinator.

Creates comprehensive final verification tasks for auditors.
"""

import logging
from typing import Dict, List, Any

from main.coordinator.callbacks import get_blocker_callbacks

logger = logging.getLogger(__name__)


def create_final_verification_task(coordinator, user_request: str, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a final verification task for the auditor.
    
    This task comprehensively verifies that all deliverables have been created
    and that the solution works end-to-end.
    
    Args:
        coordinator: CentralCoordinator instance
        user_request: The original user request
        all_results: All previous task results
        
    Returns:
        Task assignment dict for final verification
    """
    blockers = get_blocker_callbacks(coordinator)
    blocker_summary = ""
    if blockers:
        blocker_summary = f"\n\nPrevious blockers found during development that should be resolved:\n"
        for blocker in blockers:
            blocker_summary += f"- {blocker['message'][:150]}\n"
    
    final_verification_task = {
        "role": "auditor",
        "task": f"""Verify the solution for the following request:

ORIGINAL REQUEST:
{user_request[:500]}

Be EFFICIENT — only check what was actually requested. Do NOT look for files that were never part of the request (e.g. don't search for requirements.txt, README.md, or test files unless they were explicitly requested).
{blocker_summary}
Steps:
1. list_all_files('.') to see what was created
2. read_file() on the key deliverable(s)
3. run_python() to verify it works (if applicable)
4. Call confirm_task_complete() with your PASS/FAIL verdict

Do this in as few steps as possible. Once you can determine PASS or FAIL, call confirm_task_complete() immediately.""",
        "sequence": 99,  # Very high sequence to run after everything else
    }
    
    return final_verification_task
