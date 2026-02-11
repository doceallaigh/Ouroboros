"""
Callback handling for coordinator.

Manages callbacks from agents (queries, blockers, etc).
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def get_blocker_callbacks(coordinator) -> List[Dict[str, Any]]:
    """
    Get all blocker callbacks from the callback list.
    
    Args:
        coordinator: CentralCoordinator instance
    
    Returns:
        List of blocker callbacks
    """
    return [cb for cb in coordinator.callbacks if cb.get("type") == "blocker"]


def clear_blocker_callbacks(coordinator) -> None:
    """
    Clear all blocker callbacks from the callback list.
    
    Args:
        coordinator: CentralCoordinator instance
    """
    coordinator.callbacks = [cb for cb in coordinator.callbacks if cb.get("type") != "blocker"]
