"""
Core coordinator class for multi-agent orchestration.
"""

import json
import logging
from typing import Dict, List, Any, Optional

from comms import ChannelFactory, OutputPostProcessingStrategy
from fileio import FileSystem
from main.exceptions import OrganizationError

logger = logging.getLogger(__name__)


class CentralCoordinator:
    """
    Orchestrates multi-agent collaboration.
    
    Coordinates task decomposition, agent assignment, execution,
    and result aggregation for complex software development tasks.
    """
    
    def __init__(
        self,
        config_path: str,
        filesystem: FileSystem,
        replay_mode: bool = False,
        repo_working_dir: Optional[str] = None,
        allow_git_tools: bool = True,
        post_processor: Optional[OutputPostProcessingStrategy] = None,
    ):
        """
        Initialize the coordinator.
        
        Args:
            config_path: Path to roles.json configuration file
            filesystem: Filesystem manager for data storage
            replay_mode: Whether to run in replay mode
            repo_working_dir: Optional repository working directory for tool execution
            allow_git_tools: Whether git tools are enabled for agents
            post_processor: Optional post-processing strategy for agent responses
            
        Raises:
            OrganizationError: If initialization fails
        """
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
            
            self.filesystem = filesystem
            self.replay_mode = replay_mode
            self.repo_working_dir = repo_working_dir
            self.allow_git_tools = allow_git_tools
            self.post_processor = post_processor  # Store post-processor for agents
            
            # Track instance counts for each role to generate unique names
            self.role_instance_counts: Dict[str, int] = {}
            
            # Track callbacks from agents for handling blockers
            self.callbacks: List[Dict[str, Any]] = []
            
            # Create channel factory with replay data loader
            self.channel_factory = ChannelFactory(
                replay_mode=replay_mode,
                replay_data_loader=self._load_replay_data if replay_mode else None
            )
            
            logger.info(f"Initialized coordinator with {len(self.config)} agent roles")
            logger.info(f"Operating in {'REPLAY' if replay_mode else 'LIVE'} mode")
            
        except FileNotFoundError:
            raise OrganizationError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError:
            raise OrganizationError(f"Invalid JSON in configuration: {config_path}")
        except Exception as e:
            raise OrganizationError(f"Failed to initialize coordinator: {e}")
    
    def _load_replay_data(self, agent_name: str) -> Optional[str]:
        """Load replay data for an agent, in timestamp order."""
        if not hasattr(self, "_replay_pointers"):
            self._replay_pointers = {}
        outputs = self.filesystem.get_recorded_outputs_in_order(agent_name)
        idx = self._replay_pointers.get(agent_name, 0)
        if idx < len(outputs):
            self._replay_pointers[agent_name] = idx + 1
            return outputs[idx][1]
        return None
