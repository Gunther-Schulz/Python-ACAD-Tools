"""Color formatting utilities for console output and logging."""
import os
import sys
from typing import Optional, Dict, Any
from enum import Enum

try:
    import colorama
    from colorama import Fore, Back, Style
    COLORAMA_AVAILABLE = True
    # Initialize colorama for Windows compatibility
    colorama.init(autoreset=True)
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback classes for when colorama is not available
    class _FallbackColor:
        def __getattr__(self, name):
            return ""

    Fore = _FallbackColor()
    Back = _FallbackColor()
    Style = _FallbackColor()


class LogLevel(Enum):
    """Log level enumeration for color mapping."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ColorFormatter:
    """Provides color formatting for console output and logging."""

    # Color mapping for different log levels
    LOG_COLORS = {
        LogLevel.DEBUG: Fore.CYAN,
        LogLevel.INFO: Fore.GREEN,
        LogLevel.WARNING: Fore.YELLOW,
        LogLevel.ERROR: Fore.RED,
        LogLevel.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    # Color mapping for CLI message types
    CLI_COLORS = {
        'error': Fore.RED + Style.BRIGHT,
        'warning': Fore.YELLOW + Style.BRIGHT,
        'success': Fore.GREEN + Style.BRIGHT,
        'info': Fore.CYAN,
        'suggestion': Fore.BLUE,
        'highlight': Fore.MAGENTA,
        'reset': Style.RESET_ALL,
    }

    def __init__(self, use_colors: Optional[bool] = None):
        """
        Initialize ColorFormatter.

        Args:
            use_colors: Whether to use colors. If None, auto-detect based on environment.
        """
        if use_colors is None:
            # Auto-detect color support
            self.use_colors = self._should_use_colors()
        else:
            self.use_colors = use_colors and COLORAMA_AVAILABLE

    def _should_use_colors(self) -> bool:
        """
        Determine if colors should be used based on environment.

        Returns:
            True if colors should be used, False otherwise.
        """
        if not COLORAMA_AVAILABLE:
            return False

        # Disable colors in CI environments
        ci_indicators = ['CI', 'CONTINUOUS_INTEGRATION', 'GITHUB_ACTIONS', 'GITLAB_CI', 'JENKINS_URL']
        if any(os.getenv(indicator) for indicator in ci_indicators):
            return False

        # Disable colors if NO_COLOR environment variable is set
        if os.getenv('NO_COLOR'):
            return False

        # Force colors if FORCE_COLOR is set
        if os.getenv('FORCE_COLOR'):
            return True

        # Check if stdout is a TTY (terminal)
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

    def colorize_log_level(self, level_name: str) -> str:
        """
        Apply color to a log level name.

        Args:
            level_name: The log level name (e.g., 'ERROR', 'WARNING').

        Returns:
            Colored log level name if colors are enabled, otherwise plain text.
        """
        if not self.use_colors:
            return level_name

        try:
            level_enum = LogLevel(level_name.upper())
            color = self.LOG_COLORS.get(level_enum, "")
            return f"{color}{level_name}{Style.RESET_ALL}"
        except ValueError:
            # Unknown log level, return as-is
            return level_name

    def colorize_message(self, message: str, message_type: str = 'info') -> str:
        """
        Apply color to a message based on its type.

        Args:
            message: The message to colorize.
            message_type: The type of message ('error', 'warning', 'success', etc.).

        Returns:
            Colored message if colors are enabled, otherwise plain text.
        """
        if not self.use_colors:
            return message

        color = self.CLI_COLORS.get(message_type.lower(), "")
        if color:
            return f"{color}{message}{Style.RESET_ALL}"
        return message

    def format_cli_error(self, title: str, message: str, suggestions: list = None) -> str:
        """
        Format a CLI error message with colors.

        Args:
            title: The error title.
            message: The error message.
            suggestions: Optional list of suggestions.

        Returns:
            Formatted error message with colors.
        """
        if not self.use_colors:
            # Return plain text format
            result = f"\n❌ {title}:\n   {message}"
            if suggestions:
                result += "\n\n💡 Suggestions:"
                for suggestion in suggestions:
                    result += f"\n   • {suggestion}"
            return result

        # Colored format
        error_icon = f"{Fore.RED}❌{Style.RESET_ALL}"
        title_colored = f"{Fore.RED + Style.BRIGHT}{title}{Style.RESET_ALL}"
        message_colored = f"{Fore.RED}   {message}{Style.RESET_ALL}"

        result = f"\n{error_icon} {title_colored}:\n{message_colored}"

        if suggestions:
            suggestion_icon = f"{Fore.BLUE}💡{Style.RESET_ALL}"
            suggestions_title = f"{Fore.BLUE + Style.BRIGHT}Suggestions{Style.RESET_ALL}"
            result += f"\n\n{suggestion_icon} {suggestions_title}:"

            for suggestion in suggestions:
                suggestion_colored = f"{Fore.CYAN}   • {suggestion}{Style.RESET_ALL}"
                result += f"\n{suggestion_colored}"

        return result

    def format_cli_warning(self, title: str, message: str) -> str:
        """
        Format a CLI warning message with colors.

        Args:
            title: The warning title.
            message: The warning message.

        Returns:
            Formatted warning message with colors.
        """
        if not self.use_colors:
            return f"\n⚠️  {title}:\n   {message}"

        warning_icon = f"{Fore.YELLOW}⚠️{Style.RESET_ALL}"
        title_colored = f"{Fore.YELLOW + Style.BRIGHT}{title}{Style.RESET_ALL}"
        message_colored = f"{Fore.YELLOW}   {message}{Style.RESET_ALL}"

        return f"\n{warning_icon}  {title_colored}:\n{message_colored}"

    def format_cli_success(self, message: str) -> str:
        """
        Format a CLI success message with colors.

        Args:
            message: The success message.

        Returns:
            Formatted success message with colors.
        """
        if not self.use_colors:
            return f"✅ {message}"

        success_icon = f"{Fore.GREEN}✅{Style.RESET_ALL}"
        message_colored = f"{Fore.GREEN + Style.BRIGHT}{message}{Style.RESET_ALL}"

        return f"{success_icon} {message_colored}"


# Global instance for easy access
_default_formatter = ColorFormatter()

def colorize_log_level(level_name: str) -> str:
    """Convenience function to colorize log level using default formatter."""
    return _default_formatter.colorize_log_level(level_name)

def colorize_message(message: str, message_type: str = 'info') -> str:
    """Convenience function to colorize message using default formatter."""
    return _default_formatter.colorize_message(message, message_type)

def format_cli_error(title: str, message: str, suggestions: list = None) -> str:
    """Convenience function to format CLI error using default formatter."""
    return _default_formatter.format_cli_error(title, message, suggestions)

def format_cli_warning(title: str, message: str) -> str:
    """Convenience function to format CLI warning using default formatter."""
    return _default_formatter.format_cli_warning(title, message)

def format_cli_success(message: str) -> str:
    """Convenience function to format CLI success using default formatter."""
    return _default_formatter.format_cli_success(message)

def set_color_enabled(enabled: bool) -> None:
    """Enable or disable colors globally."""
    global _default_formatter
    _default_formatter.use_colors = enabled and COLORAMA_AVAILABLE
