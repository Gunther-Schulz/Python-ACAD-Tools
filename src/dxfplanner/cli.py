import asyncio
from pathlib import Path
from typing import Optional

import typer

# Application initialization and main runner logic
from dxfplanner.app import initialize_app, main_runner, container
from dxfplanner.core.exceptions import DXFPlannerBaseError

# Create a Typer application instance
cli_app = typer.Typer(
    name="dxfplanner",
    help="DXFPlanner: A tool for autogenerating DXF files from geodata.",
    add_completion=False # Can be enabled if shell completion is desired later
)

@cli_app.callback()
def common_options(
    ctx: typer.Context,
    # Example of a common option, like a config file path, if needed globally
    # config_file: Optional[Path] = typer.Option(
    #     None, "--config", "-c", help="Path to the configuration YAML file.",
    #     exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True
    # )
):
    """
    DXFPlanner CLI - Manages application setup.
    Initialization (config loading, logging, DI) happens before commands run.
    """
    # Initialize the application (loads config, sets up logging, wires DI container)
    # The initialize_app function in app.py handles finding or creating a config.
    # If a --config option were used, it could be passed to initialize_app here.
    try:
        app_config = initialize_app()
        # Store the loaded config in context if other commands need to access it directly
        # although usually services will get config via DI.
        ctx.obj = app_config
        # logger = container.logger() # Get logger after init
        # logger.debug(f"CLI initialized with config: {app_config.model_dump_json(indent=2)}")
    except DXFPlannerBaseError as e:
        # Use Typer's way to print errors and exit for CLI consistency
        typer.secho(f"Error during application initialization: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected critical error during initialization: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@cli_app.command(
    name="generate",
    help="Generate a DXF file based on sources defined in AppConfig (e.g., config.yml)."
)
def generate_dxf(
    # source_file: Path = typer.Option(
    #     ..., # Makes it a required option
    #     "--source", "-s",
    #     help="Path to the source geodata file (e.g., .shp, .geojson).",
    #     exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True
    # ), # Removed: Sources are now defined in AppConfig
    output_file: Path = typer.Option(
        ..., # Makes it a required option
        "--output", "-o",
        help="Path for the generated DXF file.",
        writable=True, resolve_path=True # resolve_path helps ensure it's absolute
    ),
    # source_crs: Optional[str] = typer.Option(
    #     None, "--source-crs",
    #     help="Source Coordinate Reference System (e.g., EPSG:4326). Optional if defined in source or config."
    # ), # Removed: Source CRS is now defined in AppConfig per source
    target_crs: Optional[str] = typer.Option(
        None, "--target-crs",
        help="Target Coordinate Reference System for DXF output (e.g., EPSG:25832). Optional if defined in config."
    )
):
    """
    Processes geodata sources defined in AppConfig and generates a DXF file at OUTPUT_FILE.
    """
    logger = container.logger() # Logger is now configured and available
    logger.info(f"CLI command: generate. Output: {output_file}")
    if target_crs:
        logger.debug(f"Target CRS specified via CLI: {target_crs}")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(main_runner(
            # source_file=str(source_file), # Removed
            output_file=str(output_file),
            # source_crs=source_crs, # Removed
            target_crs=target_crs
        ))
        typer.secho(f"Successfully generated DXF: {output_file}", fg=typer.colors.GREEN)
    except DXFPlannerBaseError as e:
        logger.error(f"DXF generation failed: {e}", exc_info=True) # Log detailed error
        typer.secho(f"Error during DXF generation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"Unexpected critical error during DXF generation: {e}", exc_info=True)
        typer.secho(f"An unexpected critical error occurred: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

# Additional commands could be added here, e.g., for validation, config management.
# @cli_app.command(name="validate-config")
# def validate_config_cmd(config_path: Path = ...):
#     pass

if __name__ == "__main__":
    cli_app() # Runs the Typer CLI application
