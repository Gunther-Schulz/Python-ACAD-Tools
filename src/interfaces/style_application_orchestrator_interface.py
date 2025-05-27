"""Interface for a service that orchestrates style resolution and application."""
from typing import Protocol, Optional, Any, Dict
import geopandas as gpd
from ezdxf.document import Drawing # For type hinting
from ezdxf.entities import DXFGraphic # For type hinting

from ..domain.style_models import NamedStyle, StyleConfig
from ..domain.geometry_models import GeomLayerDefinition

class IStyleApplicationOrchestrator(Protocol):
    """Orchestrates the resolution of styles and their application to various targets."""

    def get_style_for_layer(
        self,
        layer_name: str,
        layer_definition: Optional[GeomLayerDefinition],
        style_config: StyleConfig
    ) -> Optional[NamedStyle]:
        """Determines the appropriate style for a given layer."""
        ...

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        """Applies styling information to a GeoDataFrame's attributes."""
        ...

    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic,
        style: NamedStyle,
        dxf_drawing: Drawing
    ) -> None:
        """Applies a comprehensive style to a DXF entity."""
        ...

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Drawing,
        layer_name: str,
        style: NamedStyle
    ) -> None:
        """Applies styles to a DXF layer and entities on it."""
        ...

    def clear_caches(self) -> None:
        """Clears any cached data within the orchestrator (e.g., ACI color map)."""
        ...

    def get_cache_info(self) -> Dict[str, Any]: # Changed from int to Any for flexibility
        """Returns information about cached data for monitoring."""
        ...
