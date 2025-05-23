"""Concrete implementation of the IDataSource interface."""
from typing import Optional, Dict

# Attempt to import ezdxf and define Drawing and readfile alias
try:
    import ezdxf
    from ezdxf.document import Drawing
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None) # Placeholder type
    def ezdxf_readfile_stub(filepath: str, **kwargs) -> Drawing:
        # This stub will only be called if EZDXF_AVAILABLE is False and code proceeds
        raise DXFProcessingError("ezdxf library is not installed or available for DXF processing.")
    ezdxf_readfile = ezdxf_readfile_stub # Assign stub to the name used by the interface
    EZDXF_AVAILABLE = False

from ..interfaces.data_source_interface import IDataSource # EZDXF_AVAILABLE might be from here too
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import DXFProcessingError, DataSourceError # Added DataSourceError
from .logging_service import LoggingService # Fallback
import geopandas as gpd # Added import


class DataSourceService(IDataSource):
    """Service for loading data sources, primarily DXF files and managing GeoDataFrames."""

    def __init__(self, logger_service: Optional[ILoggingService] = None):
        if logger_service:
            self._logger = logger_service.get_logger(__name__)
        else:
            self._logger_service_instance = LoggingService()
            self._logger = self._logger_service_instance.get_logger(__name__)
            self._logger.warning("DataSourceService initialized without injected logger. Using fallback.")

        # Check ezdxf availability on instantiation and log
        if not EZDXF_AVAILABLE:
            self._logger.error(
                "ezdxf library is not available. DXF loading will fail. Please install ezdxf."
            )
            # Depending on application strictness, could raise an error here
            # or allow attempts to load DXF to fail at runtime per method.

        self._geodataframes: Dict[str, gpd.GeoDataFrame] = {} # Added GDF store

    def load_dxf_file(self, file_path: str) -> Drawing:
        """Loads a DXF file from the given path."""
        self._logger.info(f"Attempting to load DXF file: {file_path}")

        if not EZDXF_AVAILABLE:
            # This case should ideally be prevented by checks before calling,
            # or by the application failing to start if ezdxf is a hard requirement.
            self._logger.error("load_dxf_file called but ezdxf is not available.")
            raise DXFProcessingError("ezdxf library is not installed or available.")

        try:
            # Use the potentially aliased/stubbed ezdxf.readfile from the top of this module
            # Or, if ezdxf was imported directly: doc = ezdxf.readfile(file_path)
            doc = ezdxf.readfile(file_path) # Assuming direct import if EZDXF_AVAILABLE is true
            self._logger.info(f"Successfully loaded DXF file: {file_path}")
            return doc
        except FileNotFoundError:
            self._logger.error(f"DXF file not found: {file_path}")
            # Let FileNotFoundError propagate as per interface docstring, or wrap if preferred
            raise
        except ezdxf.DXFStructureError as e:
            self._logger.error(f"Invalid DXF file structure {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid DXF file structure {file_path}: {e}") from e
        except IOError as e: # Catches other I/O issues like permission errors
            self._logger.error(f"IOError reading DXF file {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"IOError reading DXF file {file_path}: {e}") from e
        except Exception as e: # Catch-all for any other unexpected ezdxf loading errors
            self._logger.error(f"Unexpected error loading DXF file {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Unexpected error loading DXF file {file_path}: {e}") from e

    def load_geojson_file(self, file_path: str) -> gpd.GeoDataFrame:
        """Loads a GeoDataFrame from a GeoJSON file."""
        self._logger.info(f"Attempting to load GeoJSON file: {file_path}")
        try:
            gdf = gpd.read_file(file_path)
            self._logger.info(f"Successfully loaded GeoJSON file: {file_path}. CRS: {gdf.crs}, Features: {len(gdf)}")
            return gdf
        except FileNotFoundError:
            self._logger.error(f"GeoJSON file not found: {file_path}")
            raise # Re-raise FileNotFoundError as per interface contract/common practice
        except Exception as e:
            # This could catch various errors from GeoPandas if the file is malformed,
            # not a valid GeoJSON, or other I/O issues beyond FileNotFoundError.
            self._logger.error(f"Failed to load GeoJSON file {file_path}: {e}", exc_info=True)
            raise DataSourceError(f"Failed to load GeoJSON file {file_path}: {e}") from e

    def add_gdf(self, gdf: gpd.GeoDataFrame, layer_name: str) -> None:
        """Adds or replaces a GeoDataFrame in the in-memory store."""
        self._logger.info(f"Attempting to add GeoDataFrame for layer: '{layer_name}'")
        if not isinstance(gdf, gpd.GeoDataFrame):
            self._logger.error(f"Attempted to add a non-GeoDataFrame object for layer '{layer_name}'. Type was {type(gdf)}.")
            raise DataSourceError(f"Invalid type for add_gdf. Expected GeoDataFrame, got {type(gdf)} for layer '{layer_name}'.")

        if layer_name in self._geodataframes:
            self._logger.warning(f"Overwriting existing GeoDataFrame for layer: '{layer_name}'")
        self._geodataframes[layer_name] = gdf
        self._logger.info(f"Successfully added/updated GeoDataFrame for layer: '{layer_name}'. GDF info: {{gdf.info(verbose=False, buf=None)}}") # Basic info log

    def get_gdf(self, layer_name: str) -> gpd.GeoDataFrame:
        """Retrieves a GeoDataFrame from the in-memory store by layer name."""
        self._logger.info(f"Attempting to retrieve GeoDataFrame for layer: '{layer_name}'")
        try:
            gdf = self._geodataframes[layer_name]
            self._logger.info(f"Successfully retrieved GeoDataFrame for layer: '{layer_name}'.")
            return gdf
        except KeyError:
            self._logger.error(f"Layer '{layer_name}' not found in DataSourceService.")
            raise DataSourceError(f"Layer '{layer_name}' not found in DataSourceService.") from None # PEP 409
