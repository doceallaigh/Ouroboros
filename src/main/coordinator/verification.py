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
        "task": f"""Perform a COMPREHENSIVE FINAL VERIFICATION of the entire solution.

ORIGINAL REQUEST:
{user_request[:1000]}

VERIFICATION CHECKLIST:
1. List all deliverables mentioned in the requirements
2. Check if each deliverable file exists in the workspace
3. Verify the quality and completeness of each deliverable
4. Check for integration issues between components
5. Validate that the solution meets ALL original requirements
6. Report on overall solution readiness (PASS/FAIL with justification)

CRITICAL: You MUST use the provided tools to:
- List all files in the current directory and subdirectories
- Read key files to verify their implementation
- Check for any missing or incomplete components

EXPECTED DELIVERABLES:
Look for files matching these patterns and verify their presence and quality:
- requirements.txt (or similar dependency file)
- Python modules/scripts (.py files)
- Documentation (README.md or similar)
- Test files
- Any model files or data artifacts mentioned
{blocker_summary}

REPORT FORMAT:
Provide a clear, structured report with:
1. Deliverables Status (list each with PRESENT/MISSING or COMPLETE/INCOMPLETE)
2. Quality Assessment (code quality, documentation, error handling)
3. Integration Status (all components work together)
4. Overall Result: PASS (solution ready) or FAIL (issues remain)
5. Recommendations (what needs to be fixed if FAIL)

If any critical deliverables are missing or incomplete, report this as a BLOCKER callback.""",
        "sequence": 99,  # Very high sequence to run after everything else
    }
    
    return final_verification_task
