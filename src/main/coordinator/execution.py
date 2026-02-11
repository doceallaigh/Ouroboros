"""
Single assignment executor - executes one task against one agent.

Handles result collection and callback processing.
"""

import json
import logging
from typing import Dict, Any, Optional

from main.exceptions import OrganizationError
from main.agent import Agent

logger = logging.getLogger(__name__)


def execute_single_assignment(
    coordinator,
    role: str,
    task: Dict[str, Any],
    original_request: str
) -> Dict[str, Any]:
    """
    Execute a single task assignment by finding/creating an agent and running the task.
    
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
        
        # Execute task
        logger.info(f"Agent {agent.name} executing task (role: {role})")
        response = agent.execute_task(agent_task)
        
        # Record result
        result = {
            "role": role,
            "agent": agent.name,
            "response": response,
            "source": "execution"
        }
        
        logger.info(f"Agent {agent.name} completed task")
        return result
        
    except Exception as e:
        error_msg = f"Task execution failed for {role}: {str(e)}"
        logger.error(error_msg)
        raise OrganizationError(error_msg)
