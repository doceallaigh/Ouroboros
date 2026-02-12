"""
Tool execution from agent responses.

Extracts and executes Python code blocks containing tool calls.
"""

import ast
import json
import logging
import re
from typing import Dict, Any, Optional, List, Tuple

from tools import AgentTools, ToolError
from tools.code_runner import CodeRunner

logger = logging.getLogger(__name__)

DEFAULT_PAGE_LINES = 500


def execute_tools_from_response(agent, response: str, working_dir: str = ".", message: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        message: Optional raw message dict with structured tool_calls
        
    Returns:
        Dict with execution results, summary, and tracked metadata
    """
    # Initialize agent tools
    allowed_tools = agent.config.get("allowed_tools")
    tools = AgentTools(working_dir=working_dir, allowed_tools=allowed_tools)
    default_git_branch = agent.config.get("default_git_branch")
    
    # Extract Python code blocks from response
    code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
    structured_tool_calls = []
    if isinstance(message, dict):
        structured_tool_calls = message.get("tool_calls", []) or []

    if not code_blocks and not structured_tool_calls:
        inline_calls = _extract_inline_calls(response, allowed_tools)
        if not inline_calls:
            logger.debug(f"No tool calls found in response from {agent.name}")
            return {
                "tools_executed": False,
                "message": "No tool calls found in response"
            }
    
    results = []
    total_calls = 0
    files_produced = set()  # Track files created/modified
    audit_requests = []  # Track audit requests
    task_complete_detected = False
    tool_outputs = []
    
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
            'read_file': _capture_output_wrapper(
                tool_outputs, "read_file", tools.read_file, supports_page=True
            ),
            'write_file': _capture_output_wrapper(tool_outputs, "write_file", tools.write_file),
            'append_file': _capture_output_wrapper(tool_outputs, "append_file", tools.append_file),
            'edit_file': _capture_output_wrapper(tool_outputs, "edit_file", tools.edit_file),
            'list_directory': _capture_output_wrapper(
                tool_outputs, "list_directory", tools.list_directory, supports_page=True
            ),
            'list_all_files': _capture_output_wrapper(
                tool_outputs, "list_all_files", tools.list_all_files, supports_page=True
            ),
            'search_files': _capture_output_wrapper(
                tool_outputs, "search_files", tools.search_files, supports_page=True
            ),
            'get_file_info': _capture_output_wrapper(
                tool_outputs, "get_file_info", tools.get_file_info, supports_page=True
            ),
            'delete_file': _capture_output_wrapper(tool_outputs, "delete_file", tools.delete_file),
            'print': lambda *args, **kwargs: None,  # Suppress print statements
        }

        if is_allowed("clone_repo"):
            def clone_repo_wrapper(repo_url, dest_dir=None, branch=None, depth=None):
                effective_branch = branch or default_git_branch
                return tools.clone_repo(repo_url, dest_dir=dest_dir, branch=effective_branch, depth=depth)
            exec_globals['clone_repo'] = _capture_output_wrapper(tool_outputs, "clone_repo", clone_repo_wrapper)
        else:
            def clone_repo_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: clone_repo")
            exec_globals['clone_repo'] = clone_repo_blocked

        if is_allowed("run_python"):
            code_runner = CodeRunner()
            exec_globals['run_python'] = _capture_output_wrapper(
                tool_outputs,
                "run_python",
                lambda code, timeout=30, log_path=None: code_runner.run_python(code, working_dir, timeout, log_path),
                supports_page=True,
            )
        else:
            def run_python_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: run_python")
            exec_globals['run_python'] = run_python_blocked
        
        if is_allowed("checkout_branch"):
            exec_globals['checkout_branch'] = _capture_output_wrapper(tool_outputs, "checkout_branch", tools.checkout_branch)
        else:
            def checkout_branch_blocked(*_args, **_kwargs):
                raise ToolError("Tool not allowed for this role: checkout_branch")
            exec_globals['checkout_branch'] = checkout_branch_blocked

        if is_allowed("raise_callback"):
            from main.agent.callbacks import raise_callback
            exec_globals['raise_callback'] = _capture_output_wrapper(
                tool_outputs,
                "raise_callback",
                lambda message, callback_type="query": raise_callback(agent, message, callback_type),
            )
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
            exec_globals['audit_files'] = _capture_output_wrapper(tool_outputs, "audit_files", audit_files_wrapper, supports_page=True)
        else:
            exec_globals['audit_files'] = _capture_output_wrapper(tool_outputs, "audit_files", tools.audit_files, supports_page=True)
        
        # Add confirm_task_complete for non-developer roles
        if agent.role != "developer":
            exec_globals['confirm_task_complete'] = _capture_output_wrapper(
                tool_outputs,
                "confirm_task_complete",
                tools.confirm_task_complete,
            )
        
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

    # Execute structured tool_calls if present
    if structured_tool_calls:
        # Reuse the same exec_globals environment from above if available
        if 'exec_globals' not in locals():
            exec_globals = {
                'read_file': _capture_output_wrapper(tool_outputs, "read_file", tools.read_file, supports_page=True),
                'write_file': _capture_output_wrapper(tool_outputs, "write_file", tools.write_file),
                'append_file': _capture_output_wrapper(tool_outputs, "append_file", tools.append_file),
                'edit_file': _capture_output_wrapper(tool_outputs, "edit_file", tools.edit_file),
                'list_directory': _capture_output_wrapper(tool_outputs, "list_directory", tools.list_directory, supports_page=True),
                'list_all_files': _capture_output_wrapper(tool_outputs, "list_all_files", tools.list_all_files, supports_page=True),
                'search_files': _capture_output_wrapper(tool_outputs, "search_files", tools.search_files, supports_page=True),
                'get_file_info': _capture_output_wrapper(tool_outputs, "get_file_info", tools.get_file_info, supports_page=True),
                'delete_file': _capture_output_wrapper(tool_outputs, "delete_file", tools.delete_file),
                'print': lambda *args, **kwargs: None,
            }

            if is_allowed("clone_repo"):
                def clone_repo_wrapper(repo_url, dest_dir=None, branch=None, depth=None):
                    effective_branch = branch or default_git_branch
                    return tools.clone_repo(repo_url, dest_dir=dest_dir, branch=effective_branch, depth=depth)
                exec_globals['clone_repo'] = _capture_output_wrapper(tool_outputs, "clone_repo", clone_repo_wrapper)
            else:
                def clone_repo_blocked(*_args, **_kwargs):
                    raise ToolError("Tool not allowed for this role: clone_repo")
                exec_globals['clone_repo'] = clone_repo_blocked

            if is_allowed("run_python"):
                code_runner = CodeRunner()
                exec_globals['run_python'] = _capture_output_wrapper(
                    tool_outputs,
                    "run_python",
                    lambda code, timeout=30, log_path=None: code_runner.run_python(code, working_dir, timeout, log_path),
                    supports_page=True,
                )
            else:
                def run_python_blocked(*_args, **_kwargs):
                    raise ToolError("Tool not allowed for this role: run_python")
                exec_globals['run_python'] = run_python_blocked

            if is_allowed("checkout_branch"):
                exec_globals['checkout_branch'] = _capture_output_wrapper(tool_outputs, "checkout_branch", tools.checkout_branch)
            else:
                def checkout_branch_blocked(*_args, **_kwargs):
                    raise ToolError("Tool not allowed for this role: checkout_branch")
                exec_globals['checkout_branch'] = checkout_branch_blocked

            if is_allowed("raise_callback"):
                from main.agent.callbacks import raise_callback
                exec_globals['raise_callback'] = _capture_output_wrapper(
                    tool_outputs,
                    "raise_callback",
                    lambda message, callback_type="query": raise_callback(agent, message, callback_type),
                )
            else:
                def raise_callback_blocked(*_args, **_kwargs):
                    raise ToolError("Tool not allowed for this role: raise_callback")
                exec_globals['raise_callback'] = raise_callback_blocked

            if agent.role == "developer":
                def audit_files_wrapper(file_paths, description="", focus_areas=None):
                    result = tools.audit_files(file_paths, description, focus_areas, produced_files=list(files_produced))
                    audit_requests.append({
                        "files": file_paths,
                        "description": description,
                        "focus_areas": focus_areas or []
                    })
                    return result
                exec_globals['audit_files'] = _capture_output_wrapper(tool_outputs, "audit_files", audit_files_wrapper, supports_page=True)
            else:
                exec_globals['audit_files'] = _capture_output_wrapper(tool_outputs, "audit_files", tools.audit_files, supports_page=True)

            if agent.role != "developer":
                exec_globals['confirm_task_complete'] = _capture_output_wrapper(
                    tool_outputs,
                    "confirm_task_complete",
                    tools.confirm_task_complete,
                )

        for tool_call in structured_tool_calls:
            if tool_call.get("type") != "function":
                continue
            func = tool_call.get("function", {})
            func_name = func.get("name")
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            if not func_name or func_name not in exec_globals:
                results.append({
                    "success": False,
                    "error": f"Unknown tool: {func_name}",
                })
                continue

            try:
                exec_globals[func_name](**(args or {}))
                total_calls += 1
                if agent.role == "developer" and func_name in ("write_file", "append_file", "edit_file"):
                    path = (args or {}).get("path")
                    if path:
                        files_produced.add(path)
                if func_name == "confirm_task_complete":
                    task_complete_detected = True
                results.append({
                    "success": True,
                    "tool": func_name,
                })
                logger.info(f"Agent {agent.name} executed tool call: {func_name}")
            except Exception as e:
                logger.error(f"Tool execution failed for {agent.name}: {e}")
                results.append({
                    "success": False,
                    "tool": func_name,
                    "error": str(e),
                })

    # Execute inline tool calls (plain text) when no code blocks/structured calls
    if not code_blocks and not structured_tool_calls:
        exec_globals = _build_exec_globals(agent, tools, allowed_tools, default_git_branch, working_dir, files_produced, audit_requests)
        inline_calls = _extract_inline_calls(response, allowed_tools)
        for func_name, args, kwargs in inline_calls:
            if agent.role == "developer" and func_name == "confirm_task_complete":
                results.append({
                    "success": False,
                    "tool": func_name,
                    "error": "Developers cannot use confirm_task_complete",
                })
                continue
            if func_name not in exec_globals:
                results.append({
                    "success": False,
                    "tool": func_name,
                    "error": f"Unknown tool: {func_name}",
                })
                continue
            try:
                exec_globals[func_name](*args, **kwargs)
                total_calls += 1
                if agent.role == "developer" and func_name in ("write_file", "append_file", "edit_file"):
                    path = None
                    if kwargs and "path" in kwargs:
                        path = kwargs.get("path")
                    elif args:
                        path = args[0]
                    if path:
                        files_produced.add(path)
                if func_name == "confirm_task_complete":
                    task_complete_detected = True
                results.append({
                    "success": True,
                    "tool": func_name,
                })
                logger.info(f"Agent {agent.name} executed inline tool call: {func_name}")
            except Exception as e:
                logger.error(f"Inline tool execution failed for {agent.name}: {e}")
                results.append({
                    "success": False,
                    "tool": func_name,
                    "error": str(e),
                })
    
    # Check if task completion was signaled via code blocks
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
        "task_complete": task_complete_detected,
        "tool_outputs": tool_outputs
    }
    
    # Add tracking info for developer role
    if agent.role == "developer":
        result_dict["files_produced"] = list(files_produced)
        result_dict["audit_requests"] = audit_requests
        if audit_requests and not files_produced:
            logger.warning(f"Developer {agent.name} requested audits but produced no files")
    
    return result_dict


def _capture_output_wrapper(
    tool_outputs: List[Dict[str, Any]],
    tool_name: str,
    func,
    supports_page: bool = False,
):
    def wrapper(*args, **kwargs):
        page = None
        if supports_page and isinstance(kwargs, dict):
            page = kwargs.pop("page", None)
        result = func(*args, **kwargs)
        page_index = page if isinstance(page, int) and page > 0 else 1
        output_entry = _format_tool_output(tool_name, args, kwargs, result, page_index)
        if output_entry:
            tool_outputs.append(output_entry)
        return result

    return wrapper


def _format_tool_output(
    tool_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    result: Any,
    page_index: int,
) -> Optional[Dict[str, Any]]:
    text = _stringify_tool_output(result)
    if text is None:
        return None
    page_text, total_pages = _paginate_text(text, page_index, DEFAULT_PAGE_LINES)
    return {
        "tool": tool_name,
        "args": list(args),
        "kwargs": kwargs,
        "page": page_index,
        "total_pages": total_pages,
        "page_lines": DEFAULT_PAGE_LINES,
        "content": page_text,
    }


def _stringify_tool_output(result: Any) -> Optional[str]:
    if result is None:
        return None
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, indent=2, ensure_ascii=True)
    except (TypeError, ValueError):
        return str(result)


def _paginate_text(text: str, page: int, lines_per_page: int) -> Tuple[str, int]:
    lines = text.splitlines()
    if not lines:
        return "", 1
    total_pages = max(1, (len(lines) + lines_per_page - 1) // lines_per_page)
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * lines_per_page
    end = start + lines_per_page
    return "\n".join(lines[start:end]), total_pages


def _extract_inline_calls(response: str, allowed_tools: Optional[list]) -> List[Tuple[str, List[Any], Dict[str, Any]]]:
    allowed_names = set(allowed_tools or [])
    calls = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        if not allowed_names or any(line.startswith(f"{name}(") for name in allowed_names):
            try:
                node = ast.parse(line, mode="eval")
            except SyntaxError:
                continue
            call = node.body
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                func_name = call.func.id
                if allowed_names and func_name not in allowed_names:
                    continue
                args = []
                kwargs = {}
                try:
                    for arg in call.args:
                        args.append(ast.literal_eval(arg))
                    for kw in call.keywords:
                        if kw.arg:
                            kwargs[kw.arg] = ast.literal_eval(kw.value)
                except (ValueError, SyntaxError):
                    continue
                calls.append((func_name, args, kwargs))
    return calls


def _build_exec_globals(agent, tools, allowed_tools, default_git_branch, working_dir, files_produced, audit_requests):
    def is_allowed(tool_name: str) -> bool:
        return allowed_tools is None or tool_name in allowed_tools

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
        'print': lambda *args, **kwargs: None,
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
        code_runner = CodeRunner()
        exec_globals['run_python'] = lambda code, timeout=30, log_path=None: code_runner.run_python(code, working_dir, timeout, log_path)
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

    if agent.role == "developer":
        def audit_files_wrapper(file_paths, description="", focus_areas=None):
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

    if agent.role != "developer":
        exec_globals['confirm_task_complete'] = tools.confirm_task_complete

    return exec_globals
