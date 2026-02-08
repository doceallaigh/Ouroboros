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
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional

from comms import ChannelFactory, CommunicationError, extract_content_from_response
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
    
    def __init__(
        self,
        config: Dict[str, str],
        channel_factory: ChannelFactory,
        filesystem: FileSystem,
    ):
        """
        Initialize an agent.
        
        Args:
            config: Agent configuration dict with name, role, system_prompt, etc.
            channel_factory: Factory for creating communication channels
            filesystem: Filesystem for storing outputs
        """
        self.config = config
        self.name = config.get("name", "unknown")
        self.role = config.get("role", "unknown")
        self.filesystem = filesystem
        
        try:
            self.channel = channel_factory.create_channel(config)
            logger.info(f"Initialized agent: {self.name} (role: {self.role})")
        except Exception as e:
            raise OrganizationError(f"Failed to initialize agent {self.name}: {e}")
    
    def execute_task(self, task: Dict[str, Any]) -> str:
        """
        Execute a task using this agent.
        
        Args:
            task: Task dict with 'user_prompt' and optionally other fields
            
        Returns:
            Agent's response as string
            
        Raises:
            OrganizationError: If task execution fails
        """
        try:
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
            
            logger.debug(f"Agent {self.name} executing task")
            
            # Send and receive through channel
            self.channel.send_message(payload)
            response = asyncio.run(self.channel.receive_message())
            
            # Extract and store result
            result = extract_content_from_response(response)
            
            # Store output for replay capability
            self.filesystem.write_data(self.name, result)
            
            logger.info(f"Agent {self.name} completed task")
            return result
            
        except Exception as e:
            error_msg = f"Agent {self.name} task execution failed: {str(e)}"
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
        
        return Agent(config, self.channel_factory, self.filesystem)
    
    def decompose_request(self, user_request: str) -> str:
        """
        Use a manager agent to decompose a request into tasks.
        
        Args:
            user_request: User's high-level request
            
        Returns:
            Decomposed tasks as string (usually JSON)
        """
        try:
            manager = self._create_agent_for_role("manager")
            
            decomposition = manager.execute_task({
                "user_prompt": user_request,
            })
            
            logger.debug(f"Request decomposed into: {decomposition}")
            return decomposition
            
        except Exception as e:
            logger.error(f"Failed to decompose request: {e}")
            raise
    
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
        Execute assignments in parallel using thread pool.
        
        Args:
            assignments: List of task assignments
            user_request: Original user request for context
            
        Returns:
            List of execution results
        """
        results = []
        
        if not assignments:
            logger.warning("No assignments to execute")
            return results
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            
            for i, assignment in enumerate(assignments):
                role = assignment.get("role")
                task_desc = assignment.get("task", "")
                
                if not role:
                    logger.warning(f"Assignment {i} missing role field")
                    continue
                
                future = executor.submit(
                    self._execute_single_assignment,
                    role,
                    task_desc,
                    user_request,
                )
                futures[i] = (future, role)
            
            # Collect results
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
        
        Args:
            role: Agent role
            task: Task description
            original_request: Original user request
            
        Returns:
            Result dict with status and output
        """
        try:
            agent = self._create_agent_for_role(role)
            
            result_text = agent.execute_task({
                "user_prompt": task,
            })
            
            return {
                "role": role,
                "task": task,
                "status": "completed",
                "output": result_text,
            }
            
        except Exception as e:
            logger.error(f"Task execution failed for role {role}: {e}")
            raise


def main():
    """
    Main entry point for the Ouroboros agent harness.
    
    Parses command-line arguments and coordinates agent execution.
    """
    try:
        # Parse arguments
        replay_mode = "--replay" in sys.argv
        
        # Initialize filesystem
        try:
            if replay_mode:
                filesystem = ReadOnlyFileSystem(shared_dir="./shared_repo", replay_mode=True)
            else:
                filesystem = FileSystem(shared_dir="./shared_repo", replay_mode=False)
        except FileSystemError as e:
            logger.error(f"Filesystem initialization failed: {e}")
            sys.exit(1)
        
        # Initialize coordinator
        try:
            coordinator = CentralCoordinator(
                config_path="roles.json",
                filesystem=filesystem,
                replay_mode=replay_mode,
            )
        except OrganizationError as e:
            logger.error(f"Coordinator initialization failed: {e}")
            sys.exit(1)
        
        # Example request (can be replaced with user input)
        user_request = "Build a collaborative task management app with real-time sync"
        
        # Process request
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