"""
Unit tests for comms module.

Tests communication channels, sanitization functions, and error handling.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
from httpx import Response as HTTPXResponse

from comms import (
    sanitize_input,
    sanitize_output,
    extract_content_from_response,
    DefaultOutputSanitizationStrategy,
    DefaultInputSanitizationStrategy,
    OutputPostProcessingStrategy,
    InputPreProcessingStrategy,
    Channel,
    APIChannel,
    ReplayChannel,
    ChannelFactory,
    CommunicationError,
    ValidationError,
    APIError,
)
from .response_processing import LLMPostProcessor


class TestDefaultOutputSanitizationStrategy(unittest.TestCase):
    """Test cases for DefaultOutputSanitizationStrategy class."""

    def test_valid_string(self):
        """Should return cleaned string for valid input."""
        strategy = DefaultOutputSanitizationStrategy()
        result = strategy.process("Hello world")
        self.assertEqual(result, "Hello world")

    def test_truncate_long_content(self):
        """Should truncate content exceeding max_length."""
        strategy = DefaultOutputSanitizationStrategy(max_length=100)
        long_string = "a" * 1000
        result = strategy.process(long_string)
        self.assertEqual(len(result), 100)

    def test_remove_null_bytes(self):
        """Should remove null bytes from content."""
        strategy = DefaultOutputSanitizationStrategy()
        content = "Hello\x00world"
        result = strategy.process(content)
        self.assertEqual(result, "Helloworld")

    def test_strip_whitespace(self):
        """Should strip leading and trailing whitespace."""
        strategy = DefaultOutputSanitizationStrategy()
        content = "  Hello world  \n"
        result = strategy.process(content)
        self.assertEqual(result, "Hello world")

    def test_invalid_type_raises_error(self):
        """Should raise ValidationError for non-string input."""
        strategy = DefaultOutputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            strategy.process(12345)

    def test_none_raises_error(self):
        """Should raise ValidationError for None input."""
        strategy = DefaultOutputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            strategy.process(None)

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        strategy = DefaultOutputSanitizationStrategy(max_length=50)
        long_string = "x" * 1000
        result = strategy.process(long_string)
        self.assertEqual(len(result), 50)

    def test_implements_protocol(self):
        """Should have process method matching OutputPostProcessingStrategy protocol."""
        strategy = DefaultOutputSanitizationStrategy()
        self.assertTrue(hasattr(strategy, 'process'))
        self.assertTrue(callable(strategy.process))
        # Verify protocol implementation
        self.assertIsInstance(strategy, OutputPostProcessingStrategy)


class TestDefaultInputSanitizationStrategy(unittest.TestCase):
    """Test cases for DefaultInputSanitizationStrategy class."""

    def test_valid_message(self):
        """Should return validated message unchanged."""
        sanitizer = DefaultInputSanitizationStrategy()
        message = {
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"}
            ]
        }
        result = sanitizer.process(message)
        self.assertEqual(len(result["messages"]), 2)

    def test_non_dict_input_raises_error(self):
        """Should raise ValidationError for non-dict input."""
        sanitizer = DefaultInputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            sanitizer.process(["not", "a", "dict"])

    def test_missing_messages_field_raises_error(self):
        """Should raise ValidationError when messages field missing."""
        sanitizer = DefaultInputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            sanitizer.process({"data": "value"})

    def test_empty_messages_list_raises_error(self):
        """Should raise ValidationError for empty messages list."""
        sanitizer = DefaultInputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            sanitizer.process({"messages": []})

    def test_invalid_message_structure_raises_error(self):
        """Should raise ValidationError for invalid message structure."""
        sanitizer = DefaultInputSanitizationStrategy()
        with self.assertRaises(ValidationError):
            sanitizer.process({"messages": [{"role": "user"}]})  # missing content

    def test_sanitizes_content(self):
        """Should sanitize content in each message."""
        sanitizer = DefaultInputSanitizationStrategy()
        message = {
            "messages": [
                {"role": "user", "content": "  Hello\x00world  "}
            ]
        }
        result = sanitizer.process(message)
        # Content should be sanitized (null bytes removed, whitespace trimmed)
        self.assertEqual(result["messages"][0]["content"], "Helloworld")

    def test_truncates_long_content(self):
        """Should truncate content exceeding max_length."""
        sanitizer = DefaultInputSanitizationStrategy()
        long_content = "a" * 60000
        message = {
            "messages": [
                {"role": "user", "content": long_content}
            ]
        }
        result = sanitizer.process(message)
        # Should be truncated to 50000 (default max for input)
        self.assertEqual(len(result["messages"][0]["content"]), 50000)

    def test_implements_protocol(self):
        """Should have process method matching InputPreProcessingStrategy protocol."""
        sanitizer = DefaultInputSanitizationStrategy()
        self.assertTrue(hasattr(sanitizer, 'process'))
        self.assertTrue(callable(sanitizer.process))
        # Verify protocol implementation
        self.assertIsInstance(sanitizer, InputPreProcessingStrategy)


class TestSanitizeOutput(unittest.TestCase):
    """Test cases for sanitize_output function."""

    def test_valid_string(self):
        """Should return cleaned string for valid input."""
        result = sanitize_output("Hello world")
        self.assertEqual(result, "Hello world")

    def test_truncate_long_content(self):
        """Should truncate content exceeding max_length."""
        long_string = "a" * 100000
        result = sanitize_output(long_string, max_length=50000)
        self.assertEqual(len(result), 50000)

    def test_remove_null_bytes(self):
        """Should remove null bytes from content."""
        content = "Hello\x00world"
        result = sanitize_output(content)
        self.assertEqual(result, "Helloworld")

    def test_strip_whitespace(self):
        """Should strip leading and trailing whitespace."""
        content = "  Hello world  \n"
        result = sanitize_output(content)
        self.assertEqual(result, "Hello world")

    def test_invalid_type_raises_error(self):
        """Should raise ValidationError for non-string input."""
        with self.assertRaises(ValidationError):
            sanitize_output(12345)

    def test_none_raises_error(self):
        """Should raise ValidationError for None input."""
        with self.assertRaises(ValidationError):
            sanitize_output(None)

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        long_string = "x" * 1000
        result = sanitize_output(long_string, max_length=100)
        self.assertEqual(len(result), 100)


class TestSanitizeInput(unittest.TestCase):
    """Test cases for sanitize_input function."""

    def test_valid_message(self):
        """Should return valid message unchanged."""
        message = {
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"}
            ]
        }
        result = sanitize_input(message)
        self.assertIn("messages", result)
        self.assertEqual(len(result["messages"]), 2)

    def test_missing_messages_field(self):
        """Should raise ValidationError if 'messages' field missing."""
        message = {"model": "gpt-3.5"}
        with self.assertRaises(ValidationError):
            sanitize_input(message)

    def test_empty_messages_list(self):
        """Should raise ValidationError for empty messages list."""
        message = {"messages": []}
        with self.assertRaises(ValidationError):
            sanitize_input(message)

    def test_invalid_message_structure(self):
        """Should raise ValidationError for invalid message structure."""
        message = {
            "messages": [
                {"role": "user"}  # Missing 'content'
            ]
        }
        with self.assertRaises(ValidationError):
            sanitize_input(message)

    def test_non_dict_input(self):
        """Should raise ValidationError for non-dict input."""
        with self.assertRaises(ValidationError):
            sanitize_input("not a dict")

    def test_sanitizes_content(self):
        """Should sanitize message content."""
        message = {
            "messages": [
                {"role": "user", "content": "  Hello  \n"}
            ]
        }
        result = sanitize_input(message)
        self.assertEqual(result["messages"][0]["content"], "Hello")

    def test_truncates_long_content(self):
        """Should truncate long message content."""
        long_content = "x" * 60000
        message = {
            "messages": [
                {"role": "user", "content": long_content}
            ]
        }
        result = sanitize_input(message)
        self.assertLess(len(result["messages"][0]["content"]), len(long_content))


class TestExtractContentFromResponse(unittest.TestCase):
    """Test cases for extract_content_from_response function."""

    def test_openai_format(self):
        """Should extract content from OpenAI format response."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "AI response"
                    }
                }
            ]
        }
        result = extract_content_from_response(response)
        self.assertEqual(result, "AI response")

    def test_plain_text_response(self):
        """Should extract plain text response."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.side_effect = ValueError()  # Not JSON
        response.text = "Plain text response"
        result = extract_content_from_response(response)
        self.assertEqual(result, "Plain text response")

    def test_thinking_tags(self):
        """Should extract content after </think> tag when processor provided."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "<think>reasoning here</think>\nFinal answer"
                    }
                }
            ]
        }
        processor = LLMPostProcessor()
        result = extract_content_from_response(response, processor)
        self.assertEqual(result, "Final answer")
    
    def test_no_processor(self):
        """Should not process thinking tags when no processor provided."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "<think>reasoning here</think>\nFinal answer"
                    }
                }
            ]
        }
        result = extract_content_from_response(response)
        # Without processor, thinking tags should remain
        self.assertIn("<think>", result)
        self.assertIn("Final answer", result)    
    def test_strategy_composition(self):
        """Should compose post-processor with default sanitization."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        # Content with thinking tags + null bytes + whitespace
                        "content": "<think>reasoning</think>\nAnswer\x00text  \n"
                    }
                }
            ]
        }
        processor = LLMPostProcessor()
        result = extract_content_from_response(response, processor)
        # Should have removed thinking tags (via LLMPostProcessor)
        self.assertNotIn("<think>", result)
        # Should have removed null bytes (via DefaultOutputSanitizationStrategy)
        self.assertNotIn("\x00", result)
        # Should have trimmed whitespace (via DefaultOutputSanitizationStrategy)
        self.assertEqual(result, "Answertext")
    def test_non_200_status_raises_error(self):
        """Should raise APIError for non-200 status."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 500
        with self.assertRaises(APIError):
            extract_content_from_response(response)

    def test_missing_choices_structure(self):
        """Should fallback to text for missing OpenAI structure."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.side_effect = KeyError()
        response.text = "Fallback text"
        result = extract_content_from_response(response)
        self.assertEqual(result, "Fallback text")

    def test_sanitizes_output(self):
        """Should sanitize extracted content."""
        response = Mock(spec=HTTPXResponse)
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "  Response  \n"
                    }
                }
            ]
        }
        result = extract_content_from_response(response)
        self.assertEqual(result, "Response")


class TestAPIChannel(unittest.TestCase):
    """Test cases for APIChannel class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "name": "test_agent",
            "endpoint": "http://localhost:8000/api",
            "timeout": 60,
        }
        self.channel = APIChannel(self.config)

    def test_initialization(self):
        """Should initialize with config."""
        self.assertEqual(self.channel.agent_name, "test_agent")
        self.assertEqual(self.channel.timeout, 60)
        self.assertEqual(self.channel.pending_replies, [])

    def test_send_message_valid(self):
        """Should queue valid message."""
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        self.channel.send_message(message)
        self.assertEqual(len(self.channel.pending_replies), 1)

    def test_send_message_invalid_raises_error(self):
        """Should raise CommunicationError for invalid message."""
        message = {"invalid": "structure"}
        with self.assertRaises(CommunicationError):
            self.channel.send_message(message)

    @patch('comms.resilience.AsyncClient')
    def test_receive_message_success(self, mock_client_class):
        """Should receive and return message successfully."""
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        mock_response = Mock(spec=HTTPXResponse)
        mock_response.status_code = 200
        
        async def mock_post(*args, **kwargs):
            return mock_response
        
        mock_client.post = mock_post
        mock_client.aclose = AsyncMock()
        
        # Queue a message
        message = {
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "gpt-3.5"
        }
        self.channel.send_message(message)
        
        # Receive message
        result = asyncio.run(self.channel.receive_message())
        self.assertEqual(result, mock_response)

    @patch('comms.channel.AsyncClient')
    def test_receive_message_no_pending_raises_error(self, mock_client_class):
        """Should raise APIError when no pending messages."""
        with self.assertRaises(APIError):
            asyncio.run(self.channel.receive_message())

    def test_receive_message_timeout_config(self):
        """Should use configured timeout."""
        config_with_timeout = {
            "name": "agent",
            "timeout": 300
        }
        channel = APIChannel(config_with_timeout)
        self.assertEqual(channel.timeout, 300)


class TestReplayChannel(unittest.TestCase):
    """Test cases for ReplayChannel class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {"name": "test_agent"}
        self.mock_loader = Mock(return_value="Recorded response")
        self.channel = ReplayChannel(self.config, self.mock_loader)

    def test_initialization(self):
        """Should initialize with config and loader."""
        self.assertEqual(self.channel.agent_name, "test_agent")
        self.assertIsNotNone(self.channel.replay_data_loader)

    def test_send_message_noop(self):
        """Should be no-op for send_message."""
        message = {"messages": [{"role": "user", "content": "Hello"}]}
        # Should not raise any error
        self.channel.send_message(message)

    def test_receive_message_loads_data(self):
        """Should load data from replay loader."""
        result = asyncio.run(self.channel.receive_message())
        self.mock_loader.assert_called_once_with("test_agent")
        self.assertEqual(result.status_code, 200)

    def test_receive_message_handles_missing_data(self):
        """Should handle missing replay data."""
        self.mock_loader.return_value = None
        result = asyncio.run(self.channel.receive_message())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, b"")

    def test_receive_message_returns_httpx_response(self):
        """Should return HTTPXResponse object."""
        result = asyncio.run(self.channel.receive_message())
        self.assertIsInstance(result, HTTPXResponse)
        self.assertEqual(result.headers["Content-Type"], "application/json")

    def test_receive_message_sanitizes_output(self):
        """Should sanitize loaded data."""
        self.mock_loader.return_value = "  Recorded response  \n"
        result = asyncio.run(self.channel.receive_message())
        content = result.content.decode("utf-8")
        self.assertEqual(content, "Recorded response")


class TestChannelFactory(unittest.TestCase):
    """Test cases for ChannelFactory class."""

    def test_create_api_channel_live_mode(self):
        """Should create APIChannel in live mode."""
        factory = ChannelFactory(replay_mode=False)
        config = {"name": "test_agent"}
        channel = factory.create_channel(config)
        self.assertIsInstance(channel, APIChannel)

    def test_create_replay_channel_replay_mode(self):
        """Should create ReplayChannel in replay mode."""
        loader = Mock()
        factory = ChannelFactory(replay_mode=True, replay_data_loader=loader)
        config = {"name": "test_agent"}
        channel = factory.create_channel(config)
        self.assertIsInstance(channel, ReplayChannel)

    def test_replay_mode_requires_loader(self):
        """Should raise error if replay mode without loader."""
        factory = ChannelFactory(replay_mode=True, replay_data_loader=None)
        config = {"name": "test_agent"}
        with self.assertRaises(CommunicationError):
            factory.create_channel(config)

    def test_live_mode_ignores_loader(self):
        """Should ignore loader in live mode."""
        loader = Mock()
        factory = ChannelFactory(replay_mode=False, replay_data_loader=loader)
        config = {"name": "test_agent"}
        channel = factory.create_channel(config)
        self.assertIsInstance(channel, APIChannel)


class TestExceptionHierarchy(unittest.TestCase):
    """Test cases for exception hierarchy."""

    def test_validation_error_is_communication_error(self):
        """ValidationError should be a CommunicationError."""
        error = ValidationError("test")
        self.assertIsInstance(error, CommunicationError)

    def test_api_error_is_communication_error(self):
        """APIError should be a CommunicationError."""
        error = APIError("test")
        self.assertIsInstance(error, CommunicationError)

    def test_catch_communication_error(self):
        """Should catch all communication errors with base exception."""
        errors = [
            ValidationError("validation"),
            APIError("api"),
            CommunicationError("general")
        ]
        
        for error in errors:
            with self.assertRaises(CommunicationError):
                raise error


if __name__ == "__main__":
    unittest.main()
