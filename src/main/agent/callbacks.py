"""
Callback handling for agents.

Allows agents to communicate with their callers for clarifications, blockers, etc.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def raise_callback(agent, message: str, callback_type: str = "query") -> Optional[str]:
    """
    Raise a callback to the calling agent (e.g., request clarification, report blocker).
    
    Args:
        agent: Agent instance
        message: The message/query to send to the caller
        callback_type: Type of callback ('query', 'blocker', 'clarification', 'error')
    
    Returns:
        Response from caller if available, None otherwise
    """
    if not agent.callback_handler:
        logger.warning(f"Agent {agent.name} attempted callback but no handler set")
        return None
    
    logger.info(f"Agent {agent.name} raising {callback_type} callback: {message[:100]}")
    
    try:
        response = agent.callback_handler(agent.name, message, callback_type)
        logger.info(f"Callback response received for {agent.name}")
        return response
    except Exception as e:
        logger.error(f"Callback failed for {agent.name}: {e}")
        return None
