"""
Request decomposition into agent tasks.

Uses manager agents to break down user requests and extract assignments.
"""

import json
import logging
import re
import time
from typing import Dict, List, Any, Optional

from main.agent.agent_factory import create_agent_for_role
from main.exceptions import OrganizationError

logger = logging.getLogger(__name__)


def extract_assignments_from_tool_calls(response: str) -> Optional[List[Dict[str, Any]]]:
    """
    Extract task assignments from manager's tool calls in response.
    
    Looks for assign_task() and assign_tasks() calls in the manager's response.
    
    Args:
        response: Manager's response text
        
    Returns:
        List of extracted assignments, or None if no tool calls found
    """
    assignments = []
    
    # Look for assign_task calls: assign_task('role', 'task', sequence=N)
    assign_task_pattern = r"assign_task\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*?)['\"]\s*,\s*sequence\s*=\s*(\d+)"
    for match in re.finditer(assign_task_pattern, response, re.DOTALL):
        role, task, sequence = match.groups()
        task = task.replace('\\n', '\n')  # Unescape newlines
        assignments.append({
            "role": role.strip(),
            "task": task.strip(),
            "sequence": int(sequence),
            "caller": "manager"
        })
    
    # Look for assign_tasks calls with array/list structure
    # This is more complex - look for assign_tasks([ ... ])
    assign_tasks_pattern = r"assign_tasks\s*\(\s*\[\s*(.*?)\s*\]\s*\)"
    for match in re.finditer(assign_tasks_pattern, response, re.DOTALL):
        tasks_str = match.group(1)
        
        # Extract individual task objects from the array
        # Look for {role: ..., task: ..., sequence: ...} patterns
        task_obj_pattern = r"\{\s*['\"]?role['\"]?\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?task['\"]?\s*:\s*['\"]([^'\"]*?)['\"]\s*,\s*['\"]?sequence['\"]?\s*:\s*(\d+)"
        for task_match in re.finditer(task_obj_pattern, tasks_str, re.DOTALL):
            role, task, sequence = task_match.groups()
            task = task.replace('\\n', '\n')  # Unescape newlines
            assignments.append({
                "role": role.strip(),
                "task": task.strip(),
                "sequence": int(sequence),
                "caller": "manager"
            })
    
    return assignments if assignments else None


def decompose_request(coordinator, user_request: str) -> str:
    """
    Use a manager agent to decompose a request into tasks.
    
    Now supports both tool-based assignments and legacy JSON format.
    Validates that assigned roles exist. If manager assigns to invalid roles,
    retries with corrective feedback.
    
    Args:
        coordinator: CentralCoordinator instance
        user_request: User's high-level request
        
    Returns:
        Decomposed tasks as JSON string
        
    Raises:
        OrganizationError: If decomposition fails after retries
    """
    from main.coordinator.validator import validate_assignment_roles
    
    max_retries = 2
    backoff_delay = 1.0
    
    # Create manager once outside the retry loop to avoid duplicate agents
    manager = create_agent_for_role(coordinator, "manager")
    
    for attempt in range(max_retries):
        try:
            decomposition = manager.execute_task({
                "user_prompt": user_request,
            })
            
            # Try to extract assignments from tool calls first
            assignments = extract_assignments_from_tool_calls(decomposition)
            
            if assignments is None:
                # Fall back to JSON parsing for legacy format
                try:
                    parsed = json.loads(decomposition)
                    if isinstance(parsed, list):
                        assignments = parsed
                    elif isinstance(parsed, dict) and "tasks" in parsed:
                        assignments = parsed.get("tasks", [])
                except json.JSONDecodeError:
                    pass
            
            if assignments is None:
                # No assignments found in either format
                json_parse_error = "No task assignments found (neither tool calls nor valid JSON)"
                # Retry with corrective feedback
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Manager response contained no task assignments. "
                        f"Retrying with corrective feedback..."
                    )
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    
                    # Add feedback about using tools
                    corrective_request = (
                        f"{user_request}\n\n"
                        f"[IMPORTANT: Use the task assignment tools to assign tasks. "
                        f"Call assign_task() or assign_tasks() with 'developer' or 'auditor' roles.]"
                    )
                    user_request = corrective_request
                    continue
                else:
                    error_msg = f"Manager failed to assign tasks after {max_retries} attempts. {json_parse_error}"
                    logger.error(error_msg)
                    raise OrganizationError(error_msg)
            
            # Validate assigned roles
            invalid_roles = validate_assignment_roles(coordinator, assignments)
            
            if invalid_roles:
                # Roles are invalid, record event and retry with feedback
                if attempt < max_retries - 1:
                    coordinator.filesystem.record_event(
                        coordinator.filesystem.EVENT_ROLE_VALIDATION_FAILED,
                        {
                            "attempt": attempt + 1,
                            "invalid_roles": invalid_roles,
                            "user_request": user_request[:200],  # Truncate for log
                        }
                    )
                    
                    logger.warning(
                        f"Manager assigned to invalid roles: {invalid_roles}. "
                        f"Retrying with corrective feedback..."
                    )
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    
                    # Create corrective prompt
                    valid_roles = list(coordinator.config.keys())
                    corrective_request = (
                        f"{user_request}\n\n"
                        f"[SYSTEM CONSTRAINT: You must ONLY assign tasks to these roles: {valid_roles}]"
                    )
                    user_request = corrective_request
                    
                    # Record retry event
                    coordinator.filesystem.record_event(
                        coordinator.filesystem.EVENT_ROLE_RETRY,
                        {
                            "attempt": attempt + 1,
                            "valid_roles": valid_roles,
                        }
                    )
                    continue
                else:
                    error_msg = f"Manager failed to assign valid roles after {max_retries} attempts. Invalid roles: {invalid_roles}"
                    logger.error(error_msg)
                    raise OrganizationError(error_msg)
            
            # Record successful decomposition event and convert to JSON for return
            coordinator.filesystem.record_event(
                coordinator.filesystem.EVENT_REQUEST_DECOMPOSED,
                {
                    "attempt": attempt + 1,
                    "num_assignments": len(assignments) if isinstance(assignments, list) else 0,
                }
            )
            
            # Convert assignments back to JSON string for compatibility
            logger.debug(f"Request decomposed into {len(assignments)} assignments")
            return json.dumps(assignments)
        
        except Exception as e:
            error_msg = f"Failed to decompose request: {e}"
            logger.error(error_msg)
            raise OrganizationError(error_msg)
    
    raise OrganizationError("Decomposition failed after maximum retries")
