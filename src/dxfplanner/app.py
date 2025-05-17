import asyncio
from pathlib import Path
from typing import Optional
from dependency_injector import providers
import sys

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
) -> bool:
    """Main application logic execution using the configured DxfGenerationService."""
    logger = container.logger()
    logger.info("DXFPlanner application starting...")
    success = False

    try:
        dxf_service: IDxfGenerationService = container.dxf_generation_service() # type: ignore
        await dxf_service.generate_dxf_from_source(
            output_dxf_path=Path(output_file),
        )
        logger.info(f"DXF generation complete. Output: {output_file}")
        success = True

    except DXFPlannerBaseError as e:
        logger.error(f"Application error: {e}", exc_info=True)
        success = False
    except Exception as e:
        logger.error(f"An unexpected critical error occurred: {e}", exc_info=True)
        success = False

    return success

def initialize_app(config_path: Optional[str] = None) -> DIContainer:
    """Initializes the application: loads config, sets up logging, and wires DI container."""

    # Load configuration using the utility function
    cfg: ProjectConfig = load_config_from_yaml(config_file_path=config_path)

    # Initialize logging using the loaded configuration
    # logging_config.setup_logging(level=cfg.logging.level, format_str=cfg.logging.format) # CHANGE THIS
    logging_config.setup_logging(config=cfg.logging) # TO THIS

    logger = logging_config.get_logger(__name__)
    # logger.info(f"Logging initialized. Level: {cfg.logging.level}") # This will be logged by setup_logging itself

    # Provide the loaded Pydantic config model instance to the DI container
    container.project_config_instance_provider.override(providers.Object(cfg))

    # Load the configuration dictionary into the container's config provider
    # This makes individual config values accessible via container.config.section.key()
    container.config.from_dict(cfg.model_dump()) # Use .model_dump() for Pydantic v2+

    # Wire the container AFTER config is loaded and provided
    # Pass relevant modules for wiring (e.g., services, readers, operations)
    # Example: container.wire(modules=[sys.modules[__name__], dxfplanner.services, dxfplanner.io.readers])
    # For now, let's assume wiring might be more extensive or handled by specific service needs.
    # If auto-wiring based on type hints is used, ensure modules are passed.
    # For now, let's be explicit about modules that might contain Inject markers or need wiring.
    # We need to ensure that modules using dependency_injector.wiring.inject or providers.Resource are wired.
    # This usually includes modules with @inject decorators or where services are instantiated.
    # The CLI module itself often needs wiring if its commands are injected.
    try:
        # Determine all modules that might need wiring.
        # This should ideally include all modules where @inject is used or where
        # providers are directly accessed from the container outside of DI-managed classes.
        import dxfplanner.services
        import dxfplanner.io.readers
        import dxfplanner.io.writers
        import dxfplanner.geometry
        import dxfplanner.cli # CLI module itself often uses injected components

        container.wire(modules=[
            sys.modules[__name__], # Current module (app.py)
            dxfplanner.services,
            dxfplanner.io.readers,
            dxfplanner.io.writers,
            dxfplanner.geometry,
            dxfplanner.cli
        ])
        logger.info("DI container configured and wired.")
    except Exception as e_wire:
        logger.error(f"Error wiring DI container: {e_wire}", exc_info=True)
        # Depending on severity, might re-raise or handle
        raise

    return container

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
        success = asyncio.run(main_runner(
            output_file=example_output_file
        ))
        if success:
            logger.info(f"app.py direct execution finished. Check: {example_output_file}")
        else:
            logger.error(f"Error during app.py direct execution: {success}", exc_info=True)
    except DXFPlannerBaseError as e_app_run:
        logger.error(f"Error during app.py direct execution: {e_app_run}", exc_info=True)
    except Exception as e_app_general:
        logger.error(f"Unexpected critical error during app.py direct execution: {e_app_general}", exc_info=True)
