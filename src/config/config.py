"""
Configuration management for Ouroboros.

This module provides utilities for loading and managing application configuration.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load JSON configuration file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigError: If file not found or invalid JSON
    """
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Configuration file not found: {config_path}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in configuration file: {e}")


def get_config_value(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Get configuration value with optional default.
    
    Args:
        config: Configuration dictionary
        key: Configuration key (supports dot notation for nested access)
        default: Default value if key not found
        
    Returns:
        Configuration value or default
    """
    keys = key.split('.')
    value = config
    
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
        
        if value is None:
            return default
    
    return value if value is not None else default


def validate_agent_config(agent_config: Dict[str, str]) -> bool:
    """
    Validate agent configuration has required fields.
    
    Args:
        agent_config: Agent configuration dictionary
        
    Returns:
        True if valid, raises ConfigError otherwise
        
    Raises:
        ConfigError: If required fields missing
    """
    required_fields = ["name", "role", "system_prompt"]
    
    for field in required_fields:
        if field not in agent_config:
            raise ConfigError(f"Agent config missing required field: {field}")
    
    return True
