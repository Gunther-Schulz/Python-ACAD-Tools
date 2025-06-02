"""Interface for data source loading services, primarily DXF files."""
from typing import Protocol, Optional
import geopandas as gpd # Added for GeoDataFrame type hint

# Direct imports for ezdxf as a hard dependency
from ezdxf.document import Drawing
from ezdxf import readfile as ezdxf_readfile # Use an alias to avoid confusion if we have local readfile

from ..domain.exceptions import DXFProcessingError


class IDataSource(Protocol):
    """Interface for accessing raw data sources, primarily DXF files."""

    def load_dxf_file(self, file_path: str) -> Drawing:
        """
        Loads a DXF file from the given path.

        Args:
            file_path: The path to the DXF file.

        Returns:
            An ezdxf.document.Drawing object.

        Raises:
            DXFProcessingError: If the DXF file cannot be loaded, is not found,
                                or if ezdxf library is unavailable.
            FileNotFoundError: If the file_path does not exist (can be caught by caller).
        """
        ...

    def load_geojson_file(
        self,
        file_path: str,
        crs: Optional[str] = None  # Add crs parameter
    ) -> gpd.GeoDataFrame:
        """
        Loads a GeoJSON file into a GeoDataFrame.

        Args:
            file_path: The path to the GeoJSON file.
            crs: Optional CRS to assign to the GeoDataFrame if not already set or to override.

        Returns:
            A GeoDataFrame with the data from the GeoJSON file.

        Raises:
            DataSourceError: If the GeoJSON file cannot be loaded or is invalid.
            FileNotFoundError: If the file_path does not exist.
        """
        ...

    def load_shapefile(
        self,
        file_path: str,
        crs: Optional[str] = None  # Add crs parameter
    ) -> gpd.GeoDataFrame:
        """
        Loads a Shapefile into a GeoDataFrame.

        Args:
            file_path: The path to the Shapefile (.shp).
            crs: Optional CRS to assign to the GeoDataFrame if not already set or to override.

        Returns:
            A GeoDataFrame with the data from the Shapefile.

        Raises:
            DataSourceError: If the Shapefile cannot be loaded or is invalid.
            FileNotFoundError: If the file_path does not exist.
        """
        ...

    def add_gdf(self, gdf: gpd.GeoDataFrame, layer_name: str) -> None:
        """
        Adds or replaces a GeoDataFrame in an in-memory store.

        Args:
            gdf: The GeoDataFrame to add/replace.
            layer_name: The name to associate with the GeoDataFrame.

        Raises:
            DataSourceError: If gdf is not a GeoDataFrame.
        """
        ...

    def get_gdf(self, layer_name: str) -> gpd.GeoDataFrame:
        """
        Retrieves a GeoDataFrame from an in-memory store by layer name.

        Args:
            layer_name: The name of the GeoDataFrame to retrieve.

        Returns:
            The requested GeoDataFrame.

        Raises:
            DataSourceError: If the layer_name is not found.
        """
        ...

    # Example for a more generic method if other sources were planned:
    # def get_drawing_from_source(self, source_identifier: str, source_type: str = "dxf") -> Drawing:
    #     """
    #     Loads a drawing from a generic source identifier.
    #     Args:
    #         source_identifier: Path to file, URL, database connection string etc.
    #         source_type: Type of the source, e.g., "dxf", "shapefile_zip".
    #     Returns:
    #         An ezdxf.document.Drawing object (or a common drawing representation).
    #     Raises:
    #         DXFProcessingError or other appropriate error if loading fails.
    #     """
    #     ...
