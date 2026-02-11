"""
Coordinator module - multi-agent orchestration and task decomposition.

This module provides the CentralCoordinator class that:
1. Decomposes user requests into atomic tasks
2. Assigns tasks to agents based on role requirements
3. Tracks task execution and handles blockers
4. Verifies solution completeness with final auditor verification
"""

from main.coordinator.coordinator import CentralCoordinator
from main.coordinator.decomposer import decompose_request
from main.coordinator.validator import validate_assignment_roles
from main.agent.agent_factory import (
    find_agent_config,
    create_agent_for_role,
)
from main.coordinator.orchestrator import execute_all_assignments
from main.coordinator.execution import execute_single_assignment
from main.coordinator.verification import create_final_verification_task
from main.coordinator.callbacks import (
    get_blocker_callbacks,
    clear_blocker_callbacks,
)


def inject_coordinator_methods():
    """
    Inject decomposer methods into CentralCoordinator class.
    
    These are core methods that should be on the coordinator instance but are
    logically organized in separate modules for clarity.
    """
    # Decomposer methods
    CentralCoordinator.decompose_request = decompose_request
    CentralCoordinator.validate_assignment_roles = validate_assignment_roles
    
    # Agent factory methods - wrap to pass coordinator state to decoupled functions
    def find_agent_config_wrapper(self, role):
        return find_agent_config(self.config, role)
    
    def create_agent_for_role_wrapper(self, role):
        return create_agent_for_role(
            self.config,
            role,
            self.channel_factory,
            self.filesystem,
            self.role_instance_counts,
            self.allow_git_tools,
            self.post_processor
        )
    
    CentralCoordinator.find_agent_config = find_agent_config_wrapper
    CentralCoordinator.create_agent_for_role = create_agent_for_role_wrapper
    
    # Orchestrator method
    CentralCoordinator.execute_all_assignments = execute_all_assignments
    
    # Execution method
    CentralCoordinator.execute_single_assignment = execute_single_assignment
    
    # Verification method
    CentralCoordinator.create_final_verification_task = create_final_verification_task


# Inject methods on module import
inject_coordinator_methods()

__all__ = [
    "CentralCoordinator",
    "decompose_request",
    "validate_assignment_roles",
    "find_agent_config",
    "create_agent_for_role",
    "execute_all_assignments",
    "execute_single_assignment",
    "create_final_verification_task",
    "get_blocker_callbacks",
    "clear_blocker_callbacks",
]
