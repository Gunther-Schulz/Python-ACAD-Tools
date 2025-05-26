"""Main CLI entry point for the application."""
import argparse
import os
import sys
import logging

from ..core.container import ApplicationContainer
from ..domain.config_models import AppConfig
from ..domain.exceptions import ApplicationBaseException, ConfigError, ConfigValidationError
from ..utils.color_formatter import format_cli_error, format_cli_success, set_color_enabled
from .commands import ProcessProjectCommand, CommandRegistry

# Get root logger for initial messages before service setup
logger = logging.getLogger(__name__)


def setup_container(args) -> ApplicationContainer:
    """Setup and configure the DI container with CLI arguments."""
    container = ApplicationContainer()

    # Create AppConfig from CLI arguments
    app_config = AppConfig(
        projects_root_dir=os.path.abspath(args.projects_root),
        global_styles_file=args.global_styles,
        aci_colors_file=args.aci_colors,
        log_level_console=args.log_level_console
    )

    # Configure the container
    container.config.app_config.override(app_config)

    return container


def setup_logging(container: ApplicationContainer, args) -> None:
    """Setup logging using the logging service from container."""
    logging_service = container.logging_service()

    log_file_path = args.log_file
    if log_file_path:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    file_log_level = args.log_level_file if args.log_level_file != "NONE" else None

    logging_service.setup_logging(
        log_level_console=args.log_level_console.upper(),
        log_level_file=file_log_level,
        log_file_path=log_file_path,
        use_colors=not args.no_color
    )
    logger.info("Logging configured via DI container.")


def setup_commands(container: ApplicationContainer) -> CommandRegistry:
    """Setup CLI commands using the DI container."""
    command_registry = CommandRegistry()

    # Register commands with their dependencies injected from container
    process_project_command = ProcessProjectCommand(
        logger_service=container.logging_service(),
        project_orchestrator=container.project_orchestrator_service()
    )
    command_registry.register_command("process_project", process_project_command)

    # Factory pattern is available for dynamic component creation:
    # service_factory = container.service_factory()
    # handler_factory = container.handler_factory()
    # factory_registry = container.factory_registry()

    return command_registry


def run_cli():
    """Parses arguments, sets up DI container, and executes commands."""
    parser = argparse.ArgumentParser(description="Process DXF and geospatial data projects.")
    parser.add_argument("project_name", help="Name of the project to process (must match a directory name).")

    # Configuration overrides
    parser.add_argument("--projects-root", help="Override projects root directory.", default=os.getenv("PROJECTS_ROOT_DIR", "./projects"))
    parser.add_argument("--global-styles", help="Override path to global styles YAML file.", default=os.getenv("GLOBAL_STYLES_FILE", "styles.yaml"))
    parser.add_argument("--aci-colors", help="Override path to ACI colors YAML file.", default=os.getenv("ACI_COLORS_FILE", "aci_colors.yaml"))

    # Logging overrides
    parser.add_argument("--log-level-console", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Console logging level.")
    parser.add_argument("--log-level-file", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], help="File logging level (NONE to disable).")
    parser.add_argument("--log-file", default="logs/app.log", help="Path to the log file.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")

    args = parser.parse_args()

    # Configure color support based on CLI argument
    if args.no_color:
        set_color_enabled(False)

    try:
        # 1. Setup DI Container
        container = setup_container(args)
        logger.info("DI container initialized.")

        # 2. Setup Logging via DI
        setup_logging(container, args)

        # 3. Setup Commands via DI
        command_registry = setup_commands(container)
        logger.info("Command registry initialized with DI.")

        # 4. Execute Command
        logger.info(f"Attempting to process project: {args.project_name}")
        command_registry.execute_command("process_project", project_name=args.project_name)

        # Success message with color
        success_msg = format_cli_success(f"Successfully completed processing for project: {args.project_name}")
        print(success_msg)
        logger.info(f"Successfully completed processing for project: {args.project_name}")
        sys.exit(0)

    except ApplicationBaseException as app_exc:
        # Check if this is actually a configuration error wrapped in ApplicationBaseException
        if "Configuration validation failed" in str(app_exc):
            # Extract the validation errors from the message
            error_msg = str(app_exc)
            if "Validation errors:" in error_msg:
                validation_part = error_msg.split("Validation errors:")[1].strip()
                message = f"Multiple validation errors found:\n"
                # Split by '; ' and format each error nicely
                errors = validation_part.split('; ')
                for error in errors:
                    if error.strip():
                        message += f"   • {error.strip()}\n"
                message = message.rstrip()
            else:
                message = str(app_exc)

            suggestions = [
                "Check that all file paths in your configuration exist",
                "Verify that geojsonFile paths are correct relative to your project",
                "Use path aliases (@data.*, @output.*, etc.) for cleaner configuration",
                "Run with --log-level-console DEBUG for detailed validation information"
            ]

            error_output = format_cli_error(
                f"Configuration Validation Error in project '{args.project_name}'",
                message,
                suggestions
            )
            print(error_output)
            sys.exit(1)
        elif "Failed to load project configuration" in str(app_exc) or "Project directory not found" in str(app_exc):
            suggestions = [
                "Check that your project directory exists in the projects folder",
                "Verify that required configuration files (project.yaml, geom_layers.yaml) are present",
                "Ensure configuration files have valid YAML syntax",
                "Run with --log-level-console DEBUG for detailed error information"
            ]

            error_output = format_cli_error(
                f"Configuration Error in project '{args.project_name}'",
                str(app_exc),
                suggestions
            )
            print(error_output)
            sys.exit(1)
    except ConfigValidationError as config_val_exc:
        # Handle configuration validation errors with user-friendly messages
        suggestions = [
            "Check that all file paths in your configuration exist",
            "Verify that geojsonFile paths are correct relative to your project",
            "Use path aliases (@data.*, @output.*, etc.) for cleaner configuration",
            "Run with --log-level-console DEBUG for detailed validation information"
        ]

        error_output = format_cli_error(
            f"Configuration Validation Error in project '{args.project_name}'",
            str(config_val_exc),
            suggestions
        )
        print(error_output)
        sys.exit(1)
    except ConfigError as config_exc:
        # Handle general configuration errors
        suggestions = [
            "Check that your project directory exists in the projects folder",
            "Verify that required configuration files (project.yaml, geom_layers.yaml) are present",
            "Ensure configuration files have valid YAML syntax",
            "Run with --log-level-console DEBUG for detailed error information"
        ]

        error_output = format_cli_error(
            f"Configuration Error in project '{args.project_name}'",
            str(config_exc),
            suggestions
        )
        print(error_output)
        sys.exit(1)
    except ApplicationBaseException as app_exc:
        # Handle other application-specific errors
        suggestions = ["For detailed error information, check the log file or run with --log-level-console DEBUG"]

        error_output = format_cli_error(
            f"Application Error processing project '{args.project_name}'",
            str(app_exc),
            suggestions
        )
        print(error_output)
        logger.critical(f"Application error processing project '{args.project_name}': {app_exc}", exc_info=True)
        sys.exit(1)
    except FileNotFoundError as file_exc:
        # Handle missing files with helpful suggestions
        suggestions = [
            "Check that the project directory exists",
            "Verify that all referenced data files exist",
            "Ensure file paths are correct (case-sensitive on Linux/Mac)",
            "Use absolute paths or path aliases for reliability"
        ]

        error_output = format_cli_error(
            "File Not Found Error",
            str(file_exc),
            suggestions
        )
        print(error_output)
        sys.exit(1)
    except Exception as e:
        # Handle unexpected errors
        suggestions = [
            "Check the log file for detailed error information",
            "Run with --log-level-console DEBUG for verbose output",
            "Report this issue if it persists"
        ]

        error_output = format_cli_error(
            f"Unexpected Error processing project '{args.project_name}'",
            f"{e}\n\nThis appears to be an unexpected error. Please:",
            suggestions
        )
        print(error_output)
        logger.critical(f"An unexpected critical error occurred while processing project '{args.project_name}': {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
