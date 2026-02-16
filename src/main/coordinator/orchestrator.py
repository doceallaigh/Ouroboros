"""
Orchestrator for multi-agent parallel execution with sequencing.

Handles task  assignment scheduling and result aggregation.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any

from main.exceptions import OrganizationError
from main.git import finalize_git_workflow

logger = logging.getLogger(__name__)


def execute_all_assignments(coordinator, assignments: List[Dict[str, Any]], user_request: str) -> List[Dict[str, Any]]:
    """
    Execute assignments respecting sequence ordering.
    
    Tasks with the same sequence number execute in parallel.
    Tasks with different sequence numbers execute sequentially, with
    sequence N+1 starting only after sequence N completes.
    
    Args:
        coordinator: CentralCoordinator instance
        assignments: List of task assignments with 'role', 'task', and optional 'sequence' fields
        user_request: Original user request for context
        
    Returns:
        List of execution results
    """
    results = []
    
    if not assignments:
        logger.warning("No assignments to execute")
        return results
    
    # Group assignments by sequence number
    # Default sequence is 1 if not specified
    sequences: Dict[int, List[Dict[str, Any]]] = {}
    for i, assignment in enumerate(assignments):
        if not assignment.get("role"):
            logger.warning(f"Assignment {i} missing role field")
            continue
        
        sequence = assignment.get("sequence", 1)
        if sequence not in sequences:
            sequences[sequence] = []
        sequences[sequence].append(assignment)
    
    # Execute sequences in order
    for seq_num in sorted(sequences.keys()):
        seq_assignments = sequences[seq_num]
        logger.info(f"Executing sequence {seq_num} ({len(seq_assignments)} assignments)")
        
        # Execute all assignments in this sequence in parallel
        seq_results = []
        with ThreadPoolExecutor(max_workers=len(seq_assignments)) as executor:
            futures = {}
            for assignment in seq_assignments:
                future = executor.submit(
                    coordinator.execute_single_assignment,
                    role=assignment.get("role"),
                    task={"description": assignment.get("task", "")},
                    original_request=user_request,
                )
                futures[future] = assignment
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    seq_results.append(result)
                    logger.info(f"Assignment completed: {result.get('role', '?')}")
                except Exception as e:
                    assignment = futures[future]
                    logger.error(f"Assignment failed for {assignment.get('role')}: {e}")
                    raise OrganizationError(f"Assignment execution failed: {e}")
        
        results.extend(seq_results)
    
    logger.info(f"All assignments completed ({len(results)} total results)")
    return results


def assign_and_execute(coordinator, user_request: str) -> List[Dict[str, Any]]:
    """
    High-level orchestration: decompose request, execute assignments, verify result.
    
    Orchestrates the complete workflow:
    1. Decompose user request into atomic assignments
    2. Validate that assigned roles exist
    3. Execute all assignments respecting sequence ordering
    4. Create and execute final verification task
    5. Return aggregated results
    
    Args:
        coordinator: CentralCoordinator instance
        user_request: User's high-level request
        
    Returns:
        List of execution results including final verification
        
    Raises:
        OrganizationError: If decomposition, execution, or verification fails
    """
    logger.info(f"Starting assign_and_execute for request: {user_request[:100]}")
    
    # Step 1: Decompose request
    decomposition_json = coordinator.decompose_request(user_request)
    
    # Step 2: Parse assignments
    try:
        assignments = json.loads(decomposition_json)
        if not isinstance(assignments, list):
            assignments = []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse decomposition JSON: {e}")
        raise OrganizationError(f"Invalid decomposition format: {e}")
    
    logger.info(f"Decomposed into {len(assignments)} assignments")
    
    # Step 3: Validate roles
    coordinator.validate_assignment_roles(assignments)
    
    # Step 4: Execute assignments
    results = coordinator.execute_all_assignments(assignments, user_request)
    
    # Step 5: Create and execute final verification task
    # Skip if the manager already assigned an auditor — avoid redundant double-audit
    has_auditor_assignment = any(
        a.get("role") == "auditor" for a in assignments
    )
    if has_auditor_assignment:
        logger.info("Manager already assigned an auditor task — skipping redundant final verification")
    else:
        verification_task = coordinator.create_final_verification_task(user_request, results)
        if verification_task:
            verification_result = coordinator.execute_single_assignment(
                role=verification_task.get("role"),
                task={
                    "description": verification_task.get("task"),
                    "task": verification_task.get("task")
                },
                original_request=user_request
            )
            results.append(verification_result)
            logger.info("Final verification completed")
    
    logger.info(f"assign_and_execute complete with {len(results)} results")
    return results

