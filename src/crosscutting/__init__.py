"""
Crosscutting concerns module.

This module handles ecosystem-wide concerns that span across multiple components,
including event sourcing, logging, and other cross-cutting functionality.
"""

from .event_sourcing import event_sourced

__all__ = ['event_sourced']
