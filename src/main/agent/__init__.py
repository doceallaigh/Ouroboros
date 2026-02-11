"""
Agent package for the Ouroboros system.

Exports the Agent class and related execution functions.
"""

from .agent import Agent
from .executor import execute_task
from .agentic_loop import execute_with_agentic_loop
from .tool_runner import execute_tools_from_response
from .callbacks import raise_callback
from .agent_factory import find_agent_config, create_agent_for_role

# Inject methods into Agent class
Agent.execute_task = execute_task
Agent.execute_with_agentic_loop = execute_with_agentic_loop
Agent.execute_tools_from_response = execute_tools_from_response
Agent.raise_callback = raise_callback

__all__ = [
    "Agent",
    "execute_task",
    "execute_with_agentic_loop",
    "execute_tools_from_response",
    "raise_callback",
    "find_agent_config",
    "create_agent_for_role",
]
