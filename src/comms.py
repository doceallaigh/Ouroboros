"""
Communications module for agent interaction.

Responsibilities:
- Communication with agents and external APIs
- Input/output sanitization and validation
- Error handling and retry logic
- Message formatting and parsing
"""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, Optional
from httpx import AsyncClient, Response as HTTPXResponse

logger = logging.getLogger(__name__)


class CommunicationError(Exception):
    """Base exception for communication-related errors."""
    pass


class ValidationError(CommunicationError):
    """Raised when message validation fails."""
    pass


class APIError(CommunicationError):
    """Raised when API communication fails."""
    pass


def sanitize_output(content: str, max_length: int = 50000) -> str:
    """
    Sanitize API output for consistency and safety.
    
    Args:
        content: Raw content from API response
        max_length: Maximum allowed content length
        
    Returns:
        Sanitized content string
        
    Raises:
        ValidationError: If content fails validation
    """
    if not isinstance(content, str):
        raise ValidationError(f"Expected string content, got {type(content)}")
    
    # Remove thinking tags (extract content after </think> tag)
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    
    # Truncate if too long
    if len(content) > max_length:
        logger.warning(f"Content truncated from {len(content)} to {max_length} chars")
        content = content[:max_length]
    
    # Remove null bytes and other problematic characters
    content = content.replace('\x00', '')
    
    return content.strip()


def sanitize_input(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize input message structure.
    
    Args:
        message: Message dictionary to validate
        
    Returns:
        Validated and sanitized message
        
    Raises:
        ValidationError: If message structure is invalid
    """
    if not isinstance(message, dict):
        raise ValidationError(f"Message must be dict, got {type(message)}")
    
    if "messages" not in message:
        raise ValidationError("Message must contain 'messages' field")
    
    messages = message.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise ValidationError("'messages' must be non-empty list")
    
    # Sanitize each message in the list
    for msg in messages:
        if not isinstance(msg, dict):
            raise ValidationError("Each message must be a dict")
        if "role" not in msg or "content" not in msg:
            raise ValidationError("Each message must have 'role' and 'content'")
        # Sanitize content
        msg["content"] = sanitize_output(msg["content"], max_length=10000)
    
    return message


def extract_content_from_response(response: HTTPXResponse) -> str:
    """
    Extract content from various API response formats.
    
    Args:
        response: HTTPXResponse object from API
        
    Returns:
        Extracted content string
        
    Raises:
        APIError: If response format is invalid
    """
    if response.status_code != 200:
        raise APIError(f"API returned status {response.status_code}")
    
    try:
        # Try standard OpenAI-style response structure
        result = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        # Fallback to raw body
        try:
            result = response.text
        except Exception:
            result = response.content.decode(errors="replace")
    
    return sanitize_output(result)


class Channel(ABC):
    """Abstract base class for communication channels."""
    
    def __init__(self, config: Dict[str, str]):
        """Initialize channel with configuration."""
        self.config = config
        self.agent_name = config.get("name", "unknown")
    
    @abstractmethod
    def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message through this channel.
        
        Args:
            message: Message payload to send
            
        Raises:
            CommunicationError: If send fails
        """
        pass
    
    @abstractmethod
    async def receive_message(self) -> HTTPXResponse:
        """
        Receive a message response through this channel.
        
        Returns:
            HTTPXResponse object
            
        Raises:
            CommunicationError: If receive fails
        """
        pass


class APIChannel(Channel):
    """Channel for live API communication."""
    
    def __init__(self, config: Dict[str, str]):
        super().__init__(config)
        self.pending_replies = []
        self.timeout = config.get("timeout", 120)
    
    def send_message(self, message: Dict[str, Any]) -> int:
        """Queue message for sending and return ticks identifier."""
        try:
            validated_msg = sanitize_input(message)
            ticks = int(time.time() * 1000)
            # store tuple of (payload, ticks)
            self.pending_replies.append((validated_msg, ticks))
            logger.debug(f"Queued message for {self.agent_name} with ticks={ticks}")
            return ticks
        except ValidationError as e:
            raise CommunicationError(f"Invalid message: {e}")
    
    async def receive_message(self) -> HTTPXResponse:
        """Send queued message and receive response. Stores `last_ticks` attribute on the channel."""
        if not self.pending_replies:
            raise APIError("No pending messages to send")

        payload, ticks = self.pending_replies.pop(0)
        endpoint = self.config.get("endpoint", "http://localhost:12345/v1/chat/completions")

        client = AsyncClient()
        try:
            logger.debug(f"Sending request to {endpoint} (ticks={ticks})")
            response = await client.post(
                url=endpoint,
                json=payload,
                timeout=self.timeout,
            )
            # store ticks for caller to retrieve if needed
            self.last_ticks = ticks
            logger.debug(f"Received response with status {response.status_code} (ticks={ticks})")
            return response
        except asyncio.TimeoutError:
            raise APIError(f"API request timed out after {self.timeout}s")
        except Exception as e:
            raise APIError(f"API request failed: {str(e)}")
        finally:
            await client.aclose()


class ReplayChannel(Channel):
    """Channel for replay mode - retrieves previously recorded responses."""
    
    def __init__(self, config: Dict[str, str], replay_data_loader):
        """
        Initialize replay channel.
        
        Args:
            config: Agent configuration
            replay_data_loader: Callable that retrieves recorded output
        """
        super().__init__(config)
        self.replay_data_loader = replay_data_loader
        # keep pending_replies for ticks tracking similar to APIChannel
        self.pending_replies = []
    
    def send_message(self, message: Dict[str, Any]) -> int:
        """Register a send in replay mode and return ticks."""
        validated_msg = sanitize_input(message)
        ticks = int(time.time() * 1000)
        self.pending_replies.append((validated_msg, ticks))
        logger.debug(f"Replay mode - registered send for {self.agent_name} with ticks={ticks}")
        return ticks
    
    async def receive_message(self) -> HTTPXResponse:
        """Retrieve recorded response. Stores `last_ticks` on the channel if available."""
        try:
            raw = self.replay_data_loader(self.agent_name) or ""
            raw = sanitize_output(raw)
            resp = HTTPXResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                content=raw.encode("utf-8") if isinstance(raw, str) else raw,
            )
            # Pop ticks if available
            ticks = None
            if self.pending_replies:
                _, ticks = self.pending_replies.pop(0)
            self.last_ticks = ticks
            logger.debug(f"Loaded replay data for {self.agent_name} (ticks={ticks})")
            return resp
        except Exception as e:
            raise APIError(f"Failed to load replay data: {e}")


class ChannelFactory:
    """Factory for creating appropriate communication channels."""
    
    def __init__(self, replay_mode: bool, replay_data_loader=None):
        """
        Initialize factory.
        
        Args:
            replay_mode: Whether to use replay mode
            replay_data_loader: Callable for loading replay data
        """
        self.replay_mode = replay_mode
        self.replay_data_loader = replay_data_loader
    
    def create_channel(self, agent_config: Dict[str, str]) -> Channel:
        """
        Create appropriate channel for agent.
        
        Args:
            agent_config: Agent configuration dict
            
        Returns:
            Channel instance
        """
        if self.replay_mode:
            if not self.replay_data_loader:
                raise CommunicationError("Replay mode requires data loader")
            return ReplayChannel(agent_config, self.replay_data_loader)
        else:
            return APIChannel(agent_config)
