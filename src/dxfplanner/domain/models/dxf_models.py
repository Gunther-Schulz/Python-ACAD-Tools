from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union, Literal, Tuple
from enum import IntEnum

from .common import Coordinate, BoundingBox # Removed Color from here
from dxfplanner.config.common_schemas import ColorModel # Added ColorModel import

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
    # Basic properties common to many DXF entities
    # Making layer Optional as it might be set by writer based on LayerConfig
    layer: Optional[str] = Field(default=None, description="Layer name for the entity.")
    color_256: Optional[int] = Field(default=None, description="ACI color index (0-255). 256 for ByLayer, 0 for ByBlock.") # ACI color
    true_color: Optional[Tuple[int, int, int]] = Field(default=None, description="RGB true color tuple, e.g., (255, 0, 0) for red.")
    linetype: Optional[str] = Field(default=None, description="Linetype name (e.g., 'CONTINUOUS', 'DASHED').")
    lineweight: Optional[int] = Field(default=None, description="Lineweight in 1/100mm (e.g., 25 for 0.25mm). -1=ByLayer, -2=ByBlock, -3=Default.")
    ltscale: Optional[float] = Field(default=None, description="Linetype scale.")
    transparency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Transparency value (0.0=opaque, 1.0=fully transparent).") # Added ge/le constraints
    visible: Optional[bool] = Field(default=None, description="Visibility flag.")
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Original feature attributes, for reference or conditional styling.")

    # XDATA fields
    xdata_app_id: Optional[str] = Field(default=None, description="Application ID for XDATA (e.g., 'DXFPLANNER').")
    xdata_tags: Optional[List[Tuple[int, Any]]] = Field(default=None, description="List of (group_code, value) tuples for XDATA.")

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

class DxfPoint(DxfEntity): # Added DxfPoint
    """Represents a DXF POINT entity."""
    position: Coordinate
    # thickness: Optional[float] = None

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

class DxfPolyline(DxfEntity): # For 3D Polylines or heavy 2D Polylines
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
    height: float = 2.5
    rotation: Optional[float] = 0.0  # Degrees
    style: Optional[str] = Field(default=None, description="Text style name.") # References a DXF TEXTSTYLE
    width_factor: Optional[float] = Field(default=None, gt=0.0, description="Text width factor.") # Added gt constraint
    oblique_angle: Optional[float] = Field(default=None, ge=0.0, lt=360.0, description="Text oblique angle in degrees.") # Added ge/lt constraints
    # TODO: Add halign, valign, etc. from ezdxf.const.TEXT_ALIGN_FLAGS if needed

class DxfMText(DxfEntity):
    """Represents a DXF MTEXT entity."""
    insertion_point: Coordinate
    text_content: str # MText content string, can include formatting codes
    char_height: float = 2.5
    width: Optional[float] = Field(default=None, gt=0.0, description="Width of the MText bounding box. If None, determined by text content.") # Added gt constraint
    rotation: Optional[float] = 0.0  # Degrees
    style: Optional[str] = Field(default=None, description="Text style name.") # References a DXF TEXTSTYLE
    attachment_point: Optional[Literal[
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    ]] = None
    flow_direction: Optional[Literal['LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE']] = None
    line_spacing_style: Optional[Literal['AT_LEAST', 'EXACT']] = None
    line_spacing_factor: Optional[float] = Field(default=None, ge=0.25, le=4.0) # Added ge/le constraints for MTEXT line spacing factor
    bg_fill_enabled: Optional[bool] = None # Enable background fill/mask
    bg_fill_color: Optional[ColorModel] = None # Color for background fill (if not mask)
    width_factor: Optional[float] = Field(default=None, gt=0.0, description="Text width factor (applied by style or MText properties).") # Added gt constraint
    oblique_angle: Optional[float] = Field(default=None, ge=0.0, lt=360.0, description="Text oblique angle in degrees (applied by style or MText properties).") # Added ge/lt constraints

# Placed before DxfHatchPath which might use it implicitly or for clarity
class HatchEdgeType(IntEnum):
    """Defines the type of an edge in a hatch boundary path, mapping to DXF flags."""
    # Values correspond to ezdxf.const or common DXF path type flags
    # e.g., 2 for polyline edges.
    POLYLINE = 2
    # Other types like ARC, ELLIPSE, SPLINE can be added if needed.
    # LINE_EDGE = 2 (often same as polyline for a 2-vertex path)
    # CIRCULAR_ARC_EDGE = 4
    # ELLIPTIC_ARC_EDGE = 8
    # SPLINE_EDGE = 16

class DxfHatchPath(BaseModel):
    """Represents a single boundary path for a HATCH entity."""
    vertices: List[Coordinate] = Field(..., min_items=2, description="List of 2D or 3D points for the path. For polylines, at least 2 points.") # Min 2 for a line segment.
    is_closed: bool = Field(default=True, description="If the polyline path is closed.")
    # ezdxf path_type_flags: 0 = external, 1 = outer, 2 = default (polyline)
    # Common flags: 1 = external polyline, 16 = derived (usually for text boundaries, not general use here)
    # For simple polylines: external=True (bit 0), polyline=True (bit 1) -> (1 | 2) = 3.
    # ezdxf default for add_polyline_path is flags=1 (HATCH_PATH_EXTERNAL | HATCH_PATH_POLYLINE if is_closed else HATCH_PATH_LINE_EDGE)
    # Let's keep it simple: path_type_flags will be mapped by the writer or use ezdxf defaults.
    # For now, no direct path_type_flags field in model, writer will use ezdxf defaults based on is_closed.

class DxfHatch(DxfEntity):
    """Represents a DXF HATCH entity."""
    paths: List[DxfHatchPath] = Field(default_factory=list)

    # Hatch pattern properties
    pattern_name: str = "SOLID"
    pattern_scale: float = Field(default=1.0, gt=0.0)
    pattern_angle: float = Field(default=0.0, ge=0.0, lt=360.0)  # Degrees
    # Hatch style (Normal, Outer, Ignore - from ezdxf.const)
    hatch_style_enum: Literal['NORMAL', 'OUTERMOST', 'IGNORE'] = 'NORMAL'
    # Associativity
    associative: bool = True
    # Color and transparency are inherited from DxfEntity and will be populated there.

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
    block_name: str = Field(..., description="Name of the block definition to insert.")
    insertion_point: Coordinate
    x_scale: float = Field(default=1.0, description="Scale factor for X axis.")
    y_scale: float = Field(default=1.0, description="Scale factor for Y axis.")
    z_scale: float = Field(default=1.0, description="Scale factor for Z axis.")
    rotation: float = Field(default=0.0, description="Rotation angle in degrees.")
    # For MINSERT (Multiple Insert Entity):
    # column_count: int = Field(default=1, ge=1)
    # row_count: int = Field(default=1, ge=1)
    # column_spacing: float = Field(default=0.0)
    # row_spacing: float = Field(default=0.0)
    # attributes: Optional[List[DxfAttribute]] = Field(default_factory=list) # For blocks with attributes

# class DxfAttribute(DxfEntity): # If handling block attributes explicitly

# Union type for any DXF entity model
AnyDxfEntity = Union[
    DxfPoint,
    DxfLine, DxfLWPolyline, DxfPolyline, DxfText, DxfMText,
    DxfHatch,
    DxfArc, DxfCircle, DxfInsert # , DxfAttribute
]

# Optional: Model for a complete DXF drawing structure if needed for internal representation
# class DxfDrawing(BaseModel):
#     layers: List[DxfLayer] = Field(default_factory=list)
#     entities: List[AnyDxfEntity] = Field(default_factory=list)
#     # Header variables, blocks, tables etc. could be added here
