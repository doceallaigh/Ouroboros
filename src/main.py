"""
Main coordination module for the Ouroboros agent harness.

Responsibilities:
- Orchestration of multi-agent collaboration
- Task decomposition and assignment
- Result aggregation and coordination
- Application lifecycle management
"""

import argparse
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
from agent_tools import get_tools_description, AgentTools
import re

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
        self.config = config.copy()  # Copy to avoid modifying original
        self.role = self.config.get("role", "unknown")
        # Generate name from role and instance number
        self.name = f"{self.role}{instance_number:02d}"
        self.filesystem = filesystem
        self.callback_handler = None  # Will be set by coordinator if callbacks are needed
        
        # Inject appropriate tools for each role
        if self.role == "manager":
            from agent_tools import get_manager_tools_description
            tools_desc = get_manager_tools_description()
            original_prompt = self.config.get("system_prompt", "")
            # Append tools description if not already present
            if "Available task assignment tools" not in original_prompt:
                self.config["system_prompt"] = f"{original_prompt}\n\n{tools_desc}"
        elif self.role in ["developer", "auditor"]:
            tools_desc = get_tools_description()
            original_prompt = self.config.get("system_prompt", "")
            # Append tools description if not already present
            if "Available tools" not in original_prompt:
                self.config["system_prompt"] = f"{original_prompt}\n\n{tools_desc}"
        
        try:
            self.channel = channel_factory.create_channel(self.config)
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
        
        # Parse model_endpoints configuration (supports both old and new formats)
        model_endpoints = self.config.get("model_endpoints", [])
        if not model_endpoints:
            # Fallback to old separate model/endpoint format for backward compatibility
            model = self.config.get("model", "qwen/qwen2-7b")
            endpoint = self.config.get("endpoint", "http://localhost:12345/v1/chat/completions")
            if isinstance(model, str):
                model = [model]
            if isinstance(endpoint, str):
                endpoint = [endpoint]
            if not model:
                model = ["qwen/qwen2-7b"]
            if not endpoint:
                endpoint = ["http://localhost:12345/v1/chat/completions"]
            # Convert old format to model_endpoints
            model_endpoints = [{"model": m, "endpoint": e} for m, e in zip(model, endpoint)]
        
        if not model_endpoints:
            model_endpoints = [{"model": "qwen/qwen2-7b", "endpoint": "http://localhost:12345/v1/chat/completions"}]
        
        backoff_delay = 1.0
        last_error = None
        ticks = None
        response_recorded = False  # Flag to ensure we only record response once
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Increase timeout with each retry
                current_timeout = base_timeout * (self.INITIAL_TIMEOUT_MULTIPLIER ** attempt)
                
                # Select model/endpoint pair for this attempt (failover to next pair on retry)
                pair_index = min(attempt, len(model_endpoints) - 1)
                selected_pair = model_endpoints[pair_index]
                selected_model = selected_pair["model"]
                selected_endpoint = selected_pair["endpoint"]

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
                    "model": selected_model,
                    "temperature": float(self.config.get("temperature", 0.7)),
                    "max_tokens": int(self.config.get("max_tokens", -1)),
                }
                
                # Update endpoint per attempt for failover
                self.channel.config["endpoint"] = selected_endpoint

                logger.debug(
                    f"Agent {self.name} executing task (attempt {attempt + 1}/{self.MAX_RETRIES}, "
                    f"timeout={current_timeout}s, model={selected_model}, endpoint={selected_endpoint})"
                )
                
                # Send message and get ticks id for this query (generate on first attempt only)
                if ticks is None:
                    ticks = self.channel.send_message(payload)
                else:
                    # On retry, send with same ticks but don't overwrite it
                    self.channel.send_message(payload)

                # Record query file with timestamp and payload (only on first attempt)
                if attempt == 0:
                    query_ts = __import__("datetime").datetime.now().isoformat()
                    try:
                        self.filesystem.create_query_file(self.name, ticks, query_ts, payload)
                    except Exception:
                        logger.exception("Failed to create query file")

                # Receive response (channel may return response or set channel.last_ticks)
                resp_result = asyncio.run(self.channel.receive_message())
                if isinstance(resp_result, tuple):
                    response, returned_ticks = resp_result
                else:
                    response = resp_result
                    returned_ticks = getattr(self.channel, 'last_ticks', None)
                if returned_ticks is None:
                    returned_ticks = ticks

                # Extract and store result
                result = extract_content_from_response(response)

                # Append response timestamp and content to the per-query file (only once)
                if not response_recorded:
                    resp_ts = __import__("datetime").datetime.now().isoformat()
                    try:
                        self.filesystem.append_response_file(self.name, returned_ticks, resp_ts, result)
                        response_recorded = True
                    except Exception:
                        logger.exception("Failed to append response to query file")

                # (Removed write_data; replay now uses per-query files in order)
                
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
    
    def execute_tools_from_response(self, response: str, working_dir: str = ".") -> Dict[str, Any]:
        """
        Extract and execute tool calls from an agent's response.
        
        Looks for Python code blocks containing tool calls and executes them.
        
        Args:
            response: Agent's text response potentially containing tool calls
            working_dir: Working directory for tool operations
            
        Returns:
            Dict with execution results and summary
        """
        # Initialize agent tools
        tools = AgentTools(working_dir=working_dir)
        
        # Extract Python code blocks from response
        code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
        
        if not code_blocks:
            logger.debug(f"No Python code blocks found in response from {self.name}")
            return {
                "tools_executed": False,
                "message": "No tool calls found in response"
            }
        
        results = []
        total_calls = 0
        
        # Execute each code block
        for code_block in code_blocks:
            # Create a safe execution environment with tools available
            exec_globals = {
                'read_file': tools.read_file,
                'write_file': tools.write_file,
                'append_file': tools.append_file,
                'edit_file': tools.edit_file,
                'list_directory': tools.list_directory,
                'list_all_files': tools.list_all_files,
                'search_files': tools.search_files,
                'get_file_info': tools.get_file_info,
                'delete_file': tools.delete_file,
                'raise_callback': self.raise_callback,  # Include callback method
                'print': lambda *args, **kwargs: None,  # Suppress print statements
            }
            exec_locals = {}
            
            try:
                # Execute the code
                exec(code_block, exec_globals, exec_locals)
                
                # Count tool calls (rough estimate based on function calls in code)
                for tool_name in ['read_file', 'write_file', 'append_file', 'edit_file', 
                                 'list_directory', 'list_all_files', 'search_files', 
                                 'get_file_info', 'delete_file', 'raise_callback']:
                    total_calls += code_block.count(f'{tool_name}(')
                
                results.append({
                    "success": True,
                    "code_executed": len(code_block),
                })
                logger.info(f"Agent {self.name} executed tools successfully")
                
            except Exception as e:
                logger.error(f"Tool execution failed for {self.name}: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "code": code_block[:200]  # Include snippet for debugging
                })
        
        return {
            "tools_executed": True,
            "code_blocks_found": len(code_blocks),
            "code_blocks_executed": len([r for r in results if r.get("success")]),
            "estimated_tool_calls": total_calls,
            "results": results
        }
    
    def raise_callback(self, message: str, callback_type: str = "query") -> Optional[str]:
        """
        Raise a callback to the calling agent (e.g., request clarification, report blocker).
        
        Args:
            message: The message/query to send to the caller
            callback_type: Type of callback ('query', 'blocker', 'clarification', 'error')
        
        Returns:
            Response from caller if available, None otherwise
        """
        if not self.callback_handler:
            logger.warning(f"Agent {self.name} attempted callback but no handler set")
            return None
        
        logger.info(f"Agent {self.name} raising {callback_type} callback: {message[:100]}")
        
        try:
            response = self.callback_handler(self.name, message, callback_type)
            logger.info(f"Callback response received for {self.name}")
            return response
        except Exception as e:
            logger.error(f"Callback failed for {self.name}: {e}")
            return None


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
        """Load replay data for an agent, in timestamp order."""
        if not hasattr(self, "_replay_pointers"):
            self._replay_pointers = {}
        outputs = self.filesystem.get_recorded_outputs_in_order(agent_name)
        idx = self._replay_pointers.get(agent_name, 0)
        if idx < len(outputs):
            self._replay_pointers[agent_name] = idx + 1
            return outputs[idx][1]
        return None
    
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
    
    def _extract_assignments_from_tool_calls(self, response: str) -> Optional[List[Dict[str, Any]]]:
        """
        Extract task assignments from manager's tool calls in response.
        
        Looks for assign_task() and assign_tasks() calls in the manager's response.
        
        Args:
            response: Manager's response text
            
        Returns:
            List of extracted assignments, or None if no tool calls found
        """
        assignments = []
        
        # Look for assign_task calls: assign_task('role', 'task', sequence=N)
        assign_task_pattern = r"assign_task\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*?)['\"]\s*,\s*sequence\s*=\s*(\d+)"
        for match in re.finditer(assign_task_pattern, response, re.DOTALL):
            role, task, sequence = match.groups()
            task = task.replace('\\n', '\n')  # Unescape newlines
            assignments.append({
                "role": role.strip(),
                "task": task.strip(),
                "sequence": int(sequence),
                "caller": "manager"
            })
        
        # Look for assign_tasks calls with array/list structure
        # This is more complex - look for assign_tasks([ ... ])
        assign_tasks_pattern = r"assign_tasks\s*\(\s*\[\s*(.*?)\s*\]\s*\)"
        for match in re.finditer(assign_tasks_pattern, response, re.DOTALL):
            tasks_str = match.group(1)
            
            # Extract individual task objects from the array
            # Look for {role: ..., task: ..., sequence: ...} patterns
            task_obj_pattern = r"\{\s*['\"]?role['\"]?\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?task['\"]?\s*:\s*['\"]([^'\"]*?)['\"]\s*,\s*['\"]?sequence['\"]?\s*:\s*(\d+)"
            for task_match in re.finditer(task_obj_pattern, tasks_str, re.DOTALL):
                role, task, sequence = task_match.groups()
                task = task.replace('\\n', '\n')  # Unescape newlines
                assignments.append({
                    "role": role.strip(),
                    "task": task.strip(),
                    "sequence": int(sequence),
                    "caller": "manager"
                })
        
        return assignments if assignments else None
    
    def decompose_request(self, user_request: str) -> str:
        """
        Use a manager agent to decompose a request into tasks.
        
        Now supports both tool-based assignments and legacy JSON format.
        Validates that assigned roles exist. If manager assigns to invalid roles,
        retries with corrective feedback.
        
        Args:
            user_request: User's high-level request
            
        Returns:
            Decomposed tasks as JSON string
            
        Raises:
            OrganizationError: If decomposition fails after retries
        """
        max_retries = 2
        backoff_delay = 1.0
        
        # Create manager once outside the retry loop to avoid duplicate agents
        manager = self._create_agent_for_role("manager")
        
        for attempt in range(max_retries):
            try:
                decomposition = manager.execute_task({
                    "user_prompt": user_request,
                })
                
                # Try to extract assignments from tool calls first
                assignments = self._extract_assignments_from_tool_calls(decomposition)
                
                if assignments is None:
                    # Fall back to JSON parsing for legacy format
                    try:
                        parsed = json.loads(decomposition)
                        if isinstance(parsed, list):
                            assignments = parsed
                        elif isinstance(parsed, dict) and "tasks" in parsed:
                            assignments = parsed.get("tasks", [])
                    except json.JSONDecodeError:
                        pass
                
                if assignments is None:
                    # No assignments found in either format
                    json_parse_error = "No task assignments found (neither tool calls nor valid JSON)"
                    # Retry with corrective feedback
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Manager response contained no task assignments. "
                            f"Retrying with corrective feedback..."
                        )
                        time.sleep(backoff_delay)
                        backoff_delay *= 2.0
                        
                        # Add feedback about using tools
                        corrective_request = (
                            f"{user_request}\n\n"
                            f"[IMPORTANT: Use the task assignment tools to assign tasks. "
                            f"Call assign_task() or assign_tasks() with 'developer' or 'auditor' roles.]"
                        )
                        user_request = corrective_request
                        continue
                    else:
                        error_msg = f"Manager failed to assign tasks after {max_retries} attempts. {json_parse_error}"
                        logger.error(error_msg)
                        raise OrganizationError(error_msg)
                
                # Validate assigned roles
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
                
                # Record successful decomposition event and convert to JSON for return
                self.filesystem.record_event(
                    self.filesystem.EVENT_REQUEST_DECOMPOSED,
                    {
                        "attempt": attempt + 1,
                        "num_assignments": len(assignments) if isinstance(assignments, list) else 0,
                    }
                )
                
                # Convert assignments back to JSON string for compatibility
                logger.debug(f"Request decomposed into {len(assignments)} assignments")
                return json.dumps(assignments)
            
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
            # Note: JSON parsing and validation happens in decompose_request with retries
            try:
                assignments = json.loads(decomposition)
                if not isinstance(assignments, list):
                    # If it's a dict, try to extract task list
                    if isinstance(assignments, dict):
                        assignments = assignments.get("tasks", [])
                    else:
                        # This shouldn't happen if decompose_request validated properly
                        logger.warning(f"Unexpected response format: {type(assignments)}. Treating as empty assignments.")
                        assignments = []
            except json.JSONDecodeError as e:
                # This shouldn't happen if decompose_request validated properly, but handle gracefully
                logger.error(f"Unexpected JSON error in assign_and_execute: {str(e)}")
                raise OrganizationError(f"Failed to parse manager response: {str(e)}")
            
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
                    # Pass the full assignment dict to preserve caller and other fields
                    task_info = {
                        "description": assignment.get("task", ""),
                        "caller": assignment.get("caller"),
                    }
                    
                    future = executor.submit(
                        self._execute_single_assignment,
                        role,
                        task_info,
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
            task: Task description or dict with 'description' and optional 'caller'
            original_request: Original user request
            
        Returns:
            Result dict with status and output
        """
        # Extract task description and caller if task is a dict
        if isinstance(task, dict):
            task_description = task.get("description", task.get("task", ""))
            caller = task.get("caller")
        else:
            task_description = task
            caller = None
        
        try:
            # Record task start event
            self.filesystem.record_event(
                self.filesystem.EVENT_TASK_STARTED,
                {
                    "role": role,
                    "task": task_description[:200],  # Truncate for log
                    "caller": caller,
                }
            )
            
            agent = self._create_agent_for_role(role)
            
            # Set callback handler if caller is specified
            if caller:
                def callback_handler(agent_name: str, message: str, callback_type: str) -> Optional[str]:
                    """Handle callbacks from agent to its caller."""
                    logger.info(f"Callback from {agent_name} to {caller}: [{callback_type}] {message[:100]}")
                    
                    # Record callback event
                    self.filesystem.record_event(
                        "AGENT_CALLBACK",
                        {
                            "from": agent_name,
                            "to": caller,
                            "type": callback_type,
                            "message": message[:200],
                        }
                    )
                    
                    # For now, return None - future enhancement could route to actual caller agent
                    # TODO: Implement actual routing to caller agent for response
                    return None
                
                agent.callback_handler = callback_handler
            
            result_text = agent.execute_task({
                "user_prompt": task_description,
            })
            
            # For roles that use tools, execute any tool calls in the response
            tool_results = None
            if role in ["developer", "auditor"]:
                tool_results = agent.execute_tools_from_response(result_text, working_dir=self.filesystem.working_dir)
            
            # Record task completion event
            self.filesystem.record_event(
                self.filesystem.EVENT_TASK_COMPLETED,
                {
                    "role": role,
                    "output_length": len(result_text),
                    "tools_executed": tool_results.get("tools_executed", False) if tool_results else False,
                    "tool_calls": tool_results.get("estimated_tool_calls", 0) if tool_results else 0,
                }
            )
            
            result = {
                "role": role,
                "task": task_description,
                "status": "completed",
                "output": result_text,
            }
            
            if tool_results:
                result["tool_execution"] = tool_results
            
            return result
            
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
    """
    parser = argparse.ArgumentParser(
        prog='ouroboros',
        description='Ouroboros - Multi-Agent Task Coordination System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Build a Hello World app"
      Execute a user request in normal mode
      
  %(prog)s "Create a REST API server" --replay
      Execute using replay mode (uses recorded responses)
      
  %(prog)s --replay
      Run default task in replay mode
      
  %(prog)s
      Run default task: "Build a simple Hello World application"

Features:
  - Multi-agent collaboration with manager, developer, and auditor roles
  - Task decomposition and parallel execution
  - Event sourcing for audit trail and replay
  - Tool-based file operations within sandboxed workspace
  - Callback mechanism for agent-to-agent communication
  - Automatic code review and quality assurance via auditor role

Directory Structure:
  roles.json       Agent role configurations (system prompts, models)
  shared_repo/     Session directories with agent outputs and events
  
For more information, see documentation in docs/
        """
    )
    
    parser.add_argument(
        'request',
        nargs='?',
        default='Build a simple Hello World application',
        help='User request describing the task to execute (default: "Build a simple Hello World application")'
    )
    
    parser.add_argument(
        '--replay',
        action='store_true',
        help='Run in replay mode using previously recorded responses instead of calling LLM'
    )
    
    parser.add_argument(
        '--config',
        metavar='PATH',
        default=None,
        help='Path to roles.json configuration file (default: auto-detect from script location)'
    )
    
    parser.add_argument(
        '--shared-dir',
        metavar='PATH',
        default=None,
        help='Path to shared repository directory for session outputs (default: ../shared_repo or ./shared_repo)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging output'
    )
    
    args = parser.parse_args()
    
    # Adjust logging level if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    try:
        replay_mode = args.replay
        
        # Determine config and shared directory paths
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Use provided config path or auto-detect
        if args.config:
            roles_path = args.config
        elif os.path.exists(os.path.join(script_dir, "roles.json")):
            roles_path = os.path.join(script_dir, "roles.json")
        else:
            roles_path = "roles.json"
        
        # Use provided shared directory or auto-detect
        if args.shared_dir:
            shared_dir = args.shared_dir
        elif os.path.exists(os.path.join(script_dir, "roles.json")):
            shared_dir = os.path.join(os.path.dirname(script_dir), "shared_repo")
        else:
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
        
        # Get user request from parsed arguments
        user_request = args.request
        
        logger.info(f"User Request: {user_request}")
        
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