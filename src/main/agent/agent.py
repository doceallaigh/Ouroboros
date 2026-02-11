"""
Core Agent class for the Ouroboros system.

Represents an agent with a specific role that can execute tasks.
"""

import logging
from typing import Dict, Any, Optional

from comms import ChannelFactory, OutputPostProcessingStrategy
from fileio import FileSystem
from tools import get_tools_description

logger = logging.getLogger(__name__)


class Agent:
    """
    Represents an agent that can execute tasks.
    
    An agent has a specific role and system prompt that guide its behavior.
    It communicates through a channel and stores results in the filesystem.
    """
    
    # Retry configuration constants
    MAX_RETRIES = 3
    INITIAL_TIMEOUT_MULTIPLIER = 1.5  # Multiply timeout by this for each retry
    BACKOFF_MULTIPLIER = 2.0  # Exponential backoff multiplier
    
    def __init__(
        self,
        config: Dict[str, str],
        channel_factory: ChannelFactory,
        filesystem: FileSystem,
        instance_number: int = 1,
        post_processor: Optional[OutputPostProcessingStrategy] = None,
    ):
        """
        Initialize an agent.
        
        Args:
            config: Agent configuration dict with role, system_prompt, etc.
            channel_factory: Factory for creating communication channels
            filesystem: Filesystem for storing outputs
            instance_number: Instance number for this role (1-based, formatted as 01, 02, etc.)
            post_processor: Optional post-processing strategy for responses
            
        Raises:
            OrganizationError: If agent initialization fails
        """
        from main.exceptions import OrganizationError
        
        self.config = config.copy()  # Copy to avoid modifying original
        self.role = self.config.get("role", "unknown")
        # Generate name from role and instance number
        self.name = f"{self.role}{instance_number:02d}"
        self.filesystem = filesystem
        self.callback_handler = None  # Will be set by coordinator if callbacks are needed
        self.post_processor = post_processor  # Store post-processor for response handling
        
        # Inject appropriate tools for each role
        allowed_tools = self.config.get("allowed_tools")

        if self.role == "manager":
            from tools import get_manager_tools_description
            tools_desc = get_manager_tools_description(allowed_tools)
            original_prompt = self.config.get("system_prompt", "")
            # Append tools description if not already present
            if "Available task assignment tools" not in original_prompt:
                self.config["system_prompt"] = f"{original_prompt}\n\n{tools_desc}"
        elif self.role in ["developer", "auditor"]:
            tools_desc = get_tools_description(allowed_tools)
            original_prompt = self.config.get("system_prompt", "")
            # Append tools description if not already present
            if "Available tools" not in original_prompt:
                self.config["system_prompt"] = f"{original_prompt}\n\n{tools_desc}"
        
        try:
            self.channel = channel_factory.create_channel(self.config)
            logger.info(f"Initialized agent: {self.name} (role: {self.role})")
        except Exception as e:
            raise OrganizationError(f"Failed to initialize agent {self.name}: {e}")
