"""
Git repository control for coordinators.

Handles git repository detection, branch management, and workflow finalization.
"""

import logging
import os
import subprocess
from typing import Optional

from tools import AgentTools

logger = logging.getLogger(__name__)


def is_git_repository(filesystem) -> bool:
    """
    Check if the current working directory is a git repository.
    
    Args:
        filesystem: Filesystem instance
        
    Returns:
        True if .git directory exists, False otherwise
    """
    work_dir = filesystem.working_dir
    if not isinstance(work_dir, (str, bytes, os.PathLike)):
        return False
    git_dir = os.path.join(work_dir, ".git")
    return os.path.exists(git_dir) and os.path.isdir(git_dir)


def get_current_git_branch(filesystem) -> Optional[str]:
    """
    Get the current git branch name.
    
    Args:
        filesystem: Filesystem instance
        
    Returns:
        Branch name or None if not in a git repo or on error
    """
    if not is_git_repository(filesystem):
        return None

    try:
        work_dir = filesystem.working_dir
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=work_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Failed to get current git branch: {e}")

    return None


def finalize_git_workflow(coordinator) -> None:
    """
    Push the current branch and create a pull request if applicable.
    
    This is called at the end of assign_and_execute after all tasks complete.
    Only executes if:
    - Working in a git repository
    - Current branch is not a default branch (main, master, develop)
    - Git tools are allowed
    
    Args:
        coordinator: CentralCoordinator instance
    """
    if not coordinator.allow_git_tools:
        logger.debug("Git tools disabled, skipping git finalization")
        return

    branch_name = get_current_git_branch(coordinator.filesystem)
    if not branch_name:
        logger.debug("Not in a git repository, skipping git finalization")
        return

    # Skip if on a default branch
    default_branches = {"main", "master", "develop", "development"}
    if branch_name in default_branches:
        logger.debug(f"On default branch '{branch_name}', skipping git finalization")
        return

    logger.info("=" * 80)
    logger.info("GIT WORKFLOW FINALIZATION")
    logger.info("=" * 80)
    logger.info(f"Current branch: {branch_name}")

    work_dir = coordinator.filesystem.working_dir
    tools = AgentTools(working_dir=work_dir)

    # Step 1: Push the branch
    try:
        logger.info(f"Pushing branch '{branch_name}' to remote...")
        push_result = tools.push_branch(repo_dir=".", branch_name=branch_name)
        if push_result.get("success"):
            logger.info(f"✓ Branch pushed to {push_result.get('remote', 'origin')}")
        else:
            logger.warning("Branch push reported failure")
            return
    except Exception as e:
        logger.warning(f"Failed to push branch: {e}")
        logger.info("Skipping pull request creation due to push failure")
        return

    # Step 2: Create pull request
    try:
        logger.info("Creating pull request...")
        pr_result = tools.create_pull_request(
            repo_dir=".",
            title=None,  # Will auto-generate from branch name
            body="Automated pull request created by Ouroboros agent system.",
            base_branch="main"
        )
    
        if pr_result.get("success"):
            if pr_result.get("already_exists"):
                logger.info("✓ Pull request already exists for this branch")
            else:
                pr_url = pr_result.get("pr_url", "unknown")
                logger.info(f"✓ Pull request created: {pr_url}")
        else:
            logger.warning("Pull request creation reported failure")
    except Exception as e:
        logger.warning(f"Failed to create pull request: {e}")
        logger.info("This may be expected if GitHub CLI is not installed or configured")

    logger.info("=" * 80)
