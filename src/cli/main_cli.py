"""Main CLI entry point for the application."""
import argparse
import os
import sys
import logging

from ..core.container import ApplicationContainer
from ..domain.config_models import AppConfig
from ..domain.exceptions import ApplicationBaseException
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
        log_file_path=log_file_path
    )
    logger.info("Logging configured via DI container.")


def setup_commands(container: ApplicationContainer) -> CommandRegistry:
    """Setup CLI commands using the DI container."""
    command_registry = CommandRegistry()

    # Register commands with their dependencies injected from container
    process_project_command = ProcessProjectCommand(
        logger_service=container.logging_service(),
        project_orchestrator=container.project_orchestrator()
    )
    command_registry.register_command("process_project", process_project_command)

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

    args = parser.parse_args()

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
        logger.info(f"Successfully completed processing for project: {args.project_name}")
        sys.exit(0)

    except ApplicationBaseException as app_exc:
        logger.critical(f"Application error processing project '{args.project_name}': {app_exc}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred while processing project '{args.project_name}': {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
