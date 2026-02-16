"""
Single assignment executor - executes one task against one agent.

Handles result collection and callback processing.
"""

import json
import logging
from typing import Dict, Any, Optional

from crosscutting import event_sourced
from main.exceptions import OrganizationError
from main.agent import Agent
from main.agent.agentic_loop import execute_with_agentic_loop

logger = logging.getLogger(__name__)


@event_sourced("task_completed")
def execute_single_assignment(
    coordinator,
    role: str,
    task: Dict[str, Any],
    original_request: str
) -> Dict[str, Any]:
    """
    Execute a single task assignment by finding/creating an agent and running the task.
    
    Uses the agentic loop to execute tools and iterate until task completion.
    
    Args:
        coordinator: CentralCoordinator instance
        role: Role name for this assignment
        task: Task dict with 'description' and optional other fields
        original_request: The original user request for context
        
    Returns:
        Result dict with execution details
        
    Raises:
        OrganizationError: If execution fails
    """
    logger.debug(f"Executing assignment: role={role}")
    
    try:
        # Find or create agent for this role
        agent = coordinator.create_agent_for_role(role)
        
        # Build task for agent
        task_prompt = task.get("description", str(task))
        if len(task_prompt) > 5000:
            task_prompt = task_prompt[:5000] + "..."
        
        agent_task = {
            "user_prompt": f"{task_prompt}\n\nOriginal Request: {original_request[:500]}"
        }
        
        # Replay mode handling
        if coordinator.replay_mode:
            replay_data = coordinator._load_replay_data(agent.name)
            if replay_data:
                logger.info(f"Agent {agent.name} using replay data")
                return {
                    "role": role,
                    "agent": agent.name,
                    "response": replay_data,
                    "source": "replay"
                }
        
        # Get working directory for tool execution
        working_dir = coordinator.filesystem.src_dir
        
        # Scale max iterations by role — auditors need fewer iterations than developers
        role_max_iterations = {
            "auditor": 5,
            "developer": 6,
            "manager": 3,
        }
        max_iter = role_max_iterations.get(role, 10)

        # Execute task using agentic loop (with tool execution)
        logger.info(f"Agent {agent.name} executing task with agentic loop (role: {role}, max_iterations={max_iter})")
        loop_result = execute_with_agentic_loop(
            agent=agent,
            task=agent_task,
            working_dir=working_dir,
            max_iterations=max_iter
        )
        
        # Build result
        result = {
            "role": role,
            "agent": agent.name,
            "response": loop_result.get("final_response", ""),
            "tool_results": loop_result.get("tool_results", []),
            "iteration_count": loop_result.get("iteration_count", 0),
            "task_complete": loop_result.get("task_complete", False),
            "source": "execution"
        }
        
        logger.info(f"Agent {agent.name} completed task")
        return result
        
    except Exception as e:
        error_msg = f"Task execution failed for {role}: {str(e)}"
        logger.error(error_msg)
        raise OrganizationError(error_msg)
