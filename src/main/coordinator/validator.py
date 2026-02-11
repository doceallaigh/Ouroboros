"""
Role validation for coordinator assignments.

Ensures that task assignments are only for valid agent roles.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def validate_assignment_roles(coordinator, assignments: List[Dict[str, Any]]) -> List[str]:
    """
    Validate that all assigned roles exist in the configuration.
    
    Args:
        coordinator: CentralCoordinator instance
        assignments: List of task assignments
        
    Returns:
        List of invalid role names, empty if all valid
    """
    valid_roles = set(coordinator.config.keys())
    invalid_roles = []
    
    for assignment in assignments:
        if isinstance(assignment, dict):
            role = assignment.get("role")
            if role and role not in valid_roles:
                invalid_roles.append(role)
    
    return invalid_roles
