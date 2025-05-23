"""Main CLI entry point for the application."""
import argparse
import os
import sys
import logging # For direct use by CLI if needed, though service is primary

# Application components
from ..services.logging_service import LoggingService
from ..services.config_loader_service import ConfigLoaderService
from ..services.data_source_service import DataSourceService
from ..services.geometry_processor_service import GeometryProcessorService
from ..services.style_applicator_service import StyleApplicatorService
from ..services.data_exporter_service import DataExporterService
from ..services.project_orchestrator_service import ProjectOrchestratorService

from ..interfaces.logging_service_interface import ILoggingService
from ..domain.config_models import AppConfig
from ..domain.exceptions import ConfigError, ProcessingError, ApplicationBaseException

# Get root logger for initial messages before service setup, or if service fails.
logger = logging.getLogger(__name__)

def run_cli():
    """Parses arguments, sets up services, and runs the project orchestrator."""
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

    # 1. Initialize Logging Service (must be first)
    # This initial logger_service is primarily for other services.
    # The setup_logging call will configure the global logging settings.
    logging_service_impl = LoggingService() # No dependencies for LoggingService itself

    log_file_path_to_use = args.log_file
    if log_file_path_to_use:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file_path_to_use)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    file_log_level = args.log_level_file if args.log_level_file != "NONE" else None

    logging_service_impl.setup_logging(
        log_level_console=args.log_level_console.upper(),
        log_level_file=file_log_level,
        log_file_path=log_file_path_to_use
    )
    logger.info("Logging configured via CLI arguments.")

    try:
        # 2. Create AppConfig (potentially overridden by CLI args)
        # We'll construct AppConfig here and pass it, rather than having ConfigLoaderService
        # try to load an .env file that might not exist or be correctly located relative to CLI.
        # For more complex CLI config, pydantic-settings could load from env/CLI directly.
        app_config = AppConfig(
            projects_root_dir=os.path.abspath(args.projects_root),
            global_styles_file=args.global_styles,
            aci_colors_file=args.aci_colors,
            # logging config within AppConfig could also be set here if it were more detailed
        )
        logger.info(f"AppConfig initialized: Projects Root='{app_config.projects_root_dir}', Styles='{app_config.global_styles_file}', ACI Colors='{app_config.aci_colors_file}'")

        # 3. Instantiate Services (with dependency injection)
        logger.debug("Instantiating services...")

        # ConfigLoader needs the AppConfig to know where to find project.yaml etc.
        config_loader_service = ConfigLoaderService(logger_service=logging_service_impl, app_config=app_config)

        data_source_service = DataSourceService(logger_service=logging_service_impl)

        # GeometryProcessor might need StyleConfig if preprocessors depend on it,
        # StyleConfig is loaded by ConfigLoaderService.
        # For now, assuming direct StyleConfig access isn't needed at GeometryProcessor init.
        # If it is, ConfigLoader would need to be used to get StyleConfig first.
        # Let's assume it needs the config_loader to potentially get styles for pre-processing context.
        geometry_processor_service = GeometryProcessorService(
            logger_service=logging_service_impl,
            data_source_service=data_source_service
        )

        # StyleApplicator needs ConfigLoader to get ACI color map and potentially base styles.
        style_applicator_service = StyleApplicatorService(
            config_loader=config_loader_service,
            logger_service=logging_service_impl
        )

        data_exporter_service = DataExporterService(logger_service=logging_service_impl)

        project_orchestrator = ProjectOrchestratorService(
            logging_service=logging_service_impl,
            config_loader=config_loader_service,
            data_source=data_source_service,
            geometry_processor=geometry_processor_service,
            style_applicator=style_applicator_service,
            data_exporter=data_exporter_service
        )
        logger.info("All services instantiated.")

        # 4. Run Project Processing
        logger.info(f"Attempting to process project: {args.project_name}")
        project_orchestrator.process_project(args.project_name)
        logger.info(f"Successfully completed processing for project: {args.project_name}")
        sys.exit(0)

    except ApplicationBaseException as app_exc: # Catch our custom base exceptions
        logger.critical(f"Application error processing project '{args.project_name}': {app_exc}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred while processing project '{args.project_name}': {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # This allows src/cli/main_cli.py to be run directly for testing,
    # but the primary entry point will be the root main.py
    run_cli()
