"""Interface for style application services."""
from typing import Protocol, Optional, Any, Dict
import geopandas as gpd

# Assuming ezdxf types might be relevant if styles are applied back to DXF entities
try:
    from ezdxf.document import Drawing
    from ezdxf.entities import DXFGraphic
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None)
    DXFGraphic = type(None)
    EZDXF_AVAILABLE = False

from ..domain.config_models import StyleConfig, NamedStyle, GeomLayerDefinition
from ..domain.exceptions import ProcessingError, DXFProcessingError


class IStyleApplicator(Protocol):
    """Interface for services that apply styling to geometric data or DXF entities."""

    def get_style_for_layer(
        self,
        layer_name: str,
        layer_definition: Optional[GeomLayerDefinition],
        style_config: StyleConfig
    ) -> Optional[NamedStyle]:
        """
        Retrieves the effective NamedStyle for a given layer based on its definition and global styles.

        Args:
            layer_name: The name of the layer.
            layer_definition: The GeomLayerDefinition, which might contain inline styles or a style name.
            style_config: The global StyleConfig object.

        Returns:
            A NamedStyle object if a style is found/resolved, otherwise None.

        Raises:
            ProcessingError: If there's an issue resolving the style.
        """
        ...

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str # For context, and if GDF needs 'layer' attribute for some renderers
    ) -> gpd.GeoDataFrame:
        """
        Applies styling information to a GeoDataFrame, typically by adding
        attributes that can be interpreted by plotting/rendering libraries (e.g., QGIS, matplotlib).
        This might involve setting 'color', 'linewidth', 'symbol' columns based on the style.
        The exact mechanism depends on the downstream use of the GDF.

        Args:
            gdf: The GeoDataFrame to style.
            style: The NamedStyle object to apply.
            layer_name: The name of the layer being styled.

        Returns:
            The GeoDataFrame with added/modified styling attributes.

        Raises:
            ProcessingError: If styling application fails.
        """
        ...

    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic, # Base class for DXF graphical entities
        style: NamedStyle,
        dxf_drawing: Drawing # For context, e.g., adding linetypes if not present
    ) -> None:
        """
        Applies styling directly to an ezdxf DXFGraphic entity.
        This would set properties like color, linetype, lineweight, text style, hatch properties etc.

        Args:
            entity: The ezdxf entity to style.
            style: The NamedStyle object to apply.
            dxf_drawing: The parent ezdxf Drawing, used for context (e.g., ensuring linetypes exist).

        Raises:
            ProcessingError: If styling application to the DXF entity fails.
            DXFProcessingError: If ezdxf is not available and this method is called.
        """
        ...

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Any,  # Drawing from ezdxf
        layer_name: str,
        style: NamedStyle
    ) -> None:
        """
        Applies style properties to the specified DXF layer.
        Creates or updates the layer with color, linetype, lineweight, etc.

        Args:
            dxf_drawing: The ezdxf Drawing object.
            layer_name: Name of the DXF layer.
            style: Style configuration with layer properties.

        Raises:
            DXFProcessingError: If style application fails due to DXF-related issues.
        """
        ...

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Any,  # Drawing from ezdxf
        gdf: "gpd.GeoDataFrame",
        layer_name: str,
        style: Optional[NamedStyle] = None
    ) -> None:
        """
        Adds geometries from a GeoDataFrame to a DXF drawing.

        Args:
            dxf_drawing: The ezdxf Drawing object.
            gdf: GeoDataFrame containing geometries to add.
            layer_name: Name of the DXF layer to add geometries to.
            style: Optional style to apply to the geometries.

        Raises:
            DXFProcessingError: If geometry addition fails.
        """
        ...

    # Potentially a method to create/ensure DXF resources like text styles or linetypes
    # def ensure_dxf_resources(self, dxf_drawing: Drawing, style_config: StyleConfig) -> None:
    #     ...
