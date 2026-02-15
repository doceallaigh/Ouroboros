"""
Tool execution from agent responses.

Extracts and executes tool calls (from code blocks, structured API tool_calls,
or inline plain-text calls) and returns a uniform result dict.

Architecture
------------
``ToolEnvironment`` builds the name -> callable mapping *once* and manages
all shared state (output capture, file tracking, audit tracking, task
completion).  ``execute_tools_from_response`` is the public entry-point;
it delegates to one of three private executors depending on the call format.
"""

import ast
import json
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Set

from tools import AgentTools, ToolError
from tools.code_runner import CodeRunner

logger = logging.getLogger(__name__)

DEFAULT_PAGE_LINES = 500


# ---------------------------------------------------------------------------
# ToolEnvironment – single-source tool binding builder
# ---------------------------------------------------------------------------

class ToolEnvironment:
    """
    Builds and manages the tool execution environment for an agent.

    Responsibilities:
    - Constructs tool name -> callable mapping exactly once.
    - Wraps every callable to capture output and (for developers) track
      produced files via the wrapper rather than regex after the fact.
    - Tracks audit requests and task-completion signals.

    This replaces the three copies of ``exec_globals`` that previously existed.
    """

    def __init__(self, agent, working_dir: str = "."):
        allowed_tools = agent.config.get("allowed_tools")
        default_git_branch = agent.config.get("default_git_branch")

        self.tools = AgentTools(working_dir=working_dir, allowed_tools=allowed_tools)
        self.tool_outputs: List[Dict[str, Any]] = []
        self.files_produced: Set[str] = set()
        self.audit_requests: List[Dict[str, Any]] = []
        self.task_complete: bool = False
        self.total_calls: int = 0

        self._agent = agent
        self._bindings: Dict[str, Any] = {}
        self._build_bindings(agent, allowed_tools, default_git_branch, working_dir)

    # -- public API ----------------------------------------------------------

    def get_bindings(self) -> Dict[str, Any]:
        """Return the tool-name -> callable mapping (same dict every time)."""
        return self._bindings

    # -- private construction ------------------------------------------------

    def _is_allowed(self, tool_name: str, allowed_tools) -> bool:
        return allowed_tools is None or tool_name in (allowed_tools or [])

    def _build_bindings(self, agent, allowed_tools, default_git_branch, working_dir):
        """Build the complete name -> callable mapping."""
        b = self._bindings
        tools = self.tools
        is_developer = agent.role == "developer"

        # ---- Core file tools (always wrapped for output capture) -----------
        CORE_TOOLS = {
            "read_file":      (tools.read_file,      False),
            "write_file":     (tools.write_file,     False),
            "append_file":    (tools.append_file,    False),
            "edit_file":      (tools.edit_file,      False),
            "list_directory": (tools.list_directory, True),
            "list_all_files": (tools.list_all_files, True),
            "search_files":   (tools.search_files,   True),
            "get_file_info":  (tools.get_file_info,  True),
            "delete_file":    (tools.delete_file,    False),
        }

        WRITE_TOOLS = {"write_file", "append_file", "edit_file"}

        for name, (func, supports_page) in CORE_TOOLS.items():
            track_file = is_developer and name in WRITE_TOOLS
            b[name] = self._wrap(name, func, supports_page=supports_page,
                                 track_file=track_file)

        # ---- Suppress print ------------------------------------------------
        b["print"] = lambda *a, **kw: None

        # ---- clone_repo (with default branch injection) --------------------
        if self._is_allowed("clone_repo", allowed_tools):
            def _clone(repo_url, dest_dir=None, branch=None, depth=None):
                effective_branch = branch or default_git_branch
                return tools.clone_repo(repo_url, dest_dir=dest_dir,
                                        branch=effective_branch, depth=depth)
            b["clone_repo"] = self._wrap("clone_repo", _clone)
        else:
            b["clone_repo"] = self._blocked("clone_repo")

        # ---- run_python ----------------------------------------------------
        if self._is_allowed("run_python", allowed_tools):
            code_runner = CodeRunner()
            b["run_python"] = self._wrap(
                "run_python",
                lambda code, timeout=30, log_path=None: code_runner.run_python(
                    code, working_dir, timeout, log_path),
                supports_page=True,
            )
        else:
            b["run_python"] = self._blocked("run_python")

        # ---- checkout_branch -----------------------------------------------
        if self._is_allowed("checkout_branch", allowed_tools):
            b["checkout_branch"] = self._wrap("checkout_branch",
                                              tools.checkout_branch)
        else:
            b["checkout_branch"] = self._blocked("checkout_branch")

        # ---- raise_callback ------------------------------------------------
        if self._is_allowed("raise_callback", allowed_tools):
            from main.agent.callbacks import raise_callback
            b["raise_callback"] = self._wrap(
                "raise_callback",
                lambda message, callback_type="query": raise_callback(
                    agent, message, callback_type),
            )
        else:
            b["raise_callback"] = self._blocked("raise_callback")

        # ---- audit_files ---------------------------------------------------
        if is_developer:
            def _audit_dev(file_paths, description="", focus_areas=None):
                result = tools.audit_files(
                    file_paths, description, focus_areas,
                    produced_files=list(self.files_produced),
                )
                self.audit_requests.append({
                    "files": file_paths,
                    "description": description,
                    "focus_areas": focus_areas or [],
                })
                return result
            b["audit_files"] = self._wrap("audit_files", _audit_dev,
                                          supports_page=True)
        else:
            b["audit_files"] = self._wrap("audit_files", tools.audit_files,
                                          supports_page=True)

        # ---- confirm_task_complete -----------------------------------------
        def _confirm(*a, **kw):
            result = tools.confirm_task_complete(*a, **kw)
            self.task_complete = True
            return result

        b["confirm_task_complete"] = self._wrap(
            "confirm_task_complete", _confirm)

    # -- wrapper helpers -----------------------------------------------------

    def _wrap(self, name: str, func, *, supports_page: bool = False,
              track_file: bool = False):
        """Return a wrapper that captures output and optionally tracks files."""
        env = self  # closure ref

        def wrapper(*args, **kwargs):
            page = None
            if supports_page and isinstance(kwargs, dict):
                page = kwargs.pop("page", None)
            result = func(*args, **kwargs)
            env.total_calls += 1

            # Track file produced (path can be positional or keyword)
            if track_file:
                path = kwargs.get("path") if kwargs and "path" in kwargs else (args[0] if args else None)
                if path:
                    env.files_produced.add(path)

            # Capture output
            page_index = page if isinstance(page, int) and page > 0 else 1
            entry = _format_tool_output(name, args, kwargs, result, page_index)
            if entry:
                env.tool_outputs.append(entry)
            return result

        return wrapper

    @staticmethod
    def _blocked(tool_name: str):
        """Return a callable that raises ToolError for disallowed tools."""
        def _raise(*_a, **_kw):
            raise ToolError(f"Tool not allowed for this role: {tool_name}")
        return _raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def execute_tools_from_response(
    agent,
    response: str,
    working_dir: str = ".",
    message: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract and execute tool calls from an agent's response.

    Looks for (in order of precedence):
    1. Structured ``tool_calls`` in *message*
    2. Python code blocks (```python ... ```)
    3. Inline plain-text function calls

    Returns a dict compatible with all existing callers.
    """
    # Parse inputs
    code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
    structured_tool_calls: list = []
    if isinstance(message, dict):
        structured_tool_calls = message.get("tool_calls", []) or []

    allowed_tools = agent.config.get("allowed_tools")
    inline_calls: List[Tuple[str, list, dict]] = []
    if not code_blocks and not structured_tool_calls:
        inline_calls = _extract_inline_calls(response, allowed_tools)
        if not inline_calls:
            logger.debug(f"No tool calls found in response from {agent.name}")
            return {
                "tools_executed": False,
                "message": "No tool calls found in response",
            }

    # Build environment once
    env = ToolEnvironment(agent, working_dir)
    bindings = env.get_bindings()
    results: List[Dict[str, Any]] = []

    # --- Execute code blocks ------------------------------------------------
    for code_block in code_blocks:
        try:
            exec(code_block, bindings, {})
            results.append({"success": True, "code_executed": len(code_block)})
            logger.info(f"Agent {agent.name} executed tools successfully")
        except Exception as e:
            logger.error(f"Tool execution failed for {agent.name}: {e}")
            results.append({
                "success": False,
                "error": str(e),
                "code": code_block[:200],
            })

    # --- Execute structured tool_calls --------------------------------------
    for tc in structured_tool_calls:
        if tc.get("type") != "function":
            continue
        func = tc.get("function", {})
        func_name = func.get("name")
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}

        if not func_name or func_name not in bindings:
            results.append({"success": False, "tool": func_name,
                            "error": f"Unknown tool: {func_name}"})
            continue

        try:
            bindings[func_name](**(args or {}))
            results.append({"success": True, "tool": func_name})
            logger.info(f"Agent {agent.name} executed tool call: {func_name}")
        except Exception as e:
            logger.error(f"Tool execution failed for {agent.name}: {e}")
            results.append({"success": False, "tool": func_name,
                            "error": str(e)})

    # --- Execute inline calls (fallback) ------------------------------------
    if not code_blocks and not structured_tool_calls:
        for func_name, i_args, i_kwargs in inline_calls:
            if func_name not in bindings:
                results.append({"success": False, "tool": func_name,
                                "error": f"Unknown tool: {func_name}"})
                continue
            try:
                bindings[func_name](*i_args, **i_kwargs)
                results.append({"success": True, "tool": func_name})
                logger.info(
                    f"Agent {agent.name} executed inline tool call: {func_name}")
            except Exception as e:
                logger.error(
                    f"Inline tool execution failed for {agent.name}: {e}")
                results.append({"success": False, "tool": func_name,
                                "error": str(e)})

    # --- Build result dict --------------------------------------------------
    result_dict: Dict[str, Any] = {
        "tools_executed": True,
        "code_blocks_found": len(code_blocks),
        "code_blocks_executed": len([r for r in results if r.get("success")]),
        "estimated_tool_calls": env.total_calls,
        "results": results,
        "task_complete": env.task_complete,
        "tool_outputs": env.tool_outputs,
    }

    if agent.role == "developer":
        result_dict["files_produced"] = list(env.files_produced)
        result_dict["audit_requests"] = env.audit_requests
        if env.audit_requests and not env.files_produced:
            logger.warning(
                f"Developer {agent.name} requested audits but produced no files")

    return result_dict


# ---------------------------------------------------------------------------
# Helpers (unchanged public interface for imports)
# ---------------------------------------------------------------------------

def _capture_output_wrapper(
    tool_outputs: List[Dict[str, Any]],
    tool_name: str,
    func,
    supports_page: bool = False,
):
    """Legacy wrapper – kept for any external callers."""
    def wrapper(*args, **kwargs):
        page = None
        if supports_page and isinstance(kwargs, dict):
            page = kwargs.pop("page", None)
        result = func(*args, **kwargs)
        page_index = page if isinstance(page, int) and page > 0 else 1
        output_entry = _format_tool_output(tool_name, args, kwargs, result,
                                           page_index)
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


def _extract_inline_calls(
    response: str, allowed_tools: Optional[list],
) -> List[Tuple[str, List[Any], Dict[str, Any]]]:
    allowed_names = set(allowed_tools or [])
    calls: List[Tuple[str, list, dict]] = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        if not allowed_names or any(
            line.startswith(f"{name}(") for name in allowed_names
        ):
            try:
                node = ast.parse(line, mode="eval")
            except SyntaxError:
                continue
            call = node.body
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                func_name = call.func.id
                if allowed_names and func_name not in allowed_names:
                    continue
                args: list = []
                kwargs: dict = {}
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
