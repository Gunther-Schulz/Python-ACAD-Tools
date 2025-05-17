import asyncio
from pathlib import Path
from typing import Optional

# Configuration loading
from dxfplanner.config.loaders import load_config_from_yaml, find_config_file, DEFAULT_CONFIG_FILES
from dxfplanner.config.schemas import AppConfig
from dxfplanner.core.exceptions import ConfigurationError, DXFPlannerBaseError

# Dependency Injection container
from dxfplanner.core.di import Container

# Core services (though typically accessed via container)
from dxfplanner.core import logging_config # For initial setup
from dxfplanner.domain.interfaces import IDxfGenerationService # For type hint

# For creating a dummy config if needed for testing
import yaml

# Global container instance
container = Container()

def create_dummy_config_if_not_exists(config_path: Path = Path("config.yml")) -> None:
    """Creates a minimal config.yml if it doesn't exist, for basic runs."""
    if not config_path.exists():
        print(f"No configuration file found at expected locations. Creating dummy '{config_path}' for basic operation.")
        dummy_config = {
            "logging": {"level": "INFO"},
            # Add other minimal essential defaults if AppConfig requires them beyond Pydantic defaults
            # e.g., if io.readers.shapefile had mandatory fields not defaulted in Pydantic
        }
        try:
            with open(config_path, "w") as f:
                yaml.dump(dummy_config, f)
            print(f"Dummy '{config_path}' created. Please review and customize it.")
        except IOError as e:
            print(f"Warning: Could not create dummy config file '{config_path}': {e}")
            print("Application will run with Pydantic model defaults which might not be optimal.")

async def main_runner(
    output_file: str,
    # target_crs: Optional[str] = None # Removed, DxfGenerationService no longer takes this directly
) -> None:
    """Main application logic execution using the configured DxfGenerationService."""
    logger = container.logger()
    logger.info("DXFPlanner application starting...")

    try:
        # Get the main service from the container
        dxf_service: IDxfGenerationService = container.dxf_generation_service() # type: ignore

        await dxf_service.generate_dxf_from_source(
            output_dxf_path=Path(output_file),
            # target_crs_override_str=target_crs # Parameter removed
        )
        logger.info(f"DXF generation complete. Output: {output_file}")

    except DXFPlannerBaseError as e:
        logger.error(f"Application error: {e}", exc_info=True)
        # Potentially exit with error code for CLI
    except Exception as e:
        logger.error(f"An unexpected critical error occurred: {e}", exc_info=True)
        # Potentially exit with error code for CLI

def initialize_app() -> AppConfig:
    """
    Initializes the application: loads config, sets up logging, wires container.
    Returns the loaded application configuration.
    """
    # 1. Determine config file path
    #    (find_config_file will raise ConfigurationError if no suitable file is found
    #     after checking standard locations if no specific path is given to load_config_from_yaml)
    #    For robustness in a non-CLI test context, we can try to create a dummy one.
    try:
        # This will search CWD, ./config, etc. for config.yml/yaml
        config_file_to_load = find_config_file()
    except ConfigurationError:
        # If truly not found, create a dummy one in CWD for this basic app.py runner
        dummy_path = Path.cwd() / DEFAULT_CONFIG_FILES[0]
        create_dummy_config_if_not_exists(dummy_path)
        # Try finding again (or just use dummy_path if it was created)
        try:
            config_file_to_load = find_config_file(dummy_path if dummy_path.exists() else None)
        except ConfigurationError as ce_after_dummy:
            # If still not found even after trying to create a dummy, something is odd.
            # Fallback to default Pydantic model, but warn heavily.
            print(f"Critical: Could not find or create a config file. Proceeding with built-in defaults. Error: {ce_after_dummy}")
            app_config = AppConfig() # Use Pydantic defaults
            # Setup logging with default config from the model
            logging_config.setup_logging(app_config.logging)
            container.logger().warning("Logging initialized with default Pydantic model settings due to config load failure.")
            # Provide the default config to the container
            container.config.from_pydantic(app_config)
            # Wire up modules. Services will get this default config.
            container.wire(modules=[__name__, ".services.orchestration_service"]) # Add other modules as needed
            return app_config

    # 2. Load configuration from the found file
    try:
        app_config = load_config_from_yaml(config_file_path=config_file_to_load)
        print(f"Configuration loaded successfully from: {config_file_to_load}")
    except ConfigurationError as e:
        print(f"Error loading configuration from {config_file_to_load}: {e}")
        print("Falling back to default Pydantic model configuration.")
        app_config = AppConfig() # Use Pydantic defaults

    # 3. Setup logging using the loaded (or default) configuration
    #    This should happen before any other component tries to get a logger that might depend on config.
    logging_config.setup_logging(app_config.logging)
    # Now that logging is set up, get a logger for app.py itself if needed for init messages.
    init_logger = container.logger() # DI container now provides configured logger
    init_logger.info(f"Logging initialized. Level: {app_config.logging.level}")

    # 4. Provide the loaded configuration to the DI container
    container.config.from_pydantic(app_config)

    # 5. Wire the container to modules that might use @inject or container directly
    #    This is crucial for dependency injection to work in those modules.
    #    List all modules where injection is used.
    #    Example: if DxfGenerationService uses @inject, its module needs to be listed.
    container.wire(
        modules=[
            __name__,
            "dxfplanner.config.loaders",
            "dxfplanner.config.schemas", # Also operation_schemas, style_schemas etc. if they use DI directly. Assume not for now.
            "dxfplanner.core.di",
            "dxfplanner.core.exceptions",
            "dxfplanner.core.logging_config",

            "dxfplanner.domain.interfaces",
            "dxfplanner.domain.models.common",
            "dxfplanner.domain.models.dxf_models",
            "dxfplanner.domain.models.geo_models",
            "dxfplanner.domain.models.layer_styles", # Contains LayerStyleConfig etc.

            "dxfplanner.geometry.operations",
            "dxfplanner.geometry.transformations",
            "dxfplanner.geometry.utils",

            "dxfplanner.io.readers.shapefile_reader",
            "dxfplanner.io.readers.geojson_reader",
            # "dxfplanner.io.readers.csv_wkt_reader", # If/when implemented and uses DI

            "dxfplanner.io.writers.dxf_writer",
            "dxfplanner.io.writers.components.dxf_entity_converter_service",
            "dxfplanner.io.writers.components.dxf_resource_setup_service",
            "dxfplanner.io.writers.components.dxf_viewport_setup_service",

            "dxfplanner.services.dxf_generation_service", # Renamed from orchestration_service
            "dxfplanner.services.pipeline_service",
            "dxfplanner.services.layer_processor_service",
            "dxfplanner.services.style_service",
            "dxfplanner.services.validation_service",
            "dxfplanner.services.legend_generation_service", # Added
            "dxfplanner.services.geoprocessing.attribute_mapping_service",
            "dxfplanner.services.geoprocessing.coordinate_service",
            "dxfplanner.services.geoprocessing.label_placement_service",

            "dxfplanner.cli" # CLI uses the container
        ]
    )
    init_logger.info("DI container configured and wired.")
    return app_config

# Example of how this app.py might be run (e.g., for testing or simple execution)
if __name__ == "__main__":
    # Initialize application (config, logging, DI)
    app_config = initialize_app()
    logger = container.logger()

    logger.info(f"DXFPlanner app.py direct execution example starting with config: {app_config.project_name or 'Default Project'}.")
    logger.info("This example attempts to run main_runner. Ensure 'config.yml' (or equivalent) is correctly set up.")

    # Determine output path from config, as CLI is not used here.
    example_output_file = "test_data/output/app_py_generated_example.dxf" # Default for this example
    output_path_from_config = None

    if app_config.io and app_config.io.writers and app_config.io.writers.dxf and app_config.io.writers.dxf.output_filepath:
        output_path_from_config = Path(app_config.io.writers.dxf.output_filepath).resolve()
    elif app_config.io and app_config.io.output_filepath: # Fallback to older general output_filepath
        output_path_from_config = Path(app_config.io.output_filepath).resolve()

    if output_path_from_config:
        example_output_file = str(output_path_from_config)
        logger.info(f"Output path for this example run will be: {example_output_file} (from configuration)")
    else:
        logger.warning(f"No output path found in configuration (io.writers.dxf.output_filepath or io.output_filepath). Using default: {example_output_file}")
        # Ensure default example output directory exists
        Path(example_output_file).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Attempting to run the main_runner...")
    logger.info("If this fails, check your 'config.yml' for valid sources and parameters,")
    logger.info("and ensure all services and operations are correctly implemented and wired in DI.")

    try:
        asyncio.run(main_runner(
            output_file=example_output_file
        ))
        logger.info(f"app.py direct execution finished. Check: {example_output_file}")
    except DXFPlannerBaseError as e_app_run:
        logger.error(f"Error during app.py direct execution: {e_app_run}", exc_info=True)
    except Exception as e_app_general:
        logger.error(f"Unexpected critical error during app.py direct execution: {e_app_general}", exc_info=True)
