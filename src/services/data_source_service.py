"""Concrete implementation of the IDataSource interface."""
from typing import Optional, Dict
import os

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
import geopandas as gpd # Added import


class DataSourceService(IDataSource):
    """Service for loading data sources, primarily DXF files and managing GeoDataFrames."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)

        # Check ezdxf availability on instantiation and log
        if not EZDXF_AVAILABLE:
            self._logger.error(
                "ezdxf library is not available. DXF loading will fail. Please install ezdxf."
            )
            # Depending on application strictness, could raise an error here
            # or allow attempts to load DXF to fail at runtime per method.

        self._geodataframes: Dict[str, gpd.GeoDataFrame] = {} # Added GDF store

    def load_dxf_file(self, file_path: str) -> Optional[Drawing]:
        """Load a DXF file and return as ezdxf Drawing."""
        if not EZDXF_AVAILABLE:
            self._logger.error("ezdxf library is not available. Cannot load DXF files.")
            raise DXFProcessingError("ezdxf library is not available. Install ezdxf to load DXF files.")

        self._logger.debug(f"Attempting to load DXF file: {file_path}")  # Changed to DEBUG

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DXF file not found: {file_path}")

        try:
            # Use ezdxf to load the DXF file
            doc = ezdxf.readfile(file_path)
            self._logger.info(f"Successfully loaded DXF file: {file_path}")
            return doc

        except ezdxf.DXFStructureError as e:
            self._logger.error(f"Invalid DXF structure in {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Invalid DXF structure in {file_path}: {e}") from e

        except ezdxf.DXFVersionError as e:
            self._logger.error(f"Unsupported DXF version in {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Unsupported DXF version in {file_path}: {e}") from e

        except Exception as e:
            self._logger.error(f"Failed to load DXF file {file_path}: {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to load DXF file {file_path}: {e}") from e

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
