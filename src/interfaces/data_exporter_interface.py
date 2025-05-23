"""Interface for data exporting services."""
from typing import Protocol, List, Dict, Optional, Any
import geopandas as gpd

# For DXF export
try:
    from ezdxf.document import Drawing
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None) # Placeholder
    EZDXF_AVAILABLE = False

from ..domain.config_models import SpecificProjectConfig # For context like DXF version
from ..domain.exceptions import ProcessingError, DXFProcessingError


class IDataExporter(Protocol):
    """Interface for services that export geometric data to various formats."""

    def export_to_dxf(
        self,
        drawing: Drawing, # The ezdxf Drawing object to be saved
        output_file_path: str,
        project_config: SpecificProjectConfig # For DXF version and other export settings
    ) -> None:
        """
        Exports an ezdxf Drawing object to a DXF file.

        Args:
            drawing: The ezdxf.document.Drawing object to save.
            output_file_path: The path for the output DXF file.
            project_config: Specific project configuration, mainly for DXF version.

        Raises:
            ProcessingError: If the DXF export fails.
            DXFProcessingError: If ezdxf is not available.
        """
        ...

    def export_to_shapefile(
        self,
        gdf: gpd.GeoDataFrame,
        output_file_path: str, # Path to the .shp file
        # crs: Optional[str] = None, # GDF should already have CRS
        # schema: Optional[Dict[str, str]] = None # Fiona schema, if specific control needed
        **kwargs: Any # To pass driver-specific options to Fiona/GeoPandas
    ) -> None:
        """
        Exports a GeoDataFrame to a Shapefile.

        Args:
            gdf: The GeoDataFrame to export.
            output_file_path: Path to the output .shp file.
            **kwargs: Additional keyword arguments for GeoDataFrame.to_file().

        Raises:
            ProcessingError: If the Shapefile export fails.
        """
        ...

    def export_layers_to_geopackage(
        self,
        layers: Dict[str, gpd.GeoDataFrame],
        output_file_path: str,
        # mode: str = 'w', # Write mode ('w' or 'a') for GeoPackage
        **kwargs: Any
    ) -> None:
        """
        Exports multiple GeoDataFrames to a single GeoPackage file, each as a separate layer.

        Args:
            layers: A dictionary where keys are layer names and values are GeoDataFrames.
            output_file_path: Path to the output .gpkg file.
            **kwargs: Additional keyword arguments for GeoDataFrame.to_file() used per layer.

        Raises:
            ProcessingError: If the GeoPackage export fails.
        """
        ...

    # Potentially other export formats: GeoJSON, CSV (for attribute data), etc.
