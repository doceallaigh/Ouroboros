"""
Filesystem module for data storage and retrieval.

Responsibilities:
- Storage of communication and operational data during runtime
- Retrieval of data in replay mode
- Task and conversation history management
- Event sourcing for audit trail and replay capability
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
    def get_recorded_outputs_in_order(self, agent_name: str) -> list:
        """
        Retrieve all recorded outputs for an agent, sorted by query timestamp.

        Returns:
            List of (query_timestamp, content) tuples, sorted by timestamp.
        """
        outputs = []
        try:
            file_paths = sorted(
                f for f in os.listdir(self.working_dir)
                if f.startswith(agent_name) and f.endswith(".txt")
            )
            for file_path in file_paths:
                full_path = os.path.join(self.working_dir, file_path)
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Extract QUERY_TIMESTAMP from the file
                first_line = content.splitlines()[0] if content else ""
                if first_line.startswith("QUERY_TIMESTAMP:"):
                    ts = first_line.split(":", 1)[1].strip()
                else:
                    ts = ""
                outputs.append((ts, content))
            # Sort by timestamp string (ISO format sorts lexicographically)
            outputs.sort(key=lambda x: x[0])
            return outputs
        except Exception as e:
            logger.error(f"Failed to retrieve ordered outputs for {agent_name}: {e}")
            return []
    """
    Manages file storage for communication logs and operational data.
    
    Creates a timestamped directory for each session and stores agent
    communications within that directory. Also maintains an event log
    for event sourcing and replay capability.
    """
    
    # Event types for event sourcing
    EVENT_REQUEST_DECOMPOSED = "request_decomposed"
    EVENT_TASK_ASSIGNED = "task_assigned"
    EVENT_TASK_STARTED = "task_started"
    EVENT_TASK_COMPLETED = "task_completed"
    EVENT_TASK_FAILED = "task_failed"
    EVENT_ROLE_VALIDATION_FAILED = "role_validation_failed"
    EVENT_TIMEOUT_RETRY = "timeout_retry"
    EVENT_ROLE_RETRY = "role_retry"
    
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
            
            self.events_file = os.path.join(self.working_dir, "_events.jsonl")
            
            logger.info(f"Initialized FileSystem with session {self.session_id}")
            logger.debug(f"Working directory: {self.working_dir}")
            logger.debug(f"Events file: {self.events_file}")
            
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

    def create_query_file(self, agent_name: str, ticks: int, query_timestamp: str, payload: Dict[str, Any]) -> str:
        """
        Create a per-query file named {agent_name}_{ticks}.txt and write the query timestamp and payload.

        Returns the full path to the created file.
        """
        try:
            file_path = os.path.join(self.working_dir, f"{agent_name}_{ticks}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"QUERY_TIMESTAMP: {query_timestamp}\n")
                f.write("PAYLOAD:\n")
                json.dump(payload, f, indent=2)
                f.write("\n\n")
            logger.debug(f"Created query file for {agent_name}: {file_path}")
            return file_path
        except Exception as e:
            raise FileSystemError(f"Failed to create query file for {agent_name}: {e}")

    def append_response_file(self, agent_name: str, ticks: int, response_timestamp: str, response: str) -> None:
        """
        Append response timestamp and response content to the per-query file {agent_name}_{ticks}.txt.
        """
        try:
            file_path = os.path.join(self.working_dir, f"{agent_name}_{ticks}.txt")
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"RESPONSE_TIMESTAMP: {response_timestamp}\n")
                f.write("RESPONSE:\n")
                f.write(response)
                f.write("\n")
            logger.debug(f"Appended response to file for {agent_name}: {file_path}")
        except Exception as e:
            raise FileSystemError(f"Failed to append response file for {agent_name}: {e}")
    
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
    
    def record_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Record an event to the event log for event sourcing.
        
        Events are stored as JSON Lines (JSONL) format for easy streaming/replay.
        Each line contains a single event with timestamp.
        
        Args:
            event_type: Type of event (use EVENT_* constants)
            data: Event data dictionary
            
        Raises:
            FileSystemError: If event recording fails
        """
        try:
            event = {
                "timestamp": datetime.datetime.now().isoformat(),
                "type": event_type,
                "data": data,
            }
            
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
            
            logger.debug(f"Recorded event: {event_type}")
        except Exception as e:
            raise FileSystemError(f"Failed to record event: {e}")
    
    def get_events(self, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve recorded events, optionally filtered by type.
        
        Args:
            event_type: Optional event type to filter by
            
        Returns:
            List of event dictionaries
        """
        events = []
        try:
            if not os.path.exists(self.events_file):
                return events
            
            with open(self.events_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        if event_type is None or event.get("type") == event_type:
                            events.append(event)
            
            logger.debug(f"Retrieved {len(events)} events" + 
                        (f" of type {event_type}" if event_type else ""))
            return events
        except Exception as e:
            logger.error(f"Failed to retrieve events: {e}")
            return events


class ReadOnlyFileSystem(FileSystem):
    """
    Read-only filesystem wrapper for replay mode.
    
    Prevents accidental writes while in replay mode. Still allows reading events.
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
    
    def record_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """No-op event recording in replay mode."""
        logger.debug(f"ReadOnlyFileSystem: Ignoring event record attempt for type {event_type}")

    def create_query_file(self, agent_name: str, ticks: int, query_timestamp: str, payload: Dict[str, Any]) -> str:
        """No-op in replay mode; return expected file path."""
        file_path = os.path.join(self.working_dir, f"{agent_name}_{ticks}.txt")
        logger.debug(f"ReadOnlyFileSystem: Ignoring create_query_file for {file_path}")
        return file_path

    def append_response_file(self, agent_name: str, ticks: int, response_timestamp: str, response: str) -> None:
        """No-op in replay mode."""
        logger.debug(f"ReadOnlyFileSystem: Ignoring append_response_file for {agent_name}_{ticks}.txt")