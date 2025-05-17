import asyncio
from pathlib import Path
from typing import Optional
from dependency_injector import providers

# Configuration loading
from dxfplanner.config.loaders import load_config_from_yaml, find_config_file, DEFAULT_CONFIG_FILES
from dxfplanner.config.schemas import ProjectConfig
from dxfplanner.core.exceptions import ConfigurationError, DXFPlannerBaseError

# Dependency Injection container
from dxfplanner.core.di import DIContainer

# Core services (though typically accessed via container)
from dxfplanner.core import logging_config # For initial setup
from dxfplanner.domain.interfaces import IDxfGenerationService # For type hint

# For creating a dummy config if needed for testing
import yaml

# Global container instance
container = DIContainer()

def create_dummy_config_if_not_exists(config_path: Path = Path("config.yml")) -> None:
    """Creates a minimal config.yml if it doesn't exist, for basic runs."""
    if not config_path.exists():
        print(f"No configuration file found at expected locations. Creating dummy '{config_path}' for basic operation.")
        dummy_project_config_content = {
            "project_name": "Dummy Project",
            "layers": [],
            "dxf_writer": {"output_filepath": "dummy_output.dxf"},
            "logging": {"level": "INFO", "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}
        }
        try:
            with open(config_path, "w") as f:
                yaml.dump(dummy_project_config_content, f)
            print(f"Dummy '{config_path}' created. Please review and customize it.")
        except IOError as e:
            print(f"Warning: Could not create dummy config file '{config_path}': {e}")
            print("Application will run with Pydantic model defaults which might not be optimal.")

async def main_runner(
    output_file: str,
) -> None:
    """Main application logic execution using the configured DxfGenerationService."""
    logger = container.logger()
    logger.info("DXFPlanner application starting...")

    try:
        dxf_service: IDxfGenerationService = container.dxf_generation_service() # type: ignore
        await dxf_service.generate_dxf_from_source(
            output_dxf_path=Path(output_file),
        )
        logger.info(f"DXF generation complete. Output: {output_file}")

    except DXFPlannerBaseError as e:
        logger.error(f"Application error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected critical error occurred: {e}", exc_info=True)

def initialize_app() -> ProjectConfig:
    """
    Initializes the application: loads config, sets up logging, wires container.
    Returns the loaded application configuration.
    """
    try:
        config_file_to_load = find_config_file()
    except ConfigurationError:
        dummy_path = Path.cwd() / DEFAULT_CONFIG_FILES[0]
        create_dummy_config_if_not_exists(dummy_path)
        try:
            config_file_to_load = find_config_file(dummy_path if dummy_path.exists() else None)
        except ConfigurationError as ce_after_dummy:
            print(f"Critical: Could not find or create a config file. Proceeding with built-in defaults. Error: {ce_after_dummy}")
            project_config = ProjectConfig()
            if hasattr(project_config, 'logging') and project_config.logging:
                logging_config.setup_logging(project_config.logging) # type: ignore
            else:
                default_log_cfg_dict = {'level': 'INFO', 'format': logging_config.DEFAULT_LOG_FORMAT}
                logging_config.setup_logging(default_log_cfg_dict)

            container.logger().warning("Logging initialized with default Pydantic model settings due to config load failure.")
            container.config.from_pydantic(project_config, exclude_unset=False)
            container.wire(
                modules=[
                    __name__,
                    "dxfplanner.services.dxf_generation_service",
                    "dxfplanner.cli"
                ]
            )
            return project_config

    try:
        project_config = load_config_from_yaml(config_file_path=config_file_to_load)
        print(f"Configuration loaded successfully from: {config_file_to_load}")
    except ConfigurationError as e:
        print(f"Error loading configuration from {config_file_to_load}: {e}")
        print("Falling back to default Pydantic model configuration.")
        project_config = ProjectConfig()

    if hasattr(project_config, 'logging') and project_config.logging:
        logging_config.setup_logging(project_config.logging) # type: ignore
    else:
        default_log_cfg_loaded_dict = {'level': 'INFO', 'format': logging_config.DEFAULT_LOG_FORMAT}
        if hasattr(project_config, 'project_name'):
            init_logger_temp = logging_config.get_logger_for_config(default_log_cfg_loaded_dict)
            init_logger_temp.warning("ProjectConfig loaded but 'logging' section is missing. Using default logging settings.")
        logging_config.setup_logging(default_log_cfg_loaded_dict)

    init_logger = container.logger()
    if hasattr(project_config, 'logging') and project_config.logging and hasattr(project_config.logging, 'level'):
        init_logger.info(f"Logging initialized. Level: {project_config.logging.level}")
    else:
        init_logger.info(f"Logging initialized with default settings (level INFO).")

    container.config.from_pydantic(project_config, exclude_unset=False)

    # Directly provide the loaded ProjectConfig instance
    # This ensures services get the exact instance, not one re-validated from a potentially incomplete dict.
    container.project_config_instance_provider.override(providers.Object(project_config))

    container.wire(
        modules=[
            __name__,
            "dxfplanner.config.loaders",
            "dxfplanner.config.schemas",
            "dxfplanner.core.di",
            "dxfplanner.core.exceptions",
            "dxfplanner.core.logging_config",
            "dxfplanner.domain.interfaces",
            "dxfplanner.domain.models.common",
            "dxfplanner.domain.models.dxf_models",
            "dxfplanner.domain.models.geo_models",
            "dxfplanner.geometry.operations",
            "dxfplanner.geometry.transformations",
            "dxfplanner.geometry.utils",
            "dxfplanner.io.readers.shapefile_reader",
            "dxfplanner.io.readers.geojson_reader",
            "dxfplanner.io.writers.dxf_writer",
            "dxfplanner.io.writers.components.dxf_entity_converter_service",
            "dxfplanner.io.writers.components.dxf_resource_setup_service",
            "dxfplanner.io.writers.components.dxf_viewport_setup_service",
            "dxfplanner.services.orchestration_service",
            "dxfplanner.services.pipeline_service",
            "dxfplanner.services.layer_processor_service",
            "dxfplanner.services.style_service",
            "dxfplanner.services.validation_service",
            "dxfplanner.services.legend_generation_service",
            "dxfplanner.services.geoprocessing.attribute_mapping_service",
            "dxfplanner.services.geoprocessing.coordinate_service",
            "dxfplanner.services.geoprocessing.label_placement_service",
            "dxfplanner.cli"
        ]
    )
    init_logger.info("DI container configured and wired.")
    return project_config

# Example of how this app.py might be run (e.g., for testing or simple execution)
if __name__ == "__main__":
    # Initialize application (config, logging, DI)
    project_config_instance = initialize_app()
    logger = container.logger()

    logger.info(f"DXFPlanner app.py direct execution example starting with config: {project_config_instance.project_name or 'Default Project'}.")
    logger.info("This example attempts to run main_runner. Ensure 'config.yml' (or equivalent) is correctly set up.")

    # Determine output path from config, as CLI is not used here.
    example_output_file = "test_data/output/app_py_generated_example.dxf" # Default for this example
    output_path_from_config = None

    if project_config_instance.dxf_writer and project_config_instance.dxf_writer.output_filepath:
        output_path_from_config = Path(project_config_instance.dxf_writer.output_filepath).resolve()
    elif project_config_instance.io and project_config_instance.io.output_filepath: # Fallback to older general output_filepath
        output_path_from_config = Path(project_config_instance.io.output_filepath).resolve()

    if output_path_from_config:
        example_output_file = str(output_path_from_config)
        logger.info(f"Output path for this example run will be: {example_output_file} (from configuration)")
    else:
        logger.warning(f"No output path found in configuration (dxf_writer.output_filepath or io.output_filepath). Using default: {example_output_file}")
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
