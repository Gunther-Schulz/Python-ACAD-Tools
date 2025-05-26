"""Tests for color formatting utility functions."""
import pytest
import os
from unittest.mock import patch, MagicMock

from src.utils.color_formatter import (
    ColorFormatter,
    LogLevel,
    colorize_log_level,
    colorize_message,
    format_cli_error,
    format_cli_warning,
    format_cli_success,
    set_color_enabled
)


class TestColorFormatter:
    """Test cases for ColorFormatter class."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_init_with_colors_enabled(self):
        """Test ColorFormatter initialization with colors enabled."""
        formatter = ColorFormatter(use_colors=True)
        assert formatter.use_colors is True

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_init_with_colors_disabled(self):
        """Test ColorFormatter initialization with colors disabled."""
        formatter = ColorFormatter(use_colors=False)
        assert formatter.use_colors is False

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_should_use_colors_ci_environment(self):
        """Test that colors are disabled in CI environments."""
        formatter = ColorFormatter()

        with patch.dict(os.environ, {'CI': 'true'}):
            assert formatter._should_use_colors() is False

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_should_use_colors_no_color_env(self):
        """Test that colors are disabled when NO_COLOR is set."""
        formatter = ColorFormatter()

        with patch.dict(os.environ, {'NO_COLOR': '1'}):
            assert formatter._should_use_colors() is False

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_should_use_colors_force_color_env(self):
        """Test that colors are enabled when FORCE_COLOR is set."""
        formatter = ColorFormatter()

        with patch.dict(os.environ, {'FORCE_COLOR': '1'}, clear=True):
            with patch('sys.stdout.isatty', return_value=False):
                assert formatter._should_use_colors() is True

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_log_level_with_colors(self):
        """Test log level colorization when colors are enabled."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.colorize_log_level("ERROR")
        assert "ERROR" in result
        # Should contain ANSI escape codes when colors are enabled
        assert "\x1b[" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_log_level_without_colors(self):
        """Test log level colorization when colors are disabled."""
        formatter = ColorFormatter(use_colors=False)

        result = formatter.colorize_log_level("ERROR")
        assert result == "ERROR"
        # Should not contain ANSI escape codes when colors are disabled
        assert "\x1b[" not in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_log_level_unknown_level(self):
        """Test colorization of unknown log level."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.colorize_log_level("UNKNOWN")
        assert result == "UNKNOWN"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_message_with_colors(self):
        """Test message colorization when colors are enabled."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.colorize_message("Test message", "error")
        assert "Test message" in result
        assert "\x1b[" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_message_without_colors(self):
        """Test message colorization when colors are disabled."""
        formatter = ColorFormatter(use_colors=False)

        result = formatter.colorize_message("Test message", "error")
        assert result == "Test message"
        assert "\x1b[" not in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_error_with_colors(self):
        """Test CLI error formatting with colors."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.format_cli_error(
            "Test Error",
            "Something went wrong",
            ["Check this", "Try that"]
        )

        assert "Test Error" in result
        assert "Something went wrong" in result
        assert "Check this" in result
        assert "Try that" in result
        assert "❌" in result
        assert "💡" in result
        assert "\x1b[" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_error_without_colors(self):
        """Test CLI error formatting without colors."""
        formatter = ColorFormatter(use_colors=False)

        result = formatter.format_cli_error(
            "Test Error",
            "Something went wrong",
            ["Check this", "Try that"]
        )

        assert "Test Error" in result
        assert "Something went wrong" in result
        assert "Check this" in result
        assert "Try that" in result
        assert "❌" in result
        assert "💡" in result
        assert "\x1b[" not in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_error_no_suggestions(self):
        """Test CLI error formatting without suggestions."""
        formatter = ColorFormatter(use_colors=False)

        result = formatter.format_cli_error("Test Error", "Something went wrong")

        assert "Test Error" in result
        assert "Something went wrong" in result
        assert "💡" not in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_warning(self):
        """Test CLI warning formatting."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.format_cli_warning("Test Warning", "Be careful")

        assert "Test Warning" in result
        assert "Be careful" in result
        assert "⚠️" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_success(self):
        """Test CLI success formatting."""
        formatter = ColorFormatter(use_colors=True)

        result = formatter.format_cli_success("Operation completed")

        assert "Operation completed" in result
        assert "✅" in result


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_log_level_function(self):
        """Test colorize_log_level convenience function."""
        result = colorize_log_level("WARNING")
        assert "WARNING" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_colorize_message_function(self):
        """Test colorize_message convenience function."""
        result = colorize_message("Test message", "info")
        assert "Test message" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_error_function(self):
        """Test format_cli_error convenience function."""
        result = format_cli_error("Error", "Message", ["Suggestion"])
        assert "Error" in result
        assert "Message" in result
        assert "Suggestion" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_warning_function(self):
        """Test format_cli_warning convenience function."""
        result = format_cli_warning("Warning", "Message")
        assert "Warning" in result
        assert "Message" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_format_cli_success_function(self):
        """Test format_cli_success convenience function."""
        result = format_cli_success("Success message")
        assert "Success message" in result

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_set_color_enabled(self):
        """Test set_color_enabled function."""
        # Test enabling colors
        set_color_enabled(True)
        result = colorize_log_level("ERROR")
        # Should work regardless of environment when explicitly enabled

        # Test disabling colors
        set_color_enabled(False)
        result = colorize_log_level("ERROR")
        assert result == "ERROR"
        assert "\x1b[" not in result


class TestLogLevel:
    """Test cases for LogLevel enum."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_log_level_values(self):
        """Test LogLevel enum values."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


class TestColorFormatterWithoutColorama:
    """Test cases for ColorFormatter when colorama is not available."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_formatter_without_colorama(self):
        """Test that formatter works gracefully without colorama."""
        with patch('src.utils.color_formatter.COLORAMA_AVAILABLE', False):
            formatter = ColorFormatter(use_colors=True)

            # Should disable colors when colorama is not available
            assert formatter.use_colors is False

            result = formatter.colorize_log_level("ERROR")
            assert result == "ERROR"
            assert "\x1b[" not in result
