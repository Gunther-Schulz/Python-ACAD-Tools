"""Concrete implementation of the IProjectOrchestrator interface."""
import os
import time  # Added for performance monitoring
from typing import Dict, Optional, List

import geopandas as gpd

try:
    from ezdxf.document import Drawing
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None) # type: ignore
    EZDXF_AVAILABLE = False

from ..interfaces.project_orchestrator_interface import IProjectOrchestrator
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.config_loader_interface import IConfigLoader
from ..interfaces.data_source_interface import IDataSource
from ..interfaces.geometry_processor_interface import IGeometryProcessor
from ..interfaces.style_applicator_interface import IStyleApplicator
from ..interfaces.data_exporter_interface import IDataExporter

from ..domain.config_models import (
    SpecificProjectConfig, StyleConfig, AppConfig, GeomLayerDefinition, AllOperationParams
)
from ..domain.exceptions import (
    ConfigError, ProcessingError, DXFProcessingError, GeometryError
)
# Assuming direct instantiation of LoggingService as a fallback if not injected.
# In a more complex app, a DI container would handle this.
from .logging_service import LoggingService


class ProjectOrchestratorService(IProjectOrchestrator):
    """Orchestrates the entire project processing workflow."""

    def __init__(
        self,
        logging_service: ILoggingService,
        config_loader: IConfigLoader,
        data_source: IDataSource,
        geometry_processor: IGeometryProcessor,
        style_applicator: IStyleApplicator,
        data_exporter: IDataExporter
    ):
        self._logger = logging_service.get_logger(__name__)
        self._config_loader = config_loader
        self._data_source = data_source
        self._geometry_processor = geometry_processor
        self._style_applicator = style_applicator
        self._data_exporter = data_exporter
        self._logger.info("ProjectOrchestratorService initialized.")

    def process_project(self, project_name: str) -> None:
        start_time = time.time()  # Performance monitoring start
        self._logger.info(f"Starting processing for project: {project_name}")
        active_layers: Dict[str, gpd.GeoDataFrame] = {}
        dxf_drawing: Optional[Drawing] = None
        app_config: Optional[AppConfig] = None
        project_config: Optional[SpecificProjectConfig] = None
        style_config: Optional[StyleConfig] = None

        try:
            # 1. Load Configurations
            self._logger.debug("Loading application configuration...")
            app_config = self._config_loader.get_app_config()
            if not app_config:
                raise ConfigError("Failed to load application configuration.")
            self._logger.info("Application configuration loaded.")

            self._logger.debug(f"Loading project configuration for '{project_name}'...")
            project_config = self._config_loader.load_specific_project_config(
                project_name,
                app_config.projects_root_dir
            )
            if not project_config:
                raise ConfigError(f"Failed to load configuration for project '{project_name}'.")
            self._logger.info(f"Project configuration for '{project_name}' loaded.")

            self._logger.debug("Loading style configuration...")
            # Use project-specific style presets file if specified, otherwise fall back to global
            style_file_path = project_config.main.style_presets_file or app_config.global_styles_file

            # If the style file path is relative, resolve it relative to the project directory
            if not os.path.isabs(style_file_path):
                # Check if it exists relative to project directory first
                project_style_path = os.path.join(app_config.projects_root_dir, project_name, style_file_path)
                if os.path.exists(project_style_path):
                    style_file_path = project_style_path
                    self._logger.debug(f"Using project-specific style file: {style_file_path}")
                else:
                    # Use as relative to root directory
                    style_file_path = os.path.join(os.getcwd(), style_file_path)
                    self._logger.debug(f"Using global style file: {style_file_path}")
            else:
                self._logger.debug(f"Using absolute style file path: {style_file_path}")

            style_config = self._config_loader.load_global_styles(style_file_path)
            if not style_config:
                # This might be acceptable if no styling is applied, but log a warning.
                self._logger.warning("Style configuration could not be loaded or is empty.")
                style_config = StyleConfig() # Empty default
            else:
                self._logger.info(f"Style configuration loaded from: {style_file_path}")

            # ColorConfig is loaded by StyleApplicatorService via its IConfigLoader instance.

            # 2. Load DXF Data Source (if applicable) with fail-fast validation
            dxf_file_path = os.path.join(app_config.projects_root_dir, project_name, project_config.main.dxf_filename)
            dxf_file_path = os.path.normpath(dxf_file_path)  # Normalize path for consistency

            # Check if any layers require DXF processing
            layers_requiring_dxf = [ld for ld in project_config.geom_layers if ld.dxf_layer]
            if layers_requiring_dxf:
                self._logger.debug(f"Found {len(layers_requiring_dxf)} layers requiring DXF: {[ld.name for ld in layers_requiring_dxf]}")

                if not os.path.exists(dxf_file_path):
                    layer_names = [ld.name for ld in layers_requiring_dxf]
                    error_msg = (f"DXF file '{dxf_file_path}' not found, but layers {layer_names} "
                               f"require DXF processing. Cannot proceed without DXF source.")
                    self._logger.error(error_msg)
                    raise ConfigError(error_msg)

                self._logger.debug(f"Attempting to load DXF document from: {dxf_file_path}")
                dxf_drawing = self._data_source.load_dxf_file(dxf_file_path)
                if dxf_drawing:
                    self._logger.info(f"DXF document '{dxf_file_path}' loaded successfully.")
                else:
                    error_msg = (f"DXF document '{dxf_file_path}' could not be loaded by data source "
                               f"(returned None), but layers {[ld.name for ld in layers_requiring_dxf]} require it.")
                    self._logger.error(error_msg)
                    raise DXFProcessingError(error_msg)
            else:
                # No layers require DXF, but try to load if file exists anyway (for potential updates)
                if os.path.exists(dxf_file_path):
                    self._logger.debug(f"Loading DXF document for potential updates from: {dxf_file_path}")
                    try:
                        dxf_drawing = self._data_source.load_dxf_file(dxf_file_path)
                        if dxf_drawing:
                            self._logger.info(f"DXF document '{dxf_file_path}' loaded successfully for potential updates.")
                        else:
                            self._logger.warning(f"DXF document '{dxf_file_path}' could not be loaded (returned None).")
                    except Exception as e:
                        self._logger.warning(f"Failed to load DXF file '{dxf_file_path}': {e}. Proceeding without DXF.")
                        dxf_drawing = None
                else:
                    self._logger.info(f"DXF file '{dxf_file_path}' not found, but no layers require DXF processing. Proceeding without DXF data.")
                    dxf_drawing = None

            # 3. Process Geometric Layer Definitions
            self._logger.info(f"Processing {len(project_config.geom_layers)} geometric layer definitions...")
            pending_operations_layers = []  # Track layers that need operations processing

            for layer_def in project_config.geom_layers:
                self._logger.debug(f"Processing layer definition: '{layer_def.name}'")
                try:
                    project_root = os.path.join(app_config.projects_root_dir, project_name)
                    gdf = self._geometry_processor.create_layer_from_definition(
                        layer_def, dxf_drawing, style_config, project_config.main.crs, project_root
                    )
                    if gdf is not None:
                        self._logger.info(f"Successfully created/loaded base for layer '{layer_def.name}'. Features: {len(gdf)}")
                        active_layers[layer_def.name] = gdf

                        # Apply inline operations if any
                        if layer_def.operations:
                            self._logger.debug(f"Applying {len(layer_def.operations)} inline operations to layer '{layer_def.name}'...")
                            current_op_input_gdf = gdf
                            for i, op_params in enumerate(layer_def.operations):
                                self._logger.debug(f"  Applying inline operation #{i+1} ('{op_params.type}') to '{layer_def.name}'")

                                # Prepare source_layers for the operation. For inline ops, this is tricky.
                                # Assume for now the operation primarily acts on the current layer_def.name.
                                # If other layers are needed, they must be already in active_layers.
                                # This might need refinement based on how ops in OLDAPP used context.
                                operation_source_layers = active_layers.copy() # Give op access to all current layers
                                if layer_def.name not in operation_source_layers and current_op_input_gdf is not None:
                                     # Ensure the current GDF being processed is available under its own name if op needs it explicitly
                                     operation_source_layers[layer_def.name] = current_op_input_gdf

                                result_gdf = self._geometry_processor.apply_operation(op_params, operation_source_layers)
                                active_layers[layer_def.name] = result_gdf # Operation output replaces the layer
                                current_op_input_gdf = result_gdf # For the next inline op
                                self._logger.debug(f"  Finished inline operation #{i+1} ('{op_params.type}') on '{layer_def.name}'. Result features: {len(result_gdf) if result_gdf is not None else 'None'}")
                    elif layer_def.operations and not layer_def.geojson_file and not layer_def.dxf_layer and not layer_def.shape_file:
                        # Check if this is an operations-only layer
                        self._logger.debug(f"Layer '{layer_def.name}' is operations-only - adding to pending operations list")
                        pending_operations_layers.append(layer_def)
                    else:
                        self._logger.warning(f"Layer '{layer_def.name}' could not be created/loaded (returned None). Skipping.")
                except Exception as e:
                    self._logger.error(f"Failed to process layer definition '{layer_def.name}': {e}", exc_info=True)
                    # Decide: continue with other layers or halt?
                    # For PIL 3, an error in one layer definition might not need to halt all project processing if others are independent.
                    # However, if other layers depend on this one, they might fail too.
                    self._logger.warning(f"Continuing to next layer definition after error in '{layer_def.name}'.")

            # Process operations-only layers after all base layers are created
            if pending_operations_layers:
                self._logger.info(f"Processing {len(pending_operations_layers)} operations-only layers...")
                for layer_def in pending_operations_layers:
                    self._logger.debug(f"Processing operations-only layer '{layer_def.name}'")
                    try:
                        result_gdf = None
                        for i, op_params in enumerate(layer_def.operations):
                            self._logger.debug(f"  Applying operation #{i+1} ('{op_params.type}') to operations-only layer '{layer_def.name}'")

                            # Use all currently active layers as source for operations
                            result_gdf = self._geometry_processor.apply_operation(op_params, active_layers)

                            # Update the active layers with the result for subsequent operations
                            if result_gdf is not None:
                                active_layers[layer_def.name] = result_gdf
                                self._logger.debug(f"  Finished operation #{i+1} ('{op_params.type}') on '{layer_def.name}'. Result features: {len(result_gdf)}")
                            else:
                                self._logger.warning(f"  Operation #{i+1} ('{op_params.type}') on '{layer_def.name}' returned None")
                                break

                        if result_gdf is not None:
                            self._logger.debug(f"Successfully processed operations-only layer '{layer_def.name}'. Features: {len(result_gdf)}")
                        else:
                            self._logger.warning(f"Operations-only layer '{layer_def.name}' processing resulted in None")

                    except Exception as e:
                        self._logger.error(f"Failed to process operations-only layer '{layer_def.name}': {e}", exc_info=True)

            self._logger.info("Finished processing all geometric layer definitions.")

            # 4. Apply Styles & Export (Simplified logic for now)
            # TODO PIL 3: Refine export paths and conditions based on project_config.main settings
            # (e.g., output_dxf_path, shapefile_output_dir, geopackage_output_path needs to be added to ProjectMainSettings)

            # DXF Export Example (create new DXF if needed and output is desired)
            if project_config.main.output_dxf_path and \
               (project_config.main.export_format == "dxf" or project_config.main.export_format == "all"):

                output_dxf_path = project_config.main.output_dxf_path
                # Ensure path is absolute or resolve relative to project root
                if not os.path.isabs(output_dxf_path):
                    output_dxf_path = os.path.join(app_config.projects_root_dir, project_name, output_dxf_path)
                output_dxf_path = os.path.normpath(output_dxf_path)

                # Check if we need to create a new DXF or update an existing one
                if not dxf_drawing:
                    # Try to load existing DXF from output path first
                    if os.path.exists(output_dxf_path):
                        self._logger.info(f"Loading existing DXF for update from: {output_dxf_path}")
                        try:
                            dxf_drawing = self._data_source.load_dxf_file(output_dxf_path)
                            if dxf_drawing:
                                self._logger.info("Existing DXF loaded successfully for update.")
                            else:
                                self._logger.warning("Failed to load existing DXF, will create new one.")
                        except Exception as e:
                            self._logger.warning(f"Failed to load existing DXF for update: {e}. Will create new one.")
                            dxf_drawing = None

                    # If still no drawing, create a new one
                    if not dxf_drawing:
                        self._logger.info("Creating new DXF drawing for export...")
                        try:
                            import ezdxf
                            dxf_drawing = ezdxf.new('R2010')  # Create a new DXF drawing
                            self._logger.info("New DXF drawing created successfully.")
                        except ImportError:
                            self._logger.error("ezdxf library not available. Cannot create new DXF drawing.")
                            dxf_drawing = None
                        except Exception as e:
                            self._logger.error(f"Failed to create new DXF drawing: {e}", exc_info=True)
                            dxf_drawing = None

                if dxf_drawing:
                    self._logger.info(f"Preparing DXF export to: {output_dxf_path}")
                    os.makedirs(os.path.dirname(output_dxf_path), exist_ok=True)

                    # Clear existing entities from layers that will be updated
                    layers_to_update = []
                    for layer_name, gdf in active_layers.items():
                        layer_def_for_style = next((ld for ld in project_config.geom_layers if ld.name == layer_name), None)
                        if layer_def_for_style and layer_def_for_style.update_dxf:
                            layers_to_update.append(layer_name)

                    if layers_to_update:
                        self._logger.debug(f"Clearing existing entities from layers: {', '.join(layers_to_update)}")
                        try:
                            # Import the utility function from the new location
                            from ..adapters.dxf import remove_entities_by_layer

                            # Use the proper removal function from OLDAPP
                            deleted_count = remove_entities_by_layer(
                                dxf_drawing,
                                layers_to_update,
                                script_identifier="python-acad-tools"
                            )
                            self._logger.debug(f"Removed {deleted_count} existing entities from {len(layers_to_update)} layers")

                        except Exception as e:
                            self._logger.warning(f"Error clearing existing entities from layers: {e}", exc_info=True)

                    self._logger.debug("Applying styles and adding geometries to DXF document...")
                    for layer_name, gdf in active_layers.items():
                        layer_def_for_style = next((ld for ld in project_config.geom_layers if ld.name == layer_name), None)
                        if layer_def_for_style and layer_def_for_style.update_dxf and style_config:
                            named_style = self._style_applicator.get_style_for_layer(layer_name, layer_def_for_style, style_config)
                            if named_style:
                                self._logger.debug(f"Applying style '{named_style.name if hasattr(named_style, 'name') else 'inline'}' to DXF layer '{layer_name}'")
                                self._style_applicator.apply_styles_to_dxf_layer(dxf_drawing, layer_name, named_style)
                            else:
                                self._logger.debug(f"No specific style found for DXF layer '{layer_name}'. Default DXF layer appearance will be used.")

                                # Add geometries from GeoDataFrame to DXF
                                self._logger.debug(f"Adding {len(gdf)} geometries to DXF layer '{layer_name}'")
                                try:
                                    self._style_applicator.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, named_style, layer_def_for_style)
                                except Exception as e:
                                    self._logger.error(f"Failed to add geometries to DXF layer '{layer_name}': {e}", exc_info=True)

                    self._logger.info(f"Exporting DXF document to: {output_dxf_path}")
                    self._data_exporter.export_to_dxf(dxf_drawing, output_dxf_path, project_config)
                else:
                    self._logger.error("DXF export requested but no DXF drawing available and failed to create new one.")
            elif (project_config.main.export_format == "dxf" or project_config.main.export_format == "all"):
                self._logger.info("DXF export selected but 'output_dxf_path' not configured in project settings. Skipping DXF export.")

            # Shapefile Export Example
            if project_config.main.shapefile_output_dir and (project_config.main.export_format == "shp" or project_config.main.export_format == "all") :
                shp_output_dir = os.path.join(app_config.projects_root_dir, project_name, project_config.main.shapefile_output_dir)
                self._logger.info(f"Exporting layers to Shapefiles in directory: {shp_output_dir}")
                for layer_name, gdf in active_layers.items():
                    if gdf.empty:
                        self._logger.debug(f"Skipping Shapefile export for empty layer: {layer_name}")
                        continue
                    # Potentially apply GDF styling if that influences SHP appearance (usually not beyond attributes)
                    # styled_gdf = self._style_applicator.apply_style_to_geodataframe(gdf, resolved_style_for_layer, layer_name)
                    output_shp_path = os.path.join(shp_output_dir, f"{layer_name}.shp")
                    self._logger.debug(f"Exporting layer '{layer_name}' to Shapefile: {output_shp_path}")
                    self._data_exporter.export_to_shapefile(gdf, output_shp_path)

            # GeoPackage Export Example
            if project_config.main.output_geopackage_path and \
               (project_config.main.export_format == "gpkg" or project_config.main.export_format == "all"):
                output_gpkg_path = project_config.main.output_geopackage_path
                if not os.path.isabs(output_gpkg_path):
                    output_gpkg_path = os.path.join(app_config.projects_root_dir, project_name, output_gpkg_path)
                output_gpkg_path = os.path.normpath(output_gpkg_path)

                if active_layers:
                    self._logger.info(f"Exporting layers to GeoPackage: {output_gpkg_path}")
                    os.makedirs(os.path.dirname(output_gpkg_path), exist_ok=True)
                    self._data_exporter.export_layers_to_geopackage(active_layers, output_gpkg_path)
                else:
                    self._logger.info("No active layers to export to GeoPackage.")
            elif (project_config.main.export_format == "gpkg" or project_config.main.export_format == "all"):
                self._logger.info("GeoPackage export selected but 'output_geopackage_path' not configured. Skipping GeoPackage export.")

            self._logger.info(f"Successfully finished processing for project: {project_name}")

        except ConfigError as e:
            self._logger.critical(f"Configuration error during project '{project_name}' processing: {e}", exc_info=True)
            # Depending on severity, might re-raise or just log that project processing failed.
            raise # Re-raise critical config errors
        except DXFProcessingError as e:
            self._logger.error(f"DXF processing error during project '{project_name}': {e}", exc_info=True)
            raise
        except GeometryError as e:
            self._logger.error(f"Geometry error during project '{project_name}': {e}", exc_info=True)
            raise
        except ProcessingError as e:
            self._logger.error(f"General processing error during project '{project_name}': {e}", exc_info=True)
            raise
        except Exception as e: # Catch-all for unexpected errors
            self._logger.critical(f"Unexpected critical error during project '{project_name}' processing: {e}", exc_info=True)
            raise ProcessingError(f"Unexpected critical error in project '{project_name}': {e}") from e
