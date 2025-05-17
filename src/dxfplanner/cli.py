import asyncio
from pathlib import Path
from typing import Optional

import typer

# Application initialization and main runner logic
from dxfplanner.app import initialize_app, main_runner, container
from dxfplanner.core.exceptions import DXFPlannerBaseError
from dxfplanner.config.schemas import ProjectConfig
from dxfplanner.core import logging_config

# Create a Typer application instance
cli_app = typer.Typer(
    name="dxfplanner",
    help="DXFPlanner: A tool for autogenerating DXF files from geodata.",
    add_completion=False # Can be enabled if shell completion is desired later
)

# --- Early Logging Setup --- ADDED BLOCK
# Call setup_logging with its internal defaults immediately.
# This ensures Loguru and its stdlib interceptor are active ASAP.
# The call from initialize_app() later will refine it with loaded config.
logging_config.setup_logging()
# --- End Early Logging Setup ---

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
    try:
        # project_config = initialize_app() # OLD: initialize_app returns container now
        initialized_container = initialize_app() # NEW: store the container
        # ctx.obj = project_config # OLD: this would set ctx.obj to the container
        ctx.obj = initialized_container.project_config_instance_provider() # NEW: get Pydantic model from provider

        # logger = container.logger() # This was commented out, container is global or from initialized_container
        # Get logger from the initialized container if needed here for debug
        # cli_logger = initialized_container.logger()
        # cli_logger.debug(f"CLI common_options: ProjectConfig instance set in ctx.obj")

    except DXFPlannerBaseError as e:
        # Use Typer's way to print errors and exit for CLI consistency
        typer.secho(f"Error during application initialization: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected critical error during initialization: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@cli_app.command(
    name="generate",
    help="Generate a DXF file based on sources defined in ProjectConfig (e.g., config.yml)."
)
def generate_dxf(
    ctx: typer.Context, # Added context to access ProjectConfig
    # source_file: Path = typer.Option(
    #     ..., # Makes it a required option
    #     "--source", "-s",
    #     help="Path to the source geodata file (e.g., .shp, .geojson).",
    #     exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True
    # ), # Removed: Sources are now defined in ProjectConfig
    output_file: Optional[Path] = typer.Option( # Made optional
        None, # Default to None
        "--output", "-o",
        help="Path for the generated DXF file. Overrides config if set.",
        writable=True, resolve_path=True # resolve_path helps ensure it's absolute
    ),
    # source_crs: Optional[str] = typer.Option(
    #     None, "--source-crs",
    #     help="Source Coordinate Reference System (e.g., EPSG:4326). Optional if defined in source or config."
    # ), # Removed: Source CRS is now defined in ProjectConfig per source
    target_crs: Optional[str] = typer.Option(
        None, "--target-crs",
        help="Target Coordinate Reference System for DXF output (e.g., EPSG:25832). Optional if defined in config."
    )
):
    """
    Processes geodata sources defined in ProjectConfig and generates a DXF file.
    Output path is determined by --output CLI option, then config settings.
    """
    logger = container.logger() # Logger is now configured and available
    project_config: ProjectConfig = ctx.obj # Get ProjectConfig from context

    try:
        final_output_path_str: Optional[str] = None

        if output_file:
            final_output_path_str = str(output_file)
            logger.info(f"CLI command: generate. Output path specified via --output: {final_output_path_str}")
        else:
            logger.debug("CLI --output not specified, checking configuration for output_filepath.")
            if project_config.dxf_writer and project_config.dxf_writer.output_filepath:
                final_output_path_str = str(Path(project_config.dxf_writer.output_filepath).resolve())
                logger.info(f"CLI command: generate. Output path from config (dxf_writer.output_filepath): {final_output_path_str}")

        if not final_output_path_str:
            err_msg = "Error: Output file path must be provided via --output option or in configuration (dxf_writer.output_filepath)."
            logger.error(err_msg)
            typer.secho(err_msg, fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        logger.info(f"Final output path determined: {final_output_path_str}")

        if target_crs:
            logger.debug(f"Target CRS specified via CLI: {target_crs}")

        Path(final_output_path_str).parent.mkdir(parents=True, exist_ok=True)

        success_status = asyncio.run(main_runner( # CAPTURE RETURN VALUE
            output_file=final_output_path_str,
        ))

        if success_status: # CHECK STATUS
            typer.secho(f"Successfully generated DXF: {final_output_path_str}", fg=typer.colors.GREEN)
        else:
            # Error messages should have already been logged by main_runner or its callees
            # The typer.secho calls in the except blocks below will handle CLI error output
            # We just need to ensure we exit with an error code if success_status is False
            # and no specific exception was caught by generate_dxf's own try/except.
            # However, main_runner's exceptions are caught internally and logged, not re-raised to here.
            # So if success_status is False, it means an error was handled in main_runner.
            # We should ensure cli.py also reports a failure to the user via typer and exits.
            logger.error(f"DXF generation reported failure from main_runner for: {final_output_path_str}") # Log it here too
            typer.secho(f"DXF generation failed for {final_output_path_str}. Check logs for details.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) # Ensure exit with error code

    except DXFPlannerBaseError as e:
        logger.error(f"DXF generation failed: {e}", exc_info=True) # Log detailed error
        typer.secho(f"Error during DXF generation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        logger.exception(f"An unexpected critical error occurred during DXF generation. Error: {e}")
        typer.secho(f"DEBUG: ENTERING except Exception as e block in CLI for: {e}", fg=typer.colors.YELLOW, err=True) # DEBUG
        typer.secho(f"An unexpected critical error occurred: {e}", fg=typer.colors.RED, err=True)
        typer.secho("DEBUG: ABOUT TO RAISE typer.Exit(code=1) FROM CLI", fg=typer.colors.YELLOW, err=True) # DEBUG
        raise typer.Exit(code=1)
        # typer.secho("DEBUG: THIS SHOULD NOT PRINT IF TYPER.EXIT WORKS", fg=typer.colors.YELLOW, err=True) # DEBUG

# Additional commands could be added here, e.g., for validation, config management.
# @cli_app.command(name="validate-config")
# def validate_config_cmd(config_path: Path = ...):
#     pass

if __name__ == "__main__":
    cli_app() # Runs the Typer CLI application
