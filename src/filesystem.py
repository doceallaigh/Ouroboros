"""
Filesystem module for data storage and retrieval.

Responsibilities:
- Storage of communication and operational data during runtime
- Retrieval of data in replay mode
- Task and conversation history management
"""

import datetime
import json
import logging
import os
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class FileSystemError(Exception):
    """Base exception for filesystem-related errors."""
    pass


class FileSystem:
    """
    Manages file storage for communication logs and operational data.
    
    Creates a timestamped directory for each session and stores agent
    communications within that directory.
    """
    
    def __init__(self, shared_dir: str, replay_mode: bool = False):
        """
        Initialize filesystem manager.
        
        Args:
            shared_dir: Relative path to shared storage directory
            replay_mode: Whether to load existing data or create new session
            
        Raises:
            FileSystemError: If initialization fails
        """
        try:
            # Find Ouroboros root directory
            root_dir = os.getcwd()
            while root_dir != os.path.dirname(root_dir):  # Stop at filesystem root
                if os.path.basename(root_dir) == "Ouroboros":
                    break
                root_dir = os.path.dirname(root_dir)
            
            if os.path.basename(root_dir) != "Ouroboros":
                logger.warning("Could not find Ouroboros root directory, using current directory")
                root_dir = os.getcwd()
            
            self.shared_dir = os.path.join(root_dir, shared_dir)
            os.makedirs(self.shared_dir, exist_ok=True)
            
            if replay_mode:
                self.session_id = self._get_latest_session_id()
            else:
                self.session_id = self._create_new_session_id()
            
            self.working_dir = os.path.join(self.shared_dir, self.session_id)
            os.makedirs(self.working_dir, exist_ok=True)
            
            logger.info(f"Initialized FileSystem with session {self.session_id}")
            logger.debug(f"Working directory: {self.working_dir}")
            
        except Exception as e:
            raise FileSystemError(f"Failed to initialize filesystem: {e}")
    
    def _create_new_session_id(self) -> str:
        """Generate a new session ID based on current timestamp."""
        return datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")[:-3]
    
    def _get_latest_session_id(self) -> str:
        """
        Get the most recent session ID from shared directory.
        
        Returns:
            Latest session ID string
            
        Raises:
            FileSystemError: If no sessions exist
        """
        try:
            sessions = sorted(os.listdir(self.shared_dir))
            if not sessions:
                raise FileSystemError("No previous sessions found for replay mode")
            latest = sessions[-1]
            logger.info(f"Loading latest session: {latest}")
            return latest
        except FileNotFoundError:
            raise FileSystemError(f"Shared directory not found: {self.shared_dir}")
    
    def write_data(self, agent_name: str, data: str) -> None:
        """
        Store agent output data to file.
        
        Args:
            agent_name: Name of agent
            data: Content to store
            
        Raises:
            FileSystemError: If write fails
        """
        try:
            file_path = os.path.join(self.working_dir, f"{agent_name}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(data)
            logger.debug(f"Wrote data for agent {agent_name} to {file_path}")
        except Exception as e:
            raise FileSystemError(f"Failed to write data for {agent_name}: {e}")
    
    def write_structured_data(self, agent_name: str, data: Dict[str, Any]) -> None:
        """
        Store structured (JSON) data for an agent.
        
        Args:
            agent_name: Name of agent
            data: Dictionary to store as JSON
            
        Raises:
            FileSystemError: If write fails
        """
        try:
            file_path = os.path.join(self.working_dir, f"{agent_name}_structured.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Wrote structured data for agent {agent_name}")
        except Exception as e:
            raise FileSystemError(f"Failed to write structured data for {agent_name}: {e}")
    
    def get_recorded_output(self, agent_name: str) -> Optional[str]:
        """
        Retrieve previously recorded output for an agent.
        
        Args:
            agent_name: Name of agent to retrieve data for
            
        Returns:
            Recorded output string, or None if not found
        """
        try:
            file_paths = sorted(os.listdir(self.working_dir))
            for file_path in file_paths:
                if file_path.startswith(agent_name) and file_path.endswith(".txt"):
                    full_path = os.path.join(self.working_dir, file_path)
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    logger.debug(f"Retrieved recorded output for {agent_name}")
                    return content
            
            logger.warning(f"No recorded output found for agent {agent_name}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve recorded output for {agent_name}: {e}")
            return None
    
    def save_conversation_history(self, agent_name: str, history: List[Dict[str, str]]) -> None:
        """
        Save full conversation history for an agent.
        
        Args:
            agent_name: Name of agent
            history: List of conversation messages
        """
        try:
            file_path = os.path.join(self.working_dir, f"{agent_name}_history.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
            logger.debug(f"Saved conversation history for {agent_name}")
        except Exception as e:
            logger.error(f"Failed to save conversation history for {agent_name}: {e}")
    
    def get_session_metadata(self) -> Dict[str, Any]:
        """Get metadata about current session."""
        return {
            "session_id": self.session_id,
            "working_dir": self.working_dir,
            "created_at": self.session_id,  # Session ID contains timestamp
        }


class ReadOnlyFileSystem(FileSystem):
    """
    Read-only filesystem wrapper for replay mode.
    
    Prevents accidental writes while in replay mode.
    """
    
    def write_data(self, agent_name: str, data: str) -> None:
        """No-op write in replay mode."""
        logger.debug(f"ReadOnlyFileSystem: Ignoring write attempt for agent {agent_name}")
    
    def write_structured_data(self, agent_name: str, data: Dict[str, Any]) -> None:
        """No-op write in replay mode."""
        logger.debug(f"ReadOnlyFileSystem: Ignoring structured write attempt for agent {agent_name}")
    
    def save_conversation_history(self, agent_name: str, history: List[Dict[str, str]]) -> None:
        """No-op write in replay mode."""
        logger.debug(f"ReadOnlyFileSystem: Ignoring history write attempt for agent {agent_name}")