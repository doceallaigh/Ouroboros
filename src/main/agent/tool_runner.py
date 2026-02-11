"""
Tool execution from agent responses.

Extracts and executes Python code blocks containing tool calls.
"""

import logging
import re
from typing import Dict, Any

from tools import AgentTools, ToolError

logger = logging.getLogger(__name__)


def execute_tools_from_response(agent, response: str, working_dir: str = ".") -> Dict[str, Any]:
    """
    Extract and execute tool calls from an agent's response.
    
    Looks for Python code blocks containing tool calls and executes them.
    
    For developer role:
    - Tracks files produced (write_file, append_file, edit_file calls)
    - Validates audit_files calls only reference produced files
    - Prevents confirm_task_complete calls (developers cannot mark completion)
    
    Args:
        agent: Agent instance
        response: Agent's text response potentially containing tool calls
        working_dir: Working directory for tool operations
        
    Returns:
        Dict with execution results, summary, and tracked metadata
    """
    # Initialize agent tools
    allowed_tools = agent.config.get("allowed_tools")
    tools = AgentTools(working_dir=working_dir, allowed_tools=allowed_tools)
    default_git_branch = agent.config.get("default_git_branch")
    
    # Extract Python code blocks from response
    code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
    
    if not code_blocks:
        logger.debug(f"No Python code blocks found in response from {agent.name}")
        return {
            "tools_executed": False,
            "message": "No tool calls found in response"
        }
    
    results = []
    total_calls = 0
    files_produced = set()  # Track files created/modified
    audit_requests = []  # Track audit requests
    
    def is_allowed(tool_name: str) -> bool:
        return allowed_tools is None or tool_name in allowed_tools

    # Execute each code block
    for code_block in code_blocks:
        # Check for disallowed tool calls in developer role
        if agent.role == "developer":
            if 'confirm_task_complete(' in code_block:
                logger.error(f"Developer {agent.name} attempted to use confirm_task_complete - not allowed")
                results.append({
                    "success": False,
                    "error": "Developers cannot use confirm_task_complete. Task completion must come from manager callback or audit feedback.",
                    "code": code_block[:200]
                })
                continue
        
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
            'print': lambda *args, **kwargs: None,  # Suppress print statements
        }

        if is_allowed("clone_repo"):
            def clone_repo_wrapper(repo_url, dest_dir=None, branch=None, depth=None):
                effective_branch = branch or default_git_branch
                return tools.clone_repo(repo_url, dest_dir=dest_dir, branch=effective_branch, depth=depth)
            exec_globals['clone_repo'] = clone_repo_wrapper
        else:
            def clone_repo_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: clone_repo")
            exec_globals['clone_repo'] = clone_repo_blocked

        if is_allowed("run_python"):
            exec_globals['run_python'] = tools.run_python
        else:
            def run_python_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: run_python")
            exec_globals['run_python'] = run_python_blocked
        
        if is_allowed("checkout_branch"):
            exec_globals['checkout_branch'] = tools.checkout_branch
        else:
            def checkout_branch_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: checkout_branch")
            exec_globals['checkout_branch'] = checkout_branch_blocked

        if is_allowed("raise_callback"):
            from main.agent.callbacks import raise_callback
            exec_globals['raise_callback'] = lambda message, callback_type="query": raise_callback(agent, message, callback_type)
        else:
            def raise_callback_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: raise_callback")
            exec_globals['raise_callback'] = raise_callback_blocked
        
        # Add audit_files wrapper for developers to track audit requests and validate they only audit produced files
        if agent.role == "developer":
            def audit_files_wrapper(file_paths, description="", focus_areas=None):
                # Pass currently produced files to validate the audit
                result = tools.audit_files(file_paths, description, focus_areas, produced_files=list(files_produced))
                audit_requests.append({
                    "files": file_paths,
                    "description": description,
                    "focus_areas": focus_areas or []
                })
                return result
            exec_globals['audit_files'] = audit_files_wrapper
        else:
            exec_globals['audit_files'] = tools.audit_files
        
        # Add confirm_task_complete for non-developer roles
        if agent.role != "developer":
            exec_globals['confirm_task_complete'] = tools.confirm_task_complete
        
        exec_locals = {}
        
        try:
            # Execute the code
            exec(code_block, exec_globals, exec_locals)
            
            # Track file operations for developer role
            if agent.role == "developer":
                for tool_name in ['write_file', 'append_file', 'edit_file']:
                    calls = re.findall(rf'{tool_name}\(["\']([^"\']+)["\']', code_block)
                    files_produced.update(calls)
            
            # Count tool calls (rough estimate based on function calls in code)
            for tool_name in ['read_file', 'write_file', 'append_file', 'edit_file', 
                             'list_directory', 'list_all_files', 'search_files', 
                             'get_file_info', 'delete_file', 'clone_repo', 'checkout_branch', 'run_python',
                             'raise_callback', 'audit_files', 'confirm_task_complete']:
                calls = code_block.count(f'{tool_name}(')
                total_calls += calls
                
                # Track task completion signal
                if tool_name == 'confirm_task_complete' and calls > 0:
                    task_complete_detected = True
            
            results.append({
                "success": True,
                "code_executed": len(code_block),
            })
            logger.info(f"Agent {agent.name} executed tools successfully")
            
        except Exception as e:
            logger.error(f"Tool execution failed for {agent.name}: {e}")
            results.append({
                "success": False,
                "error": str(e),
                "code": code_block[:200]  # Include snippet for debugging
            })
    
    # Check if task completion was signaled
    task_complete_detected = False
    for code_block in code_blocks:
        if 'confirm_task_complete(' in code_block:
            task_complete_detected = True
            break
    
    result_dict = {
        "tools_executed": True,
        "code_blocks_found": len(code_blocks),
        "code_blocks_executed": len([r for r in results if r.get("success")]),
        "estimated_tool_calls": total_calls,
        "results": results,
        "task_complete": task_complete_detected
    }
    
    # Add tracking info for developer role
    if agent.role == "developer":
        result_dict["files_produced"] = list(files_produced)
        result_dict["audit_requests"] = audit_requests
        if audit_requests and not files_produced:
            logger.warning(f"Developer {agent.name} requested audits but produced no files")
    
    return result_dict
