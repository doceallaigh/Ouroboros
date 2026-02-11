"""
Main entry point for the Ouroboros agent harness.

This module serves as the CLI entry point and orchestrates multi-agent collaboration.
The actual implementation is modularized:
- main.agent: Agent execution with tools, retries, and callbacks
- main.coordinator: Multi-agent orchestration and task decomposition
- main.git: Git repository operations
- main.exceptions: Custom exceptions

Responsibilities (delegated to submodules):
- Orchestration of multi-agent collaboration
- Task decomposition and assignment
- Result aggregation and coordination
- Application lifecycle management
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

from comms import APIError, CommunicationError, ChannelFactory, OutputPostProcessingStrategy, extract_content_from_response
from comms.response_processing import LLMPostProcessor
from fileio import FileSystem, FileSystemError, ReadOnlyFileSystem
from tools import AgentTools, ToolError, get_tools_description

from .exceptions import OrganizationError
from .coordinator import CentralCoordinator
from .agent import Agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

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
        '--repo',
        metavar='URL_OR_PATH',
        default=None,
        help='Git repository URL or local path to clone/use for this run'
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

        repo_working_dir = None
        allow_git_tools = False
        if args.repo:
            try:
                if os.path.isdir(args.repo) and os.path.isdir(os.path.join(args.repo, ".git")):
                    repo_working_dir = os.path.abspath(args.repo)
                    allow_git_tools = True
                    logger.info(f"Using local repository: {repo_working_dir}")
                else:
                    tools = AgentTools(working_dir=filesystem.src_dir, allowed_tools=["clone_repo"])
                    clone_result = tools.clone_repo(args.repo)
                    repo_working_dir = clone_result["absolute_path"]
                    allow_git_tools = True
                    logger.info(f"Cloned repository to: {repo_working_dir}")
            except (ToolError, FileSystemError) as e:
                logger.error(f"Repository setup failed: {e}")
                sys.exit(1)
        else:
            logger.info("No repository provided; git tools disabled")
        
        # Initialize post-processor for LLM responses
        post_processor = LLMPostProcessor()
        
        # Initialize coordinator
        try:
            coordinator = CentralCoordinator(
                config_path=roles_path,
                filesystem=filesystem,
                replay_mode=replay_mode,
                repo_working_dir=repo_working_dir,
                allow_git_tools=allow_git_tools,
                post_processor=post_processor,
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

__all__ = ["main", "CentralCoordinator", "Agent", "OrganizationError"]
