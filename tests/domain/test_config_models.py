"""Comprehensive tests for application configuration models."""
import pytest
import os
from typing import Dict, Any
from unittest.mock import patch
from pydantic import ValidationError

from src.domain.config_models import AppConfig


class TestAppConfig:
    """Test cases for AppConfig application settings model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_default_configuration(self):
        """Test AppConfig with default values."""
        config = AppConfig()

        # Test default values
        assert config.projects_root_dir == "projects"
        assert config.global_styles_file == "styles.yaml"
        assert config.aci_colors_file == "aci_colors.yaml"
        assert config.log_level_console == "INFO"
        assert config.log_level_file == "DEBUG"
        assert config.log_file_path == "logs/app.log"
        assert config.max_memory_mb == 1024.0
        assert config.temp_dir is None
        assert config.enable_validation is True
        assert config.enable_memory_optimization is True
        assert config.enable_parallel_processing is False

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "PROJECTS_ROOT_DIR": "custom_projects",
            "GLOBAL_STYLES_FILE": "custom_styles.yaml",
            "LOG_LEVEL_CONSOLE": "DEBUG",
            "MAX_MEMORY_MB": "2048.0",
            "ENABLE_VALIDATION": "false",
            "ENABLE_PARALLEL_PROCESSING": "true"
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()

            assert config.projects_root_dir == "custom_projects"
            assert config.global_styles_file == "custom_styles.yaml"
            assert config.log_level_console == "DEBUG"
            assert config.max_memory_mb == 2048.0
            assert config.enable_validation is False
            assert config.enable_parallel_processing is True

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_case_insensitive_environment_variables(self):
        """Test that environment variables are case insensitive."""
        env_vars = {
            "projects_root_dir": "lowercase_projects",
            "LOG_LEVEL_CONSOLE": "warning",
            "enable_validation": "False"
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()

            assert config.projects_root_dir == "lowercase_projects"
            assert config.log_level_console == "WARNING"  # Should be normalized to uppercase
            assert config.enable_validation is False

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_log_level_validation_success(self):
        """Test valid log level values."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

        for level in valid_levels:
            env_vars = {"LOG_LEVEL_CONSOLE": level}
            with patch.dict(os.environ, env_vars, clear=False):
                config = AppConfig()
                assert config.log_level_console == level.upper()

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_log_level_validation_case_insensitive(self):
        """Test log level validation is case insensitive."""
        test_cases = [
            ("debug", "DEBUG"),
            ("Info", "INFO"),
            ("WARNING", "WARNING"),
            ("error", "ERROR"),
            ("Critical", "CRITICAL")
        ]

        for input_level, expected_level in test_cases:
            env_vars = {"LOG_LEVEL_CONSOLE": input_level}
            with patch.dict(os.environ, env_vars, clear=False):
                config = AppConfig()
                assert config.log_level_console == expected_level

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_log_level_validation_failures(self):
        """Test invalid log level values raise ValidationError."""
        invalid_levels = ['INVALID', 'TRACE', 'VERBOSE', '', '123', 'debug_level']

        for level in invalid_levels:
            env_vars = {"LOG_LEVEL_CONSOLE": level}
            with patch.dict(os.environ, env_vars, clear=False):
                with pytest.raises(ValidationError) as exc_info:
                    AppConfig()
                assert "log level must be one of" in str(exc_info.value).lower()

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_log_level_file_can_be_none(self):
        """Test that log_level_file can be None."""
        env_vars = {"LOG_LEVEL_FILE": ""}
        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()
            # Empty string should be treated as None or default
            assert config.log_level_file in [None, "DEBUG"]

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_boolean_field_parsing(self):
        """Test boolean field parsing from environment variables."""
        test_cases = [
            # True values
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            # False values
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ]

        for env_value, expected in test_cases:
            env_vars = {"ENABLE_VALIDATION": env_value}
            with patch.dict(os.environ, env_vars, clear=False):
                config = AppConfig()
                assert config.enable_validation == expected

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_numeric_field_parsing(self):
        """Test numeric field parsing from environment variables."""
        test_cases = [
            ("512.0", 512.0),
            ("1024", 1024.0),
            ("2048.5", 2048.5),
            ("0.5", 0.5),
        ]

        for env_value, expected in test_cases:
            env_vars = {"MAX_MEMORY_MB": env_value}
            with patch.dict(os.environ, env_vars, clear=False):
                config = AppConfig()
                assert config.max_memory_mb == expected

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_invalid_numeric_field_parsing(self):
        """Test invalid numeric values raise ValidationError."""
        invalid_values = ["not_a_number", "abc", "", "12.34.56"]

        for value in invalid_values:
            env_vars = {"MAX_MEMORY_MB": value}
            with patch.dict(os.environ, env_vars, clear=False):
                with pytest.raises(ValidationError):
                    AppConfig()

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_optional_fields_handling(self):
        """Test handling of optional fields."""
        # Test with None values
        env_vars = {
            "LOG_LEVEL_FILE": "",
            "LOG_FILE_PATH": "",
            "TEMP_DIR": ""
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()
            # These should handle empty strings appropriately
            assert config.temp_dir in [None, ""]

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_extra_fields_ignored(self):
        """Test that extra environment variables are ignored."""
        env_vars = {
            "UNKNOWN_FIELD": "should_be_ignored",
            "RANDOM_CONFIG": "also_ignored",
            "LOG_LEVEL_CONSOLE": "INFO"  # Valid field
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()
            # Should not raise error and should work normally
            assert config.log_level_console == "INFO"
            # Extra fields should not be accessible
            assert not hasattr(config, 'unknown_field')
            assert not hasattr(config, 'random_config')

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_field_aliases(self):
        """Test that field aliases work correctly."""
        # Test using the actual environment variable names (aliases)
        env_vars = {
            "PROJECTS_ROOT_DIR": "alias_test_projects",
            "GLOBAL_STYLES_FILE": "alias_test_styles.yaml",
            "ACI_COLORS_FILE": "alias_test_colors.yaml"
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()
            assert config.projects_root_dir == "alias_test_projects"
            assert config.global_styles_file == "alias_test_styles.yaml"
            assert config.aci_colors_file == "alias_test_colors.yaml"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_immutability_after_creation(self):
        """Test that config values can be modified after creation (not frozen)."""
        config = AppConfig()

        # AppConfig should allow modification (not frozen like domain models)
        original_value = config.projects_root_dir
        config.projects_root_dir = "modified_projects"
        assert config.projects_root_dir == "modified_projects"
        assert config.projects_root_dir != original_value

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_realistic_configuration_scenario(self):
        """Test a realistic configuration scenario with mixed settings."""
        env_vars = {
            "PROJECTS_ROOT_DIR": "/opt/cad_projects",
            "GLOBAL_STYLES_FILE": "/etc/cad/styles.yaml",
            "LOG_LEVEL_CONSOLE": "WARNING",
            "LOG_LEVEL_FILE": "DEBUG",
            "LOG_FILE_PATH": "/var/log/cad_app.log",
            "MAX_MEMORY_MB": "4096.0",
            "TEMP_DIR": "/tmp/cad_processing",
            "ENABLE_VALIDATION": "true",
            "ENABLE_MEMORY_OPTIMIZATION": "true",
            "ENABLE_PARALLEL_PROCESSING": "true"
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = AppConfig()

            assert config.projects_root_dir == "/opt/cad_projects"
            assert config.global_styles_file == "/etc/cad/styles.yaml"
            assert config.log_level_console == "WARNING"
            assert config.log_level_file == "DEBUG"
            assert config.log_file_path == "/var/log/cad_app.log"
            assert config.max_memory_mb == 4096.0
            assert config.temp_dir == "/tmp/cad_processing"
            assert config.enable_validation is True
            assert config.enable_memory_optimization is True
            assert config.enable_parallel_processing is True

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_model_config_settings(self):
        """Test that the model configuration is set correctly."""
        config = AppConfig()

        # Test that the model config is properly set
        model_config = config.model_config
        assert model_config['env_file'] == ".env"
        assert model_config['env_file_encoding'] == "utf-8"
        assert model_config['extra'] == "ignore"
        assert model_config['case_sensitive'] is False
