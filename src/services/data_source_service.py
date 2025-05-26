"""Concrete implementation of the IDataSource interface."""
from typing import Optional, Dict, Any
import os

# Removed direct ezdxf import block and EZDXF_AVAILABLE logic
# try:
#     import ezdxf
#     from ezdxf.document import Drawing
#     EZDXF_AVAILABLE = True
# except ImportError:
#     Drawing = type(None) # Placeholder type
#     def ezdxf_readfile_stub(filepath: str, **kwargs) -> Drawing:
#         # This stub will only be called if EZDXF_AVAILABLE is False and code proceeds
#         raise DXFProcessingError("ezdxf library is not installed or available for DXF processing.")
#     ezdxf_readfile = ezdxf_readfile_stub # Assign stub to the name used by the interface
#     EZDXF_AVAILABLE = False

from ..interfaces.dxf_adapter_interface import IDXFAdapter # ADDED
from ..interfaces.data_source_interface import IDataSource
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import DXFProcessingError, DataSourceError
import geopandas as gpd

# Define Drawing for type hinting if it's still used in the interface for load_dxf_file return type
# If IDXFAdapter.load_dxf_file returns 'Any', this might not be strictly needed here
# but can be kept for clarity in this file if preferred. For now, assuming 'Any' from adapter.
# from ezdxf.document import Drawing # This could be 'Any' depending on adapter's strictness


class DataSourceService(IDataSource):
    """Service for loading data sources, primarily DXF files and managing GeoDataFrames."""

    def __init__(self, logger_service: ILoggingService, dxf_adapter: IDXFAdapter): # ADDED dxf_adapter
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)
        self._dxf_adapter = dxf_adapter # STORED

        # Check DXF availability via adapter on instantiation and log
        if not self._dxf_adapter.is_available():
            self._logger.error(
                "DXF library not available via adapter. DXF loading will fail."
            )
            # Depending on application strictness, could raise an error here
            # or allow attempts to load DXF to fail at runtime per method.

        self._geodataframes: Dict[str, gpd.GeoDataFrame] = {}

    def load_dxf_file(self, file_path: str) -> Optional[Any]: # Return type changed to Optional[Any] to match adapter
        """Load a DXF file and return as DXF document object using the adapter."""
        if not self._dxf_adapter.is_available():
            self._logger.error("DXF library not available via adapter. Cannot load DXF files.")
            raise DXFProcessingError("DXF library not available via adapter. Install ezdxf or check adapter configuration.")

        self._logger.debug(f"Attempting to load DXF file via adapter: {file_path}")

        if not os.path.exists(file_path):
            # This check can remain, or be deferred to the adapter. Keeping it for now.
            raise FileNotFoundError(f"DXF file not found: {file_path}")

        try:
            # Use DXF adapter to load the DXF file
            doc = self._dxf_adapter.load_dxf_file(file_path)
            if doc: # Adapter might return None on some failures even before raising an exception
                self._logger.info(f"Successfully loaded DXF file via adapter: {file_path}")
            else: # If adapter returns None without exception, treat as a processing error
                self._logger.error(f"Adapter returned None for DXF file {file_path} without explicit exception.")
                raise DXFProcessingError(f"Adapter failed to load DXF file {file_path} (returned None).")
            return doc

        except DXFProcessingError as e: # Catching the error type adapter is expected to raise
            # Log message can be more generic now as adapter handles specifics
            self._logger.error(f"Adapter failed to load DXF file {file_path}: {e}", exc_info=True)
            raise # Re-raise the DXFProcessingError

        # Removed specific ezdxf.DXFStructureError and ezdxf.DXFVersionError,
        # as the adapter's load_dxf_file method is expected to encapsulate these
        # and raise a DXFProcessingError.
        # If the adapter is designed to let specific ezdxf errors pass through,
        # those catches would need to be reinstated here. The current plan assumes
        # adapter normalizes to DXFProcessingError.

        except FileNotFoundError: # Should be caught by os.path.exists, but as a safeguard if that's removed.
            self._logger.error(f"DXF file not found (should have been caught earlier): {file_path}", exc_info=True)
            raise

        except Exception as e: # General catch for truly unexpected issues from adapter or this service
            self._logger.error(f"Unexpected error loading DXF file {file_path} via adapter: {e}", exc_info=True)
            # Wrap in DXFProcessingError if it's not already one.
            if not isinstance(e, DXFProcessingError):
                raise DXFProcessingError(f"Unexpected error loading DXF file {file_path} via adapter: {e}") from e
            else:
                raise # Re-raise if it's already the correct type

    def load_geojson_file(self, file_path: str) -> gpd.GeoDataFrame:
        """Load a GeoJSON file and return as GeoDataFrame."""
        self._logger.debug(f"Attempting to load GeoJSON file: {file_path}")  # Changed to DEBUG

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

        try:
            gdf = gpd.read_file(file_path)
            self._logger.info(f"Successfully loaded GeoJSON file: {file_path}. CRS: {gdf.crs}, Features: {len(gdf)}")
            return gdf
        except Exception as e:
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
