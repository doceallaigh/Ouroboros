"""
Unit tests for executor module shared utilities.

Tests parse_model_endpoints and send_llm_request – the shared
communication core used by both execute_task and the agentic loop.
"""

import unittest
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from conftest import MockedNetworkTestCase


class TestParseModelEndpoints(unittest.TestCase):
    """Tests for parse_model_endpoints configuration parsing."""

    def test_uses_model_endpoints_when_present(self):
        from main.agent.executor import parse_model_endpoints
        config = {
            "model_endpoints": [
                {"model": "gpt-4", "endpoint": "http://api.example.com/v1"},
            ]
        }
        result = parse_model_endpoints(config)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["model"], "gpt-4")

    def test_backward_compat_single_strings(self):
        """Should convert old-style model/endpoint strings to model_endpoints."""
        from main.agent.executor import parse_model_endpoints
        config = {
            "model": "gpt-3.5",
            "endpoint": "http://localhost:8000/v1",
        }
        result = parse_model_endpoints(config)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["model"], "gpt-3.5")
        self.assertEqual(result[0]["endpoint"], "http://localhost:8000/v1")

    def test_backward_compat_lists(self):
        """Should zip model and endpoint lists for backward compat."""
        from main.agent.executor import parse_model_endpoints
        config = {
            "model": ["gpt-3.5", "gpt-4"],
            "endpoint": ["http://a.com/v1", "http://b.com/v1"],
        }
        result = parse_model_endpoints(config)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["model"], "gpt-4")

    def test_falls_back_to_defaults(self):
        """Should return a default endpoint if nothing is configured."""
        from main.agent.executor import parse_model_endpoints
        result = parse_model_endpoints({})
        self.assertEqual(len(result), 1)
        self.assertIn("model", result[0])
        self.assertIn("endpoint", result[0])

    def test_empty_model_endpoints_list(self):
        """Empty model_endpoints list should fall through to defaults."""
        from main.agent.executor import parse_model_endpoints
        result = parse_model_endpoints({"model_endpoints": []})
        self.assertEqual(len(result), 1)


class TestSendLLMRequest(MockedNetworkTestCase):
    """Tests for send_llm_request – single-attempt send/receive/record."""

    def setUp(self):
        super().setUp()
        self.mock_agent = Mock()
        self.mock_agent.name = "developer01"
        self.mock_agent.role = "developer"
        self.mock_agent.post_processor = None
        self.mock_channel = Mock()
        self.mock_channel.config = {"endpoint": "http://localhost:12345/v1/chat/completions"}
        self.mock_agent.channel = self.mock_channel
        self.mock_filesystem = Mock()
        self.mock_agent.filesystem = self.mock_filesystem

    def test_returns_response_and_message(self):
        """Should return dict with 'response' and 'message' keys."""
        from main.agent.executor import send_llm_request

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}]
        }
        self.mock_channel.send_message.return_value = {"request_id": "r1"}

        with patch("main.agent.executor.run_async", return_value=mock_resp):
            result = send_llm_request(
                self.mock_agent,
                payload={"messages": [], "model": "gpt-3.5"},
                selected_endpoint="http://localhost:12345/v1/chat/completions",
            )

        self.assertIn("response", result)
        self.assertIn("message", result)
        self.assertEqual(result["response"], "Hello world")

    def test_records_query_file(self):
        """Should call filesystem.create_query_file."""
        from main.agent.executor import send_llm_request

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        self.mock_channel.send_message.return_value = {"request_id": "r1"}

        with patch("main.agent.executor.run_async", return_value=mock_resp):
            send_llm_request(
                self.mock_agent,
                payload={"messages": [], "model": "gpt-3.5"},
                selected_endpoint="http://localhost:12345/v1",
            )

        self.mock_filesystem.create_query_file.assert_called_once()

    def test_records_response_file(self):
        """Should call filesystem.append_response_file."""
        from main.agent.executor import send_llm_request

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "done"}}]
        }
        self.mock_channel.send_message.return_value = {"request_id": "r1"}

        with patch("main.agent.executor.run_async", return_value=mock_resp):
            send_llm_request(
                self.mock_agent,
                payload={"messages": [], "model": "m"},
                selected_endpoint="http://x/v1",
            )

        self.mock_filesystem.append_response_file.assert_called_once()

    def test_handles_tool_calls_in_response(self):
        """Should convert tool_calls to text and include in response."""
        from main.agent.executor import send_llm_request

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Let me write a file",
                    "tool_calls": [{
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "test.py", "content": "x=1"})
                        }
                    }]
                }
            }]
        }
        self.mock_channel.send_message.return_value = {"request_id": "r1"}

        with patch("main.agent.executor.run_async", return_value=mock_resp):
            result = send_llm_request(
                self.mock_agent,
                payload={"messages": [], "model": "m"},
                selected_endpoint="http://x/v1",
            )

        self.assertIn("message", result)
        self.assertIn("write_file", result["response"])

    def test_sets_endpoint_on_channel(self):
        """Should update channel config with selected endpoint."""
        from main.agent.executor import send_llm_request

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        self.mock_channel.send_message.return_value = {"request_id": "r1"}

        with patch("main.agent.executor.run_async", return_value=mock_resp):
            send_llm_request(
                self.mock_agent,
                payload={"messages": [], "model": "m"},
                selected_endpoint="http://custom-endpoint/v1",
            )

        self.assertEqual(
            self.mock_channel.config["endpoint"],
            "http://custom-endpoint/v1"
        )


if __name__ == "__main__":
    unittest.main()
