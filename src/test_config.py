"""
Unit tests for config module.

Tests configuration loading, retrieval, and validation.
"""

import unittest
import json
import tempfile
import os
from unittest.mock import patch, mock_open

from config import (
    load_config,
    get_config_value,
    validate_agent_config,
    ConfigError,
)


class TestLoadConfig(unittest.TestCase):
    """Test cases for load_config function."""

    def test_load_valid_json_config(self):
        """Should load valid JSON configuration file."""
        config_data = {
            "agent1": {
                "name": "Agent 1",
                "role": "developer"
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
            with patch('config.json.load', return_value=config_data):
                config = load_config("config.json")
                self.assertEqual(config, config_data)

    def test_load_config_file_not_found(self):
        """Should raise ConfigError if file not found."""
        with patch('builtins.open', side_effect=FileNotFoundError()):
            with self.assertRaises(ConfigError):
                load_config("nonexistent.json")

    def test_load_config_invalid_json(self):
        """Should raise ConfigError for invalid JSON."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            with patch('config.json.load', side_effect=json.JSONDecodeError("", "", 0)):
                with self.assertRaises(ConfigError):
                    load_config("invalid.json")

    def test_load_config_empty_file(self):
        """Should handle empty config file."""
        with patch('builtins.open', mock_open(read_data="{}")):
            with patch('config.json.load', return_value={}):
                config = load_config("empty.json")
                self.assertEqual(config, {})

    def test_load_config_complex_structure(self):
        """Should load complex nested configuration."""
        config_data = {
            "agents": {
                "manager": {
                    "name": "Manager",
                    "config": {
                        "timeout": 120,
                        "retries": 3
                    }
                }
            },
            "settings": {
                "debug": True,
                "log_level": "INFO"
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
            with patch('config.json.load', return_value=config_data):
                config = load_config("complex.json")
                self.assertEqual(config, config_data)


class TestGetConfigValue(unittest.TestCase):
    """Test cases for get_config_value function."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "credentials": {
                    "user": "admin",
                    "password": "secret"
                }
            },
            "api": {
                "endpoint": "http://api.example.com",
                "timeout": 30
            }
        }

    def test_get_simple_value(self):
        """Should retrieve simple value."""
        value = get_config_value(self.config, "api.endpoint")
        self.assertEqual(value, "http://api.example.com")

    def test_get_nested_value(self):
        """Should retrieve deeply nested value."""
        value = get_config_value(self.config, "database.credentials.user")
        self.assertEqual(value, "admin")

    def test_get_nonexistent_value_returns_default(self):
        """Should return default for nonexistent key."""
        value = get_config_value(self.config, "nonexistent.key", "default_value")
        self.assertEqual(value, "default_value")

    def test_get_value_with_none_default(self):
        """Should return None as default."""
        value = get_config_value(self.config, "nonexistent.key", None)
        self.assertIsNone(value)

    def test_get_value_without_default(self):
        """Should return None if no default specified."""
        value = get_config_value(self.config, "nonexistent.key")
        self.assertIsNone(value)

    def test_get_numeric_value(self):
        """Should retrieve numeric values."""
        value = get_config_value(self.config, "database.port")
        self.assertEqual(value, 5432)

    def test_get_boolean_value(self):
        """Should retrieve boolean values."""
        config = {"debug": True}
        value = get_config_value(config, "debug")
        self.assertTrue(value)

    def test_get_value_partial_path_returns_default(self):
        """Should return default when path is partial."""
        value = get_config_value(
            self.config,
            "database.credentials.username",
            "default"
        )
        self.assertEqual(value, "default")

    def test_get_value_non_dict_intermediate(self):
        """Should return default when intermediate value is not dict."""
        value = get_config_value(
            self.config,
            "database.port.something",
            "default"
        )
        self.assertEqual(value, "default")

    def test_get_all_nested_dict(self):
        """Should retrieve entire nested dictionary."""
        value = get_config_value(self.config, "database.credentials")
        self.assertEqual(value, {"user": "admin", "password": "secret"})


class TestValidateAgentConfig(unittest.TestCase):
    """Test cases for validate_agent_config function."""

    def test_validate_valid_agent_config(self):
        """Should validate correct agent configuration."""
        agent_config = {
            "name": "Developer Agent",
            "role": "developer",
            "system_prompt": "You are a developer"
        }
        
        result = validate_agent_config(agent_config)
        self.assertTrue(result)

    def test_validate_config_missing_name(self):
        """Should raise ConfigError if name missing."""
        agent_config = {
            "role": "developer",
            "system_prompt": "You are a developer"
        }
        
        with self.assertRaises(ConfigError):
            validate_agent_config(agent_config)

    def test_validate_config_missing_role(self):
        """Should raise ConfigError if role missing."""
        agent_config = {
            "name": "Developer Agent",
            "system_prompt": "You are a developer"
        }
        
        with self.assertRaises(ConfigError):
            validate_agent_config(agent_config)

    def test_validate_config_missing_system_prompt(self):
        """Should raise ConfigError if system_prompt missing."""
        agent_config = {
            "name": "Developer Agent",
            "role": "developer"
        }
        
        with self.assertRaises(ConfigError):
            validate_agent_config(agent_config)

    def test_validate_config_extra_fields_allowed(self):
        """Should validate config with extra optional fields."""
        agent_config = {
            "name": "Developer Agent",
            "role": "developer",
            "system_prompt": "You are a developer",
            "model_endpoints": [
                {"model": "gpt-3.5", "endpoint": "http://api.example.com"}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        result = validate_agent_config(agent_config)
        self.assertTrue(result)

    def test_validate_config_empty_dict(self):
        """Should raise ConfigError for empty config."""
        with self.assertRaises(ConfigError):
            validate_agent_config({})

    def test_validate_config_with_additional_metadata(self):
        """Should validate config with additional metadata fields."""
        agent_config = {
            "name": "Developer Agent",
            "role": "developer",
            "system_prompt": "You are a developer",
            "model_endpoints": [
                {"model": "gpt-3.5", "endpoint": "http://api.example.com"}
            ],
            "timeout": 120,
            "tags": ["python", "backend"]
        }
        
        result = validate_agent_config(agent_config)
        self.assertTrue(result)


class TestConfigError(unittest.TestCase):
    """Test cases for ConfigError exception."""

    def test_config_error_raised(self):
        """Should raise ConfigError for config issues."""
        with self.assertRaises(ConfigError):
            raise ConfigError("Invalid configuration")

    def test_config_error_message(self):
        """Should include meaningful error message."""
        try:
            raise ConfigError("Missing required field: name")
        except ConfigError as e:
            self.assertIn("Missing required field", str(e))

    def test_config_error_inheritance(self):
        """ConfigError should inherit from Exception."""
        error = ConfigError("test")
        self.assertIsInstance(error, Exception)


class TestConfigIntegration(unittest.TestCase):
    """Integration tests for config module."""

    def test_load_and_validate_agent_configs(self):
        """Should load and validate multiple agent configs."""
        config_data = {
            "manager": {
                "name": "Project Manager",
                "role": "manager",
                "system_prompt": "Decompose requests"
            },
            "developer": {
                "name": "Code Developer",
                "role": "developer",
                "system_prompt": "Write code"
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
            with patch('config.json.load', return_value=config_data):
                config = load_config("roles.json")
                
                # Validate each agent config
                for agent_config in config.values():
                    result = validate_agent_config(agent_config)
                    self.assertTrue(result)

    def test_get_config_with_validation(self):
        """Should retrieve config values with validation."""
        config_data = {
            "agents": {
                "developer": {
                    "name": "Developer",
                    "role": "developer",
                    "system_prompt": "Write code",
                    "timeout": 120
                }
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
            with patch('config.json.load', return_value=config_data):
                config = load_config("config.json")
                
                agent_config = get_config_value(config, "agents.developer")
                result = validate_agent_config(agent_config)
                self.assertTrue(result)

    def test_config_with_fallback_values(self):
        """Should handle config with fallback/default values."""
        config_data = {
            "timeout": 30,  # default timeout
            "agents": {
                "fast_agent": {
                    "name": "Fast Agent",
                    "role": "researcher",
                    "system_prompt": "Research quickly",
                    "timeout": 10  # override default
                },
                "slow_agent": {
                    "name": "Slow Agent",
                    "role": "analyst",
                    "system_prompt": "Analyze deeply"
                    # uses default timeout
                }
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
            with patch('config.json.load', return_value=config_data):
                config = load_config("config.json")
                
                default_timeout = get_config_value(config, "timeout")
                fast_timeout = get_config_value(config, "agents.fast_agent.timeout")
                slow_timeout = get_config_value(config, "agents.slow_agent.timeout", default_timeout)
                
                self.assertEqual(default_timeout, 30)
                self.assertEqual(fast_timeout, 10)
                self.assertEqual(slow_timeout, 30)


if __name__ == "__main__":
    unittest.main()
