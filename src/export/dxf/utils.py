"""
DXF utilities for PyCAD.
Helper functions for DXF operations.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import ezdxf
from ezdxf.lldxf.const import LWPOLYLINE_PLINEGEN
from ezdxf import pattern
from ezdxf import const
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point
from ...utils.logging import log_debug, log_error, log_warning
from ...utils.path import ensure_path_exists, resolve_path
from ...core.exceptions import ExportError

# Constants
SCRIPT_IDENTIFIER = "PyCAD"

# Invalid characters for layer names
invalid_chars = r'<>/\:"|?*'

def get_color_code(color_name: str) -> int:
    """Get AutoCAD color code from color name.

    Args:
        color_name: Name of the color

    Returns:
        AutoCAD color code
    """
    color_map = {
        'red': 1,
        'yellow': 2,
        'green': 3,
        'cyan': 4,
        'blue': 5,
        'magenta': 6,
        'white': 7,
        'gray': 8,
        'light_red': 9,
        'light_green': 10,
        'light_blue': 11,
        'light_cyan': 12,
        'light_magenta': 13,
        'light_yellow': 14,
        'light_white': 15
    }
    return color_map.get(color_name.lower(), 7)  # Default to white

def attach_custom_data(entity: ezdxf.dxfentity.DXFEntity, entity_name: Optional[str] = None) -> None:
    """Attach custom data to a DXF entity.

    Args:
        entity: DXF entity to attach data to
        entity_name: Optional name for the entity
    """
    if entity_name:
        entity.dxf.name = entity_name
    entity.dxf.owner = SCRIPT_IDENTIFIER

def is_created_by_script(entity: ezdxf.dxfentity.DXFEntity) -> bool:
    """Check if an entity was created by our script.

    Args:
        entity: DXF entity to check

    Returns:
        bool: True if created by script
    """
    return getattr(entity.dxf, 'owner', None) == SCRIPT_IDENTIFIER

def add_text(msp: ezdxf.modelspace.ModelSpace, text: str, point: tuple,
            layer: str, height: float = 2.5, style: str = 'Standard') -> None:
    """Add text to the modelspace.

    Args:
        msp: Modelspace to add text to
        text: Text content
        point: Insertion point (x, y)
        layer: Layer name
        height: Text height
        style: Text style
    """
    msp.add_text(text, dxfattribs={
        'layer': layer,
        'height': height,
        'style': style,
        'insert': point
    })

def remove_entities_by_layer(msp: ezdxf.modelspace.ModelSpace,
                           layers: List[str], script_id: str) -> None:
    """Remove entities from specified layers that were created by our script.

    Args:
        msp: Modelspace to clean
        layers: List of layer names
        script_id: Script identifier
    """
    for layer in layers:
        for entity in msp.query(f'*[layer=="{layer}"]'):
            if getattr(entity.dxf, 'owner', None) == script_id:
                msp.delete_entity(entity)

def ensure_layer_exists(doc: ezdxf.document.Drawing, layer_name: str) -> ezdxf.lldxf.lldxf.Layer:
    """Ensure a layer exists in the document.

    Args:
        doc: DXF document
        layer_name: Name of the layer

    Returns:
        Layer object
    """
    if layer_name not in doc.layers:
        doc.layers.add(name=layer_name)
    return doc.layers.get(layer_name)

def update_layer_properties(layer: ezdxf.lldxf.lldxf.Layer,
                          properties: Dict[str, Any]) -> None:
    """Update layer properties.

    Args:
        layer: Layer to update
        properties: Properties to apply
    """
    if 'color' in properties:
        layer.color = get_color_code(properties['color'])
    if 'linetype' in properties:
        layer.linetype = properties['linetype']
    if 'lineweight' in properties:
        layer.lineweight = properties['lineweight']
    if 'plot' in properties:
        layer.plot = properties['plot']
    if 'locked' in properties:
        layer.lock = properties['locked']
    if 'frozen' in properties:
        layer.freeze = properties['frozen']
    if 'is_on' in properties:
        layer.is_on = properties['is_on']
    if 'transparency' in properties:
        layer.transparency = properties['transparency']

def set_drawing_properties(doc: ezdxf.document.Drawing) -> None:
    """Set drawing properties.

    Args:
        doc: DXF document to configure
    """
    # Set drawing units
    doc.units = ezdxf.units.MM

    # Set paper space units
    doc.paperspace.units = ezdxf.units.MM

    # Set model space units
    doc.modelspace.units = ezdxf.units.MM

def verify_dxf_settings(file_path: str) -> bool:
    """Verify DXF file settings.

    Args:
        file_path: Path to DXF file

    Returns:
        bool: True if settings are valid
    """
    try:
        doc = ezdxf.readfile(file_path)
        if doc.units != ezdxf.units.MM:
            log_warning(f"DXF file {file_path} does not use millimeter units")
            return False
        return True
    except Exception as e:
        log_error(f"Error verifying DXF settings: {str(e)}")
        return False

def sanitize_layer_name(name: str) -> str:
    """Sanitize layer name for DXF compatibility.

    Args:
        name: Original layer name

    Returns:
        Sanitized layer name
    """
    # Replace invalid characters
    for char in invalid_chars:
        name = name.replace(char, '_')

    # Limit length
    if len(name) > 31:
        name = name[:31]

    return name

def add_mtext(msp: ezdxf.modelspace.ModelSpace, text: str, point: tuple,
              layer: str, height: float = 2.5, width: float = 100) -> None:
    """Add multiline text to the modelspace.

    Args:
        msp: Modelspace to add text to
        text: Text content
        point: Insertion point (x, y)
        layer: Layer name
        height: Text height
        width: Text width
    """
    msp.add_mtext(text, dxfattribs={
        'layer': layer,
        'char_height': height,
        'width': width,
        'insert': point
    })
