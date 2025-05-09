from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

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
    # rotation: Optional[float] = 0.0 # Angle in degrees
    # style: Optional[str] = "Standard" # Text style name
    # width_factor: Optional[float] = 1.0
    # oblique_angle: Optional[float] = 0.0
    # halign: Optional[int] = 0 # Horizontal alignment (0=Left, 1=Center, 2=Right, ...)
    # valign: Optional[int] = 0 # Vertical alignment (0=Baseline, 1=Bottom, 2=Middle, ...)

class DxfMText(DxfEntity):
    """Represents a DXF MTEXT entity."""
    insertion_point: Coordinate
    text_content: str # Can contain MText formatting codes
    char_height: float = Field(..., gt=0)
    # width: Optional[float] = 0.0 # Width of the MText bounding box (0 for no constraint)
    # rotation: Optional[float] = 0.0
    # style: Optional[str] = "Standard"
    # attachment_point: Optional[int] = 1 # 1=TopLeft, 2=TopCenter, ..., 9=BottomRight

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
