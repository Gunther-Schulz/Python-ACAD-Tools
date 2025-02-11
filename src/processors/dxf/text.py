"""DXF text handling functionality for labeling and text placement."""

from typing import Dict, Any, Optional, Tuple
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from shapely.geometry import Point, LineString, Polygon
import geopandas as gpd
import pandas as pd

from ...utils.logging import log_debug, log_warning

def add_text_to_layout(
    layout: Layout,
    text: str,
    position: Tuple[float, float],
    layer: str,
    height: float = 2.5,
    rotation: float = 0,
    alignment: str = "LEFT",
    style: str = "Standard",
    **style_attrs: Dict[str, Any]
) -> None:
    """Add text to the DXF layout with specified properties.
    
    Args:
        layout: DXF layout to add text to
        text: Text content to add
        position: (x, y) coordinates for text placement
        layer: Layer name for the text
        height: Text height
        rotation: Text rotation angle in degrees
        alignment: Text alignment (LEFT, CENTER, RIGHT)
        style: Text style name
        **style_attrs: Additional style attributes for the text
    """
    dxfattribs = {
        "layer": layer,
        "height": height,
        "rotation": rotation,
        "style": style,
        **style_attrs
    }
    
    # Add text with specified properties
    layout.add_text(
        text=str(text),
        dxfattribs=dxfattribs
    ).set_placement(position, align=alignment)

def add_labels_from_gdf(
    layout: Layout,
    gdf: gpd.GeoDataFrame,
    label_column: str,
    layer: str,
    text_height: float = 2.5,
    text_style: str = "Standard",
    **style_attrs: Dict[str, Any]
) -> None:
    """Add labels to features from a GeoDataFrame.
    
    Args:
        layout: DXF layout to add labels to
        gdf: GeoDataFrame containing features to label
        label_column: Column name containing label text
        layer: Layer name for the labels
        text_height: Height of the label text
        text_style: Text style to use
        **style_attrs: Additional style attributes for the text
    """
    if label_column not in gdf.columns:
        log_warning(f"Label column '{label_column}' not found in GeoDataFrame")
        return
        
    for idx, row in gdf.iterrows():
        if pd.isna(row[label_column]):
            continue
            
        # Get label position based on geometry type
        try:
            position = get_label_position(row.geometry)
            if position:
                add_text_to_layout(
                    layout=layout,
                    text=str(row[label_column]),
                    position=position,
                    layer=layer,
                    height=text_height,
                    style=text_style,
                    **style_attrs
                )
        except Exception as e:
            log_warning(f"Failed to add label for feature {idx}: {str(e)}")

def get_label_position(geom: Any) -> Optional[Tuple[float, float]]:
    """Get the position to place a label for a geometry.
    
    Args:
        geom: Shapely geometry object
        
    Returns:
        Tuple of (x, y) coordinates for label placement, or None if position cannot be determined
    """
    try:
        if isinstance(geom, Point):
            return geom.coords[0]
        elif isinstance(geom, LineString):
            # Place label at midpoint of line
            return geom.interpolate(0.5, normalized=True).coords[0]
        elif isinstance(geom, Polygon):
            # Place label at centroid of polygon
            return geom.centroid.coords[0]
        else:
            log_warning(f"Unsupported geometry type for labeling: {type(geom)}")
            return None
    except Exception as e:
        log_warning(f"Error determining label position: {str(e)}")
        return None 