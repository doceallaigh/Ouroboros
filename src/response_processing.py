"""
LLM response processing utilities.

Responsibilities:
- Application-specific transformations of LLM outputs
- Thinking tag removal and domain-specific formatting
- Business logic for response interpretation
"""

import logging
from comms import OutputPostProcessingStrategy

logger = logging.getLogger(__name__)


def remove_thinking_tags(content: str) -> str:
    """
    Remove thinking tags from LLM response content.
    
    Extracts content after </think> tag if present. This is specific
    to LLM models that use thinking tags in their responses.
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Content with thinking tags removed
        
    Examples:
        >>> remove_thinking_tags("Hello")
        "Hello"
        >>> remove_thinking_tags("<think>reasoning</think>\\nAnswer")
        "\\nAnswer"
    """
    if "</think>" in content:
        return content.split("</think>", 1)[1]
    return content


def process_llm_response(content: str) -> str:
    """
    Apply all LLM-specific processing to response content.
    
    This is the main entry point for processing raw LLM responses
    with all application-specific transformations.
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Processed content ready for use
    """
    # Remove thinking tags
    content = remove_thinking_tags(content)
    
    return content


class LLMPostProcessor(OutputPostProcessingStrategy):
    """
    Post-processing strategy for LLM responses.
    
    Inherits: OutputPostProcessingStrategy (from comms module)
    
    Applies application-specific transformations for LLM outputs,
    including thinking tag removal and other domain-specific processing.
    Designed to be injected into the communication layer via dependency injection.
    """
    
    def process(self, content: str) -> str:
        """
        Process LLM response content with all transformations.
        
        Args:
            content: Raw LLM response content
            
        Returns:
            Processed content
        """
        return process_llm_response(content)
