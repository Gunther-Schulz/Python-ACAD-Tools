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
    target_crs: Optional[str] = None
) -> None:
    """Main application logic execution using the configured DxfGenerationService."""
    logger = container.logger()
    logger.info("DXFPlanner application starting...")

    try:
        # Get the main service from the container
        dxf_service: IDxfGenerationService = container.dxf_generation_service() # type: ignore

        await dxf_service.generate_dxf_from_source(
            output_dxf_path=Path(output_file),
            target_crs=target_crs
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
            __name__, # For main_runner if it were to use @inject (it uses direct container access here)
            "dxfplanner.services.orchestration_service",
            "dxfplanner.services.geoprocessing.geometry_transform_service",
            "dxfplanner.services.geoprocessing.attribute_mapping_service",
            "dxfplanner.services.geoprocessing.coordinate_service",
            "dxfplanner.services.validation_service",
            "dxfplanner.io.readers.shapefile_reader",
            "dxfplanner.io.writers.dxf_writer",
            # Add other modules here if they use @inject decorators or direct container access.
            # e.g., "dxfplanner.cli" if you have a cli.py using the container.
        ]
    )
    init_logger.info("DI container configured and wired.")
    return app_config

# Example of how this app.py might be run (e.g., for testing or simple execution)
if __name__ == "__main__":
    # Initialize application (config, logging, DI)
    app_config = initialize_app()
    logger = container.logger()

    # --- Example Usage (replace with actual file paths) ---
    # Ensure you have a sample geodata file (e.g., a .shp file)
    # and specify output path.
    # For Shapefile, you need all associated files (.dbf, .shx, etc.) in the same directory.

    # Create a dummy shapefile for testing if one doesn't exist
    # This is complex to do ad-hoc, usually you'd have a test file.
    # For now, assume a test_data/sample.shp or similar might exist.

    example_source_file = "test_data/input/sample.shp" # MODIFY THIS PATH
    example_output_file = "test_data/output/generated_sample.dxf" # MODIFY THIS PATH

    # Create directories if they don't exist for the example
    Path("test_data/input").mkdir(parents=True, exist_ok=True)
    Path("test_data/output").mkdir(parents=True, exist_ok=True)

    logger.warning(f"This is an example runner. Ensure '{example_source_file}' exists or change the path.")
    logger.warning("The default readers/services are placeholders and will raise NotImplementedError.")
    logger.warning("You will need to implement them and install libraries like pyshp/fiona and ezdxf.")

    # To make this runnable for a very basic test (it will hit NotImplementedError quickly):
    # You might need a dummy shapefile. Creating one programmatically is non-trivial here.
    # Let's assume the user is responsible for providing a shapefile for this test.
    if not Path(example_source_file).exists():
        logger.error(f"Example source file '{example_source_file}' not found. Please create it or update the path.")
        logger.error("The application now relies on 'config.yml' (or other configured file) to define this source.")
        logger.error("Cannot run example without source data defined in the configuration.")
    else:
        # Note: example_source_file is now just for the existence check.
        # The actual source path must be in config.yml for the service to use it.
        logger.info(f"Running example: Output will be '{example_output_file}'.")
        logger.info(f"Ensure your configuration (e.g., config.yml) points to '{example_source_file}' or similar.")
        asyncio.run(main_runner(
            output_file=example_output_file,
            target_crs=None  # Optional: Specify desired output CRS, or None for config default
        ))
