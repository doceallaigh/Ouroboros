"""
Agent factory for creating agent instances.

Handles agent configuration lookup and instantiation with proper tool permissions.
"""

import logging
from typing import Dict, Optional, Any

from main.agent import Agent
from main.exceptions import OrganizationError
from main.git import is_git_repository
from main.agent.tool_runner import TOOL_DEFINITIONS
from fileio import FileSystem
from comms import ChannelFactory, OutputPostProcessingStrategy

logger = logging.getLogger(__name__)


def find_agent_config(config: Dict[str, Any], role: str) -> Optional[Dict[str, str]]:
    """
    Find configuration for a specific role.
    
    Args:
        config: Agent configuration dict
        role: Role name to find
        
    Returns:
        First matching agent config, or None
    """
    for agent_config in config.values():
        if agent_config.get("role") == role:
            return agent_config
    return None


def create_agent_for_role(
    config: Dict[str, Any],
    role: str,
    channel_factory: ChannelFactory,
    filesystem: FileSystem,
    role_instance_counts: Dict[str, int],
    allow_git_tools: bool = True,
    post_processor: Optional[OutputPostProcessingStrategy] = None,
) -> Agent:
    """
    Create an agent instance for a specific role.
    
    Tracks instance counts to generate unique agent names.
    
    Args:
        config: Agent configuration dict
        role: Role name
        channel_factory: Channel factory for creating communication channels
        filesystem: Filesystem for data storage
        role_instance_counts: Dict tracking instance counts per role
        allow_git_tools: Whether git tools are enabled
        post_processor: Optional post-processing strategy for responses
        
    Returns:
        Agent instance
        
    Raises:
        OrganizationError: If no agent found for role
    """
    agent_config = find_agent_config(config, role)
    if not agent_config:
        raise OrganizationError(f"No agent configured for role: {role}")

    config_copy = dict(agent_config)
    if not allow_git_tools:
        git_tools = {"clone_repo", "checkout_branch"}
        allowed_tools = config_copy.get("allowed_tools")
        if allowed_tools is None:
            allowed_tools = [tool for tool in TOOL_DEFINITIONS if tool not in git_tools]
        else:
            allowed_tools = [tool for tool in allowed_tools if tool not in git_tools]
        config_copy["allowed_tools"] = allowed_tools
    
    # If creating a manager in a git repository, append branch management instruction
    if role == "manager" and is_git_repository(filesystem):
        original_prompt = config_copy.get("system_prompt", "")
        branch_instruction = (
            "\n\nBRANCH MANAGEMENT: You are working in a git repository. "
            "You MUST checkout a new branch using checkout_branch() BEFORE assigning any tasks. "
            "Use a short, descriptive branch name following snake_case convention "
            "(e.g., 'add_auth_module', 'fix_logging_bug', 'refactor_config'). "
            "This prevents conflicts between developers and auditors working on different tasks."
        )
        config_copy["system_prompt"] = f"{original_prompt}{branch_instruction}"
    
    # Increment instance count for this role
    if role not in role_instance_counts:
        role_instance_counts[role] = 0
    role_instance_counts[role] += 1
    
    return Agent(
        config_copy,
        channel_factory,
        filesystem,
        instance_number=role_instance_counts[role],
        post_processor=post_processor
    )
