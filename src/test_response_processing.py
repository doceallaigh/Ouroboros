"""
Unit tests for response_processing module.

Tests LLM-specific response processing logic.
"""

import unittest

from response_processing import remove_thinking_tags, process_llm_response, LLMPostProcessor
from comms import OutputPostProcessingStrategy


class TestRemoveThinkingTags(unittest.TestCase):
    """Test cases for remove_thinking_tags function."""

    def test_no_thinking_tags(self):
        """Should return content unchanged when no thinking tags present."""
        content = "Hello world"
        result = remove_thinking_tags(content)
        self.assertEqual(result, "Hello world")

    def test_with_thinking_tags(self):
        """Should extract content after </think> tag."""
        content = "<think>reasoning here</think>\nFinal answer"
        result = remove_thinking_tags(content)
        self.assertEqual(result, "\nFinal answer")

    def test_multiple_think_tags(self):
        """Should only split on first </think> tag."""
        content = "<think>first</think>middle<think>second</think>end"
        result = remove_thinking_tags(content)
        self.assertEqual(result, "middle<think>second</think>end")

    def test_empty_after_tag(self):
        """Should handle empty content after </think> tag."""
        content = "<think>reasoning</think>"
        result = remove_thinking_tags(content)
        self.assertEqual(result, "")

    def test_whitespace_preserved(self):
        """Should preserve whitespace after </think> tag."""
        content = "<think>reasoning</think>   \n\n  Answer  "
        result = remove_thinking_tags(content)
        self.assertEqual(result, "   \n\n  Answer  ")


class TestProcessLLMResponse(unittest.TestCase):
    """Test cases for process_llm_response function."""

    def test_full_processing(self):
        """Should apply all processing steps."""
        content = "<think>internal reasoning</think>Final response"
        result = process_llm_response(content)
        self.assertEqual(result, "Final response")

    def test_no_processing_needed(self):
        """Should return content unchanged if no processing needed."""
        content = "Simple response"
        result = process_llm_response(content)
        self.assertEqual(result, "Simple response")

    def test_empty_string(self):
        """Should handle empty string."""
        result = process_llm_response("")
        self.assertEqual(result, "")


class TestLLMPostProcessor(unittest.TestCase):
    """Test cases for LLMPostProcessor class."""

    def test_implements_strategy_interface(self):
        """Should have process method matching OutputPostProcessingStrategy protocol."""
        processor = LLMPostProcessor()
        self.assertTrue(hasattr(processor, 'process'))
        self.assertTrue(callable(processor.process))
        # Verify protocol implementation
        self.assertIsInstance(processor, OutputPostProcessingStrategy)

    def test_process_with_thinking_tags(self):
        """Should process thinking tags via strategy interface."""
        processor = LLMPostProcessor()
        content = "<think>internal thought</think>Result"
        result = processor.process(content)
        self.assertEqual(result, "Result")

    def test_process_without_tags(self):
        """Should handle content without thinking tags."""
        processor = LLMPostProcessor()
        content = "Plain result"
        result = processor.process(content)
        self.assertEqual(result, "Plain result")

    def test_process_empty_string(self):
        """Should handle empty string."""
        processor = LLMPostProcessor()
        result = processor.process("")
        self.assertEqual(result, "")


if __name__ == '__main__':
    unittest.main()
