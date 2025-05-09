from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union, Literal

from .common import Coordinate, Color, BoundingBox # Assuming common.py is in the same directory

# --- DXF Specific Primitives & Attributes ---

class DxfLayer(BaseModel):
    """Represents a DXF Layer definition."""
    name: str
    color_256: Optional[int] = None  # ACI color index (0-256; 0=ByBlock, 256=ByLayer)
    linetype: Optional[str] = "Continuous"
    # Other layer properties like lineweight, plot style name, transparency can be added
    # plot: bool = True

class DxfEntity(BaseModel):
    """Base model for all DXF graphical entities."""
    # Common properties for most DXF entities
    layer: str = Field(default="0")
    color_256: Optional[int] = None # ACI color index. If None, defaults to ByLayer.
    linetype: Optional[str] = None  # If None, defaults to ByLayer.
    # lineweight: Optional[int] = None # e.g., -1=ByLayer, -2=ByBlock, -3=Default
    # transparency: Optional[int] = None # 0-255
    # handle: Optional[str] = None # Entity handle (usually assigned by DXF library)
    # owner: Optional[str] = None # Handle of the owner (e.g., block definition, paperspace)
    # true_color: Optional[Tuple[int, int, int]] = None # (R, G, B) for true color support

    class Config:
        # Allow extra fields that are not explicitly defined, for passthrough to ezdxf
        # Pydantic v1: extra = "allow"
        # Pydantic v2: model_config = {"extra": "allow"}
        extra = "allow" # For Pydantic v1
        # model_config = {"extra": "allow"} # For Pydantic v2 if used

# --- Specific DXF Entity Types ---

class DxfLine(DxfEntity):
    """Represents a DXF LINE entity."""
    start: Coordinate
    end: Coordinate
    # thickness: Optional[float] = None

class DxfLWPolyline(DxfEntity):
    """Represents a DXF LWPOLYLINE entity (Lightweight Polyline)."""
    points: List[Coordinate] # List of 2D or 3D points (z is often ignored for LWPOLYLINE)
    # For LWPOLYLINE, points are typically (x, y, [start_width, [end_width, [bulge]]])
    # For simplicity, this model stores Coordinates. The writer will need to adapt.
    # Alternatively, define a specific LWPolylineVertex model.
    is_closed: bool = False
    # elevation: Optional[float] = 0.0
    # thickness: Optional[float] = None

class DxfPolyline(DxfEntity): # For old-style heavy POLYLINE (less common for new drawings)
    """Represents a DXF POLYLINE entity (heavy polyline with separate VERTEX entities)."""
    # This is more complex as vertices are separate entities in DXF.
    # For simplicity, we might initially focus on LWPOLYLINE for 2D polylines.
    # If heavy polylines are needed, this model would need a list of DxfVertex models.
    points: List[Coordinate] # Simplified representation
    is_closed: bool = False
    # flags: int = 0 # Polyline flags

class DxfText(DxfEntity):
    """Represents a DXF TEXT entity."""
    insertion_point: Coordinate
    text_content: str
    height: float = Field(..., gt=0) # Text height must be > 0
    rotation: Optional[float] = 0.0 # Angle in degrees
    style: Optional[str] = "Standard" # Text style name
    # width_factor: Optional[float] = 1.0 # This is part of TEXTSTYLE
    # oblique_angle: Optional[float] = 0.0 # This is part of TEXTSTYLE
    # halign: Optional[int] = 0 # Horizontal alignment (0=Left, 1=Center, 2=Right, ...)
    # valign: Optional[int] = 0 # Vertical alignment (0=Baseline, 1=Bottom, 2=Middle, ...)

class DxfMText(DxfEntity):
    """Represents a DXF MTEXT entity."""
    insertion_point: Coordinate
    text_content: str # Can contain MText formatting codes
    char_height: float = Field(..., gt=0, description="Character height for the MTEXT entity.")
    width: Optional[float] = Field(default=None, description="Width of the MText bounding box. None or 0 for no constraint.")
    rotation: Optional[float] = Field(default=0.0, description="Rotation angle in degrees.")
    style: Optional[str] = Field(default="Standard", description="Text style name.")

    # MTEXT specific properties, aligned with TextStylePropertiesConfig where applicable
    attachment_point: Optional[Literal[
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    ]] = Field(default=None, description="MTEXT attachment point.")

    flow_direction: Optional[Literal[
        'LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE'
    ]] = Field(default=None, description="MTEXT flow direction.")

    line_spacing_style: Optional[Literal[
        'AT_LEAST', 'EXACT'
    ]] = Field(default=None, description="MTEXT line spacing style.")
    line_spacing_factor: Optional[float] = Field(default=None, ge=0.25, le=4.0, description="MTEXT line spacing factor.")

    # Background fill properties
    bg_fill_enabled: Optional[bool] = Field(default=None, description="Enable background fill.")
    # bg_fill_color: Optional[ColorModel] = None # Color for background fill, requires ColorModel import
    # bg_fill_scale: Optional[float] = Field(default=None, gt=0.0, description="Scale for background fill if it's a dialog box color.")
    # bg_fill_transparency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Transparency for background fill.")
    # Note: For bg_fill_color to work, ColorModel needs to be imported in this file.
    # For now, keeping it simple. DxfWriter can resolve color from style or direct entity if needed.

class DxfArc(DxfEntity):
    """Represents a DXF ARC entity."""
    center: Coordinate
    radius: float = Field(..., gt=0)
    start_angle: float # In degrees
    end_angle: float   # In degrees
    # thickness: Optional[float] = None

class DxfCircle(DxfEntity):
    """Represents a DXF CIRCLE entity."""
    center: Coordinate
    radius: float = Field(..., gt=0)
    # thickness: Optional[float] = None

class DxfInsert(DxfEntity):
    """Represents a DXF INSERT entity (Block Reference)."""
    block_name: str
    insertion_point: Coordinate
    # x_scale: Optional[float] = 1.0
    # y_scale: Optional[float] = 1.0
    # z_scale: Optional[float] = 1.0
    # rotation: Optional[float] = 0.0
    # attributes: Optional[List[DxfAttribute]] = Field(default_factory=list) # For blocks with attributes

# class DxfAttribute(DxfEntity): # If handling block attributes explicitly
#     """Represents a DXF ATTRIB entity (within a block reference)."""
#     tag: str
#     text_content: str
#     insertion_point: Coordinate # Relative to block insertion point
#     height: float = Field(..., gt=0)
#     # ... other text properties ...

# Union type for any DXF entity model
AnyDxfEntity = Union[
    DxfLine, DxfLWPolyline, DxfPolyline, DxfText, DxfMText,
    DxfArc, DxfCircle, DxfInsert # , DxfAttribute
]

# Optional: Model for a complete DXF drawing structure if needed for internal representation
# class DxfDrawing(BaseModel):
#     layers: List[DxfLayer] = Field(default_factory=list)
#     entities: List[AnyDxfEntity] = Field(default_factory=list)
#     # Header variables, blocks, tables etc. could be added here
