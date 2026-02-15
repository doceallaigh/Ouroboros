"""
Unit tests for tool_runner module.

Tests the ToolEnvironment class and execute_tools_from_response function.
"""

import unittest
import tempfile
import os
import json
from unittest.mock import Mock, patch, MagicMock

from tools import ToolError


class TestToolEnvironment(unittest.TestCase):
    """Tests for ToolEnvironment - the single-source tool binding builder."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.mock_agent = Mock()
        self.mock_agent.name = "developer01"
        self.mock_agent.role = "developer"
        self.mock_agent.config = {
            "role": "developer",
            "allowed_tools": [
                "read_file", "write_file", "edit_file",
                "list_directory", "list_all_files", "search_files",
                "get_file_info", "delete_file", "confirm_task_complete",
                "audit_files",
            ],
            "default_git_branch": None,
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_env(self, **overrides):
        from main.agent.tool_runner import ToolEnvironment
        config = dict(self.mock_agent.config, **overrides)
        self.mock_agent.config = config
        return ToolEnvironment(
            agent=self.mock_agent,
            working_dir=self.tmpdir,
        )

    # --- Binding construction tests ---

    def test_bindings_contain_core_tools(self):
        """All standard file tools should be present as callables."""
        env = self._make_env()
        bindings = env.get_bindings()
        for name in ["read_file", "write_file", "edit_file",
                      "list_directory", "list_all_files", "search_files",
                      "get_file_info", "delete_file"]:
            self.assertIn(name, bindings, f"Missing binding: {name}")
            self.assertTrue(callable(bindings[name]))

    def test_bindings_built_once(self):
        """get_bindings() should return the same dict on repeated calls."""
        env = self._make_env()
        self.assertIs(env.get_bindings(), env.get_bindings())

    def test_disallowed_tool_raises(self):
        """Calling a tool not in allowed_tools should raise ToolError."""
        env = self._make_env(allowed_tools=["read_file"])
        bindings = env.get_bindings()
        # clone_repo is not in allowed_tools
        self.assertIn("clone_repo", bindings)
        with self.assertRaises(ToolError):
            bindings["clone_repo"]("https://example.com/repo.git")

    def test_clone_repo_default_branch_injected(self):
        """clone_repo should use default_git_branch when no branch given."""
        env = self._make_env(
            allowed_tools=["clone_repo"],
            default_git_branch="main",
        )
        bindings = env.get_bindings()
        # clone_repo doesn't exist on AgentTools yet (pre-existing gap),
        # so we patch it onto the tools instance for this test
        env.tools.clone_repo = Mock(return_value="ok")
        bindings["clone_repo"]("https://example.com/repo.git")
        env.tools.clone_repo.assert_called_once_with(
            "https://example.com/repo.git",
            dest_dir=None, branch="main", depth=None,
        )

    def test_clone_repo_explicit_branch_overrides_default(self):
        """Explicit branch should override default_git_branch."""
        env = self._make_env(
            allowed_tools=["clone_repo"],
            default_git_branch="main",
        )
        bindings = env.get_bindings()
        env.tools.clone_repo = Mock(return_value="ok")
        bindings["clone_repo"]("https://example.com/repo.git", branch="dev")
        env.tools.clone_repo.assert_called_once_with(
            "https://example.com/repo.git",
            dest_dir=None, branch="dev", depth=None,
        )

    def test_print_is_suppressed(self):
        """print() in exec_globals should be a no-op."""
        env = self._make_env()
        bindings = env.get_bindings()
        self.assertIn("print", bindings)
        # Should not raise
        bindings["print"]("hello", "world", end="\n")

    # --- File tracking tests ---

    def test_write_file_tracked(self):
        """write_file() calls should be tracked in files_produced."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("test.txt", "content")
        self.assertIn("test.txt", env.files_produced)

    def test_edit_file_tracked(self):
        """edit_file() calls should be tracked in files_produced."""
        env = self._make_env()
        bindings = env.get_bindings()
        # Create file first
        bindings["write_file"]("test.txt", "hello world")
        env.files_produced.clear()
        bindings["edit_file"]("test.txt", "--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-hello world\n+goodbye world")
        self.assertIn("test.txt", env.files_produced)

    def test_read_file_not_tracked_as_produced(self):
        """read_file() should NOT be listed in files_produced."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("test.txt", "content")
        env.files_produced.clear()
        bindings["read_file"]("test.txt")
        self.assertNotIn("test.txt", env.files_produced)

    def test_file_tracking_for_non_developer_role(self):
        """Non-developer roles should not track files_produced."""
        self.mock_agent.role = "auditor"
        self.mock_agent.config["role"] = "auditor"
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("test.txt", "content")
        # Non-developers don't track
        self.assertEqual(len(env.files_produced), 0)

    # --- Tool output capture tests ---

    def test_tool_output_captured(self):
        """Tool outputs should be captured in env.tool_outputs."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("test.txt", "content")
        self.assertTrue(len(env.tool_outputs) > 0)
        self.assertEqual(env.tool_outputs[0]["tool"], "write_file")

    def test_tool_output_has_pagination(self):
        """Tool outputs for paginated tools should include page info."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("test.txt", "content")
        bindings["read_file"]("test.txt")
        read_output = [o for o in env.tool_outputs if o["tool"] == "read_file"]
        self.assertTrue(len(read_output) > 0)
        self.assertIn("page", read_output[0])
        self.assertIn("total_pages", read_output[0])

    # --- Task completion tests ---

    def test_confirm_task_complete_sets_flag(self):
        """confirm_task_complete() should set env.task_complete = True."""
        env = self._make_env()
        bindings = env.get_bindings()
        self.assertFalse(env.task_complete)
        bindings["confirm_task_complete"]()
        self.assertTrue(env.task_complete)

    # --- Audit tracking tests ---

    def test_developer_audit_files_tracked(self):
        """Developer's audit_files() calls should be tracked in audit_requests."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("app.py", "print('hello')")
        bindings["audit_files"](["app.py"], description="Review code")
        self.assertEqual(len(env.audit_requests), 1)
        self.assertEqual(env.audit_requests[0]["files"], ["app.py"])

    def test_audit_validates_against_produced_files(self):
        """Developer audit_files should pass produced files for validation."""
        env = self._make_env()
        bindings = env.get_bindings()
        bindings["write_file"]("app.py", "print('hello')")
        with patch.object(env.tools, "audit_files", return_value="ok") as mock_audit:
            bindings["audit_files"](["app.py"], description="Review")
            # Verify produced_files was passed
            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args
            self.assertIn("app.py", call_kwargs[1].get("produced_files", call_kwargs[0][3] if len(call_kwargs[0]) > 3 else []))


class TestExecuteToolsFromResponse(unittest.TestCase):
    """Tests for the main execute_tools_from_response function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mock_agent = Mock()
        self.mock_agent.name = "developer01"
        self.mock_agent.role = "developer"
        self.mock_agent.config = {
            "role": "developer",
            "allowed_tools": [
                "read_file", "write_file", "confirm_task_complete",
                "list_directory", "edit_file",
                "list_all_files", "search_files", "get_file_info",
                "delete_file", "audit_files",
            ],
            "default_git_branch": None,
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_tool_calls_returns_not_executed(self):
        """Response with no tool calls should return tools_executed=False."""
        from main.agent.tool_runner import execute_tools_from_response
        result = execute_tools_from_response(
            self.mock_agent, "Just a plain response.", self.tmpdir
        )
        self.assertFalse(result["tools_executed"])

    def test_python_code_block_executed(self):
        """Python code blocks should be extracted and executed."""
        from main.agent.tool_runner import execute_tools_from_response
        response = '```python\nwrite_file("hello.txt", "hello world")\n```'
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertTrue(result["tools_executed"])
        self.assertIn("hello.txt", result.get("files_produced", []))
        # Verify file was actually created
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "hello.txt")))

    def test_structured_tool_calls_executed(self):
        """Structured tool_calls from message dict should be executed."""
        from main.agent.tool_runner import execute_tools_from_response
        message = {
            "content": "",
            "tool_calls": [{
                "type": "function",
                "id": "call_1",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "out.txt", "content": "data"})
                }
            }]
        }
        result = execute_tools_from_response(
            self.mock_agent, "", self.tmpdir, message=message
        )
        self.assertTrue(result["tools_executed"])
        self.assertIn("out.txt", result.get("files_produced", []))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "out.txt")))

    def test_inline_calls_executed(self):
        """Plain-text inline function calls should be parsed and executed."""
        from main.agent.tool_runner import execute_tools_from_response
        response = "write_file('inline.txt', 'inline content')"
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertTrue(result["tools_executed"])
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "inline.txt")))

    def test_task_complete_flag_from_code_block(self):
        """confirm_task_complete() in code block should set task_complete."""
        from main.agent.tool_runner import execute_tools_from_response
        response = '```python\nconfirm_task_complete()\n```'
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertTrue(result["task_complete"])

    def test_task_complete_flag_from_structured_call(self):
        """confirm_task_complete as structured tool call should set task_complete."""
        from main.agent.tool_runner import execute_tools_from_response
        message = {
            "content": "",
            "tool_calls": [{
                "type": "function",
                "id": "call_1",
                "function": {
                    "name": "confirm_task_complete",
                    "arguments": "{}"
                }
            }]
        }
        result = execute_tools_from_response(
            self.mock_agent, "", self.tmpdir, message=message
        )
        self.assertTrue(result["task_complete"])

    def test_failed_code_block_recorded(self):
        """Failed code blocks should be recorded with error info."""
        from main.agent.tool_runner import execute_tools_from_response
        response = '```python\nread_file("nonexistent_dir/file.txt")\n```'
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertTrue(result["tools_executed"])
        failed = [r for r in result["results"] if not r.get("success")]
        self.assertTrue(len(failed) > 0, "Should have at least one failure")

    def test_unknown_structured_tool_recorded(self):
        """Unknown tool names in structured calls should produce error results."""
        from main.agent.tool_runner import execute_tools_from_response
        message = {
            "content": "",
            "tool_calls": [{
                "type": "function",
                "id": "call_1",
                "function": {
                    "name": "nonexistent_tool",
                    "arguments": "{}"
                }
            }]
        }
        result = execute_tools_from_response(
            self.mock_agent, "", self.tmpdir, message=message
        )
        failed = [r for r in result["results"] if not r.get("success")]
        self.assertTrue(len(failed) > 0)
        self.assertIn("Unknown tool", failed[0]["error"])

    def test_tool_outputs_present_in_result(self):
        """Result dict should include tool_outputs list."""
        from main.agent.tool_runner import execute_tools_from_response
        response = '```python\nwrite_file("test.txt", "content")\n```'
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertIn("tool_outputs", result)
        self.assertTrue(len(result["tool_outputs"]) > 0)

    def test_result_dict_structure(self):
        """Result dict should have all expected keys."""
        from main.agent.tool_runner import execute_tools_from_response
        response = '```python\nwrite_file("test.txt", "content")\n```'
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        expected_keys = {
            "tools_executed", "code_blocks_found", "code_blocks_executed",
            "estimated_tool_calls", "results", "task_complete", "tool_outputs",
        }
        for k in expected_keys:
            self.assertIn(k, result, f"Missing key: {k}")
        # Developer-specific keys
        self.assertIn("files_produced", result)
        self.assertIn("audit_requests", result)

    def test_multiple_code_blocks(self):
        """Multiple code blocks should all be executed."""
        from main.agent.tool_runner import execute_tools_from_response
        response = (
            '```python\nwrite_file("a.txt", "aaa")\n```\n'
            'Some text\n'
            '```python\nwrite_file("b.txt", "bbb")\n```'
        )
        result = execute_tools_from_response(
            self.mock_agent, response, self.tmpdir
        )
        self.assertTrue(result["tools_executed"])
        self.assertEqual(result["code_blocks_found"], 2)
        self.assertIn("a.txt", result["files_produced"])
        self.assertIn("b.txt", result["files_produced"])


class TestHelperFunctions(unittest.TestCase):
    """Tests for helper/utility functions in tool_runner."""

    def test_extract_inline_calls_simple(self):
        """Should extract simple inline function calls."""
        from main.agent.tool_runner import _extract_inline_calls
        calls = _extract_inline_calls(
            "write_file('test.txt', 'content')",
            ["write_file", "read_file"]
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "write_file")  # func_name
        self.assertEqual(calls[0][1], ["test.txt", "content"])  # args

    def test_extract_inline_calls_ignores_non_calls(self):
        """Should ignore lines that aren't function calls."""
        from main.agent.tool_runner import _extract_inline_calls
        calls = _extract_inline_calls(
            "This is just plain text\nwrite_file('test.txt', 'content')\nMore text",
            ["write_file"]
        )
        self.assertEqual(len(calls), 1)

    def test_extract_inline_calls_with_kwargs(self):
        """Should handle keyword arguments."""
        from main.agent.tool_runner import _extract_inline_calls
        calls = _extract_inline_calls(
            "read_file('test.txt', page=2)",
            ["read_file"]
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], {"page": 2})

    def test_paginate_text_single_page(self):
        """Short text should be a single page."""
        from main.agent.tool_runner import _paginate_text
        text = "line1\nline2\nline3"
        page_text, total = _paginate_text(text, 1, 500)
        self.assertEqual(total, 1)
        self.assertEqual(page_text, text)

    def test_paginate_text_multiple_pages(self):
        """Long text should paginate correctly."""
        from main.agent.tool_runner import _paginate_text
        text = "\n".join(f"line{i}" for i in range(100))
        page1, total = _paginate_text(text, 1, 25)
        self.assertEqual(total, 4)
        self.assertEqual(len(page1.splitlines()), 25)

        page2, total2 = _paginate_text(text, 2, 25)
        self.assertEqual(total2, 4)
        self.assertNotEqual(page1, page2)

    def test_stringify_tool_output_string(self):
        """String results should pass through."""
        from main.agent.tool_runner import _stringify_tool_output
        self.assertEqual(_stringify_tool_output("hello"), "hello")

    def test_stringify_tool_output_none(self):
        """None results should return None."""
        from main.agent.tool_runner import _stringify_tool_output
        self.assertIsNone(_stringify_tool_output(None))

    def test_stringify_tool_output_dict(self):
        """Dict results should be JSON-serialized."""
        from main.agent.tool_runner import _stringify_tool_output
        result = _stringify_tool_output({"key": "value"})
        self.assertIn('"key"', result)
        self.assertIn('"value"', result)


if __name__ == "__main__":
    unittest.main()
