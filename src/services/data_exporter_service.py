"""Concrete implementation of the IDataExporter interface."""
import os
from typing import List, Dict, Optional, Any

import geopandas as gpd

# Direct import for ezdxf as a hard dependency
import ezdxf
from ezdxf.document import Drawing

from ..interfaces.data_exporter_interface import IDataExporter
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.config_models import SpecificProjectConfig
from ..domain.exceptions import ProcessingError, DXFProcessingError


class DataExporterService(IDataExporter):
    """Service for exporting geometric data to various formats."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)

    def _ensure_output_dir(self, file_path: str) -> None:
        """Ensures the output directory for the given file_path exists."""
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                self._logger.info(f"Created output directory: {output_dir}")
            except OSError as e:
                self._logger.error(f"Failed to create output directory {output_dir}: {e}", exc_info=True)
                raise ProcessingError(f"Failed to create output directory {output_dir}: {e}") from e

    def export_to_dxf(
        self,
        drawing: Drawing,
        output_file_path: str,
        project_config: SpecificProjectConfig
    ) -> None:
        self._logger.info(f"Exporting DXF to: {output_file_path}")

        self._ensure_output_dir(output_file_path)

        dxf_version = project_config.main.dxf_version # Assumes ProjectMainSettings has dxf_version
        if not dxf_version:
            dxf_version = "R2010" # A safe default, consistent with domain.config_models
            self._logger.warning(f"DXF version not specified in project_config, defaulting to {dxf_version}.")

        try:
            drawing.saveas(output_file_path)
            self._logger.info(f"Successfully exported DXF to: {output_file_path} (version: {dxf_version})")
        except ezdxf.DXFError as e: # Catch specific ezdxf errors
            self._logger.error(f"ezdxf.DXFError during DXF export to {output_file_path}: {e}", exc_info=True)
            raise ProcessingError(f"ezdxf.DXFError exporting to {output_file_path}: {e}") from e
        except IOError as e:
            self._logger.error(f"IOError during DXF export to {output_file_path}: {e}", exc_info=True)
            raise ProcessingError(f"IOError exporting to {output_file_path}: {e}") from e
        except Exception as e: # Catch any other unexpected errors
            self._logger.error(f"Unexpected error during DXF export to {output_file_path}: {e}", exc_info=True)
            raise ProcessingError(f"Unexpected error exporting to {output_file_path}: {e}") from e

    def export_to_shapefile(
        self,
        gdf: gpd.GeoDataFrame,
        output_file_path: str,
        **kwargs: Any
    ) -> None:
        self._logger.info(f"Exporting GeoDataFrame to Shapefile: {output_file_path}")
        self._ensure_output_dir(output_file_path)

        if gdf.empty:
            self._logger.warning(f"GeoDataFrame for Shapefile export to '{output_file_path}' is empty. Exporting empty Shapefile.")
            # GeoPandas handles empty GDF export gracefully by creating an empty shapefile.

        try:
            gdf.to_file(output_file_path, driver="ESRI Shapefile", **kwargs)
            self._logger.info(f"Successfully exported GeoDataFrame to Shapefile: {output_file_path}")
        except Exception as e: # Fiona/GeoPandas can raise various errors
            self._logger.error(f"Error exporting GeoDataFrame to Shapefile {output_file_path}: {e}", exc_info=True)
            raise ProcessingError(f"Error exporting to Shapefile {output_file_path}: {e}") from e

    def export_layers_to_geopackage(
        self,
        layers: Dict[str, gpd.GeoDataFrame],
        output_file_path: str,
        **kwargs: Any
    ) -> None:
        self._logger.info(f"Exporting {len(layers)} layer(s) to GeoPackage: {output_file_path}")
        self._ensure_output_dir(output_file_path)

        if not layers:
            self._logger.warning("No layers provided for GeoPackage export. Nothing to do.")
            return

        # Ensure the GeoPackage file is new or overwritten for the first layer if mode='w' (default for to_file)
        # Subsequent layers will append.
        first_layer_exported = False
        for layer_name, gdf in layers.items():
            self._logger.debug(f"Exporting layer '{layer_name}' to GeoPackage '{output_file_path}'.")
            if gdf.empty:
                self._logger.warning(f"GeoDataFrame for layer '{layer_name}' is empty. Skipping this layer for GeoPackage export.")
                continue

            try:
                # For the first layer, default 'to_file' behavior will create/overwrite.
                # For subsequent layers, they will be added if the GPKG exists.
                # GeoPandas handles this logic internally based on the file existence and driver.
                gdf.to_file(output_file_path, layer=layer_name, driver="GPKG", **kwargs)
                self._logger.info(f"Successfully exported layer '{layer_name}' to GeoPackage: {output_file_path}")
                first_layer_exported = True # Mark that at least one layer (potentially the file creator) was processed
            except Exception as e:
                self._logger.error(f"Error exporting layer '{layer_name}' to GeoPackage {output_file_path}: {e}", exc_info=True)
                # Decide on error strategy: continue with other layers or raise immediately?
                # For PIL 2, raising immediately is safer to alert user of any failure.
                raise ProcessingError(f"Error exporting layer '{layer_name}' to GeoPackage {output_file_path}: {e}") from e

        if not first_layer_exported and layers: # Check if layers were provided but all were empty
             self._logger.info(f"All provided layers for GeoPackage '{output_file_path}' were empty. GeoPackage may not have been created or is empty.")
        elif first_layer_exported:
            self._logger.info(f"Finished exporting layers to GeoPackage: {output_file_path}")
