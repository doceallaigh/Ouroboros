"""
Main coordination module for the Ouroboros agent harness.

Responsibilities:
- Orchestration of multi-agent collaboration
- Task decomposition and assignment
- Result aggregation and coordination
- Application lifecycle management
"""

import asyncio
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional

from comms import ChannelFactory, CommunicationError, APIError, extract_content_from_response
from filesystem import FileSystem, ReadOnlyFileSystem, FileSystemError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class OrganizationError(Exception):
    """Base exception for organizational errors."""
    pass


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
    ):
        """
        Initialize an agent.
        
        Args:
            config: Agent configuration dict with role, system_prompt, etc.
            channel_factory: Factory for creating communication channels
            filesystem: Filesystem for storing outputs
            instance_number: Instance number for this role (1-based, formatted as 01, 02, etc.)
            
        Raises:
            OrganizationError: If agent initialization fails
        """
        self.config = config
        self.role = config.get("role", "unknown")
        # Generate name from role and instance number
        self.name = f"{self.role}{instance_number:02d}"
        self.filesystem = filesystem
        
        try:
            self.channel = channel_factory.create_channel(config)
            logger.info(f"Initialized agent: {self.name} (role: {self.role})")
        except Exception as e:
            raise OrganizationError(f"Failed to initialize agent {self.name}: {e}")
    
    def execute_task(self, task: Dict[str, Any]) -> str:
        """
        Execute a task using this agent with retry logic for timeouts.
        
        Records timeout retry events for event sourcing.
        
        Args:
            task: Task dict with 'user_prompt' and optionally other fields
            
        Returns:
            Agent's response as string
            
        Raises:
            OrganizationError: If task execution fails after retries
        """
        base_timeout = self.config.get("timeout", 120)
        backoff_delay = 1.0
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Increase timeout with each retry
                current_timeout = base_timeout * (self.INITIAL_TIMEOUT_MULTIPLIER ** attempt)
                
                # Build the message payload
                payload = {
                    "messages": [
                        {
                            "role": "system",
                            "content": self.config.get("system_prompt", "")
                        },
                        {
                            "role": "user",
                            "content": task.get("user_prompt", "")
                        }
                    ],
                    "model": self.config.get("model", "qwen/qwen2-7b"),
                    "temperature": float(self.config.get("temperature", 0.7)),
                    "max_tokens": int(self.config.get("max_tokens", -1)),
                }
                
                logger.debug(f"Agent {self.name} executing task (attempt {attempt + 1}/{self.MAX_RETRIES}, timeout={current_timeout}s)")
                
                # Send message and get ticks id for this query
                ticks = self.channel.send_message(payload)

                # Record query file with timestamp and payload
                query_ts = __import__("datetime").datetime.now().isoformat()
                try:
                    self.filesystem.create_query_file(self.name, ticks, query_ts, payload)
                except Exception:
                    logger.exception("Failed to create query file")

                # Receive response (channel returns (response, ticks))
                response, returned_ticks = asyncio.run(self.channel.receive_message())
                if returned_ticks is None:
                    returned_ticks = ticks
                
                # Extract and store result
                result = extract_content_from_response(response)

                # Append response timestamp and content to the per-query file
                resp_ts = __import__("datetime").datetime.now().isoformat()
                try:
                    self.filesystem.append_response_file(self.name, returned_ticks, resp_ts, result)
                except Exception:
                    logger.exception("Failed to append response to query file")

                # Also store latest output for replay capability
                self.filesystem.write_data(self.name, result)
                
                logger.info(f"Agent {self.name} completed task")
                return result
                
            except APIError as e:
                # Check if it's a timeout error
                if "timed out" in str(e).lower():
                    last_error = e
                    if attempt < self.MAX_RETRIES - 1:
                        # Record timeout retry event
                        self.filesystem.record_event(
                            self.filesystem.EVENT_TIMEOUT_RETRY,
                            {
                                "agent": self.name,
                                "attempt": attempt + 1,
                                "timeout_seconds": base_timeout * (self.INITIAL_TIMEOUT_MULTIPLIER ** attempt),
                                "next_timeout_seconds": base_timeout * (self.INITIAL_TIMEOUT_MULTIPLIER ** (attempt + 1)),
                            }
                        )
                        
                        logger.warning(
                            f"Agent {self.name} timeout (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                            f"retrying in {backoff_delay}s with increased timeout"
                        )
                        time.sleep(backoff_delay)
                        backoff_delay *= self.BACKOFF_MULTIPLIER
                        continue
                    else:
                        error_msg = f"Agent {self.name} task execution failed after {self.MAX_RETRIES} retries: {str(e)}"
                        logger.error(error_msg)
                        raise OrganizationError(error_msg)
                else:
                    # Non-timeout API error, don't retry
                    error_msg = f"Agent {self.name} task execution failed: {str(e)}"
                    logger.error(error_msg)
                    raise OrganizationError(error_msg)
            
            except Exception as e:
                error_msg = f"Agent {self.name} task execution failed: {str(e)}"
                logger.error(error_msg)
                raise OrganizationError(error_msg)
        
        # Should not reach here, but handle just in case
        error_msg = f"Agent {self.name} task execution failed after {self.MAX_RETRIES} retries: {str(last_error)}"
        logger.error(error_msg)
        raise OrganizationError(error_msg)


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
    ):
        """
        Initialize the coordinator.
        
        Args:
            config_path: Path to roles.json configuration file
            filesystem: Filesystem manager for data storage
            replay_mode: Whether to run in replay mode
            
        Raises:
            OrganizationError: If initialization fails
        """
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
            
            self.filesystem = filesystem
            self.replay_mode = replay_mode
            
            # Track instance counts for each role to generate unique names
            self.role_instance_counts: Dict[str, int] = {}
            
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
        """Load replay data for an agent."""
        return self.filesystem.get_recorded_output(agent_name)
    
    def _find_agent_config(self, role: str) -> Optional[Dict[str, str]]:
        """
        Find configuration for a specific role.
        
        Args:
            role: Role name to find
            
        Returns:
            First matching agent config, or None
        """
        for agent_config in self.config.values():
            if agent_config.get("role") == role:
                return agent_config
        return None
    
    def _create_agent_for_role(self, role: str) -> Agent:
        """
        Create an agent instance for a specific role.
        
        Tracks instance counts to generate unique agent names.
        
        Args:
            role: Role name
            
        Returns:
            Agent instance
            
        Raises:
            OrganizationError: If no agent found for role
        """
        config = self._find_agent_config(role)
        if not config:
            raise OrganizationError(f"No agent configured for role: {role}")
        
        # Increment instance count for this role
        if role not in self.role_instance_counts:
            self.role_instance_counts[role] = 0
        self.role_instance_counts[role] += 1
        
        return Agent(
            config, 
            self.channel_factory, 
            self.filesystem,
            instance_number=self.role_instance_counts[role]
        )
    
    def decompose_request(self, user_request: str) -> str:
        """
        Use a manager agent to decompose a request into tasks.
        
        Validates that assigned roles exist. If manager assigns to invalid roles,
        retries with corrective feedback.
        
        Args:
            user_request: User's high-level request
            
        Returns:
            Decomposed tasks as string (usually JSON)
            
        Raises:
            OrganizationError: If decomposition fails after retries
        """
        max_retries = 2
        backoff_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                manager = self._create_agent_for_role("manager")
                
                decomposition = manager.execute_task({
                    "user_prompt": user_request,
                })
                
                # Validate that assigned roles exist
                assignments = None
                try:
                    assignments = json.loads(decomposition)
                    if isinstance(assignments, list):
                        invalid_roles = self._validate_assignment_roles(assignments)
                        
                        if invalid_roles:
                            # Roles are invalid, record event and retry with feedback
                            if attempt < max_retries - 1:
                                self.filesystem.record_event(
                                    self.filesystem.EVENT_ROLE_VALIDATION_FAILED,
                                    {
                                        "attempt": attempt + 1,
                                        "invalid_roles": invalid_roles,
                                        "user_request": user_request[:200],  # Truncate for log
                                    }
                                )
                                
                                logger.warning(
                                    f"Manager assigned to invalid roles: {invalid_roles}. "
                                    f"Retrying with corrective feedback..."
                                )
                                time.sleep(backoff_delay)
                                backoff_delay *= 2.0
                                
                                # Create corrective prompt
                                valid_roles = list(self.config.keys())
                                corrective_request = (
                                    f"{user_request}\n\n"
                                    f"[SYSTEM CONSTRAINT: You must ONLY assign tasks to these roles: {valid_roles}]"
                                )
                                user_request = corrective_request
                                
                                # Record retry event
                                self.filesystem.record_event(
                                    self.filesystem.EVENT_ROLE_RETRY,
                                    {
                                        "attempt": attempt + 1,
                                        "valid_roles": valid_roles,
                                    }
                                )
                                continue
                            else:
                                error_msg = f"Manager failed to assign valid roles after {max_retries} attempts. Invalid roles: {invalid_roles}"
                                logger.error(error_msg)
                                raise OrganizationError(error_msg)
                except json.JSONDecodeError:
                    # Not JSON, will be handled later in assign_and_execute
                    pass
                
                # Record successful decomposition event
                if assignments is not None:
                    self.filesystem.record_event(
                        self.filesystem.EVENT_REQUEST_DECOMPOSED,
                        {
                            "attempt": attempt + 1,
                            "num_assignments": len(assignments) if isinstance(assignments, list) else 0,
                        }
                    )
                
                logger.debug(f"Request decomposed into: {decomposition}")
                return decomposition
                
            except OrganizationError:
                raise
            except Exception as e:
                error_msg = f"Failed to decompose request: {e}"
                logger.error(error_msg)
                raise OrganizationError(error_msg)
        
        raise OrganizationError("Decomposition failed after maximum retries")
    
    def _validate_assignment_roles(self, assignments: List[Dict[str, Any]]) -> List[str]:
        """
        Validate that all assigned roles exist in the configuration.
        
        Args:
            assignments: List of task assignments
            
        Returns:
            List of invalid role names, empty if all valid
        """
        valid_roles = set(self.config.keys())
        invalid_roles = []
        
        for assignment in assignments:
            if isinstance(assignment, dict):
                role = assignment.get("role")
                if role and role not in valid_roles:
                    invalid_roles.append(role)
        
        return invalid_roles
    
    def assign_and_execute(self, user_request: str) -> List[Dict[str, Any]]:
        """
        Main coordination method: decompose request and execute via agents.
        
        This is the primary entry point for processing user requests through
        the agent harness.
        
        Args:
            user_request: User's request to process
            
        Returns:
            List of results from agent execution
        """
        try:
            logger.info(f"Processing request: {user_request}")
            
            # Step 1: Decompose request using manager
            decomposition = self.decompose_request(user_request)
            
            # Step 2: Parse decomposition (handle various formats)
            try:
                assignments = json.loads(decomposition)
                if not isinstance(assignments, list):
                    # If it's a dict, try to extract task list
                    if isinstance(assignments, dict):
                        assignments = assignments.get("tasks", [])
            except json.JSONDecodeError:
                logger.warning("Decomposition not in JSON format, treating as single task")
                assignments = []
            
            # Step 3: Execute tasks in parallel
            results = self._execute_assignments(assignments, user_request)
            
            logger.info(f"Request processing complete with {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Request processing failed: {e}")
            raise OrganizationError(f"Failed to process request: {e}")
    
    def _execute_assignments(self, assignments: List[Dict[str, Any]], user_request: str) -> List[Dict[str, Any]]:
        """
        Execute assignments respecting sequence ordering.
        
        Tasks with the same sequence number execute in parallel.
        Tasks with different sequence numbers execute sequentially, with
        sequence N+1 starting only after sequence N completes.
        
        Args:
            assignments: List of task assignments with 'role', 'task', and optional 'sequence' fields
            user_request: Original user request for context
            
        Returns:
            List of execution results
        """
        results = []
        
        if not assignments:
            logger.warning("No assignments to execute")
            return results
        
        # Group assignments by sequence number
        # Default sequence is 1 if not specified
        sequences: Dict[int, List[Dict[str, Any]]] = {}
        for i, assignment in enumerate(assignments):
            if not assignment.get("role"):
                logger.warning(f"Assignment {i} missing role field")
                continue
            
            sequence = assignment.get("sequence", 1)
            if sequence not in sequences:
                sequences[sequence] = []
            sequences[sequence].append((i, assignment))
        
        if not sequences:
            logger.warning("No valid assignments to execute")
            return results
        
        # Execute sequences in order
        for sequence in sorted(sequences.keys()):
            sequence_assignments = sequences[sequence]
            logger.info(f"Executing sequence {sequence} with {len(sequence_assignments)} tasks")
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}
                
                # Submit all tasks in this sequence
                for i, assignment in sequence_assignments:
                    role = assignment.get("role")
                    task_desc = assignment.get("task", "")
                    
                    future = executor.submit(
                        self._execute_single_assignment,
                        role,
                        task_desc,
                        user_request,
                    )
                    futures[i] = (future, role)
                
                # Collect results from this sequence
                for i, (future, role) in futures.items():
                    try:
                        result = future.result(timeout=300)  # 5 minute timeout per task
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Assignment {i} (role: {role}) failed: {e}")
                        results.append({
                            "role": role,
                            "status": "failed",
                            "error": str(e),
                        })
        
        return results
    
    def _execute_single_assignment(self, role: str, task: str, original_request: str) -> Dict[str, Any]:
        """
        Execute a single task assignment.
        
        Records events for task start and completion/failure.
        
        Args:
            role: Agent role
            task: Task description
            original_request: Original user request
            
        Returns:
            Result dict with status and output
        """
        try:
            # Record task start event
            self.filesystem.record_event(
                self.filesystem.EVENT_TASK_STARTED,
                {
                    "role": role,
                    "task": task[:200],  # Truncate for log
                }
            )
            
            agent = self._create_agent_for_role(role)
            
            result_text = agent.execute_task({
                "user_prompt": task,
            })
            
            # Record task completion event
            self.filesystem.record_event(
                self.filesystem.EVENT_TASK_COMPLETED,
                {
                    "role": role,
                    "output_length": len(result_text),
                }
            )
            
            return {
                "role": role,
                "task": task,
                "status": "completed",
                "output": result_text,
            }
            
        except Exception as e:
            # Record task failure event
            self.filesystem.record_event(
                self.filesystem.EVENT_TASK_FAILED,
                {
                    "role": role,
                    "error": str(e)[:200],  # Truncate for log
                }
            )
            logger.error(f"Task execution failed for role {role}: {e}")
            raise


def main():
    """
    Main entry point for the Ouroboros agent harness.
    
    Parses command-line arguments and coordinates agent execution.
    
    Usage:
        python main.py [run] [--replay]
        
    Arguments:
        run: Execute the coordinator (optional, runs by default)
        --replay: Run in replay mode using recorded responses
    """
    try:
        # Parse arguments
        replay_mode = "--replay" in sys.argv
        
        # Determine config and shared directory paths
        # Try current directory first, then parent directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try to find roles.json in script directory or parent
        if os.path.exists(os.path.join(script_dir, "roles.json")):
            roles_path = os.path.join(script_dir, "roles.json")
            shared_dir = os.path.join(os.path.dirname(script_dir), "shared_repo")
        else:
            roles_path = "roles.json"
            shared_dir = "./shared_repo"
        
        # Ensure directories exist
        os.makedirs(shared_dir, exist_ok=True)
        
        logger.info(f"Using roles.json from: {roles_path}")
        logger.info(f"Using shared directory: {shared_dir}")
        
        # Initialize filesystem
        try:
            if replay_mode:
                filesystem = ReadOnlyFileSystem(shared_dir=shared_dir, replay_mode=True)
            else:
                filesystem = FileSystem(shared_dir=shared_dir, replay_mode=False)
        except FileSystemError as e:
            logger.error(f"Filesystem initialization failed: {e}")
            sys.exit(1)
        
        # Initialize coordinator
        try:
            coordinator = CentralCoordinator(
                config_path=roles_path,
                filesystem=filesystem,
                replay_mode=replay_mode,
            )
        except OrganizationError as e:
            logger.error(f"Coordinator initialization failed: {e}")
            sys.exit(1)
        
        # Example request (can be replaced with user input)
        user_request = "Build a collaborative task management app with real-time sync"
        
        # Process request
        # Process request (fail-fast: do not auto-fallback to replay)
        results = coordinator.assign_and_execute(user_request)
        
        # Output results
        logger.info("Execution Results:")
        for result in results:
            logger.info(json.dumps(result, indent=2))
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()