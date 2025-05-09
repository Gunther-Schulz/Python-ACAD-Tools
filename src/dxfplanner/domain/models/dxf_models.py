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
    paths: List[DxfHatchPath] = Field(..., min_items=1, description="List of boundary paths for the hatch.")

    hatch_style_enum: Literal['NORMAL', 'OUTERMOST', 'IGNORE'] = Field(
        default='NORMAL',
        description="Hatch style: NORMAL, OUTERMOST (fills outermost boundary only), IGNORE (fills all areas within boundary, ignoring islands)."
    )

    pattern_name: str = Field(default="SOLID", description="Name of the hatch pattern (e.g., SOLID, ANSI31).")
    pattern_scale: float = Field(default=1.0, gt=0, description="Scale of the hatch pattern.")
    pattern_angle: float = Field(default=0.0, description="Angle of the hatch pattern in degrees.")

    # Associativity for hatches is often complex and might depend on how boundaries are defined/if they are proxy graphics.
    # For new hatches with explicit boundaries, False is safer if boundaries might change independently.
    associative: bool = Field(default=False, description="If the hatch is associative with its boundaries.")

    # Transparency can be None (ByLayer/ByBlock), or a float 0.0 (opaque) to 1.0 (fully transparent).
    transparency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Hatch transparency (0.0=opaque, 1.0=fully transparent).")

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
    DxfLine, DxfLWPolyline, DxfPolyline, DxfText, DxfMText,
    DxfHatch,
    DxfArc, DxfCircle, DxfInsert # , DxfAttribute
]

# Optional: Model for a complete DXF drawing structure if needed for internal representation
# class DxfDrawing(BaseModel):
#     layers: List[DxfLayer] = Field(default_factory=list)
#     entities: List[AnyDxfEntity] = Field(default_factory=list)
#     # Header variables, blocks, tables etc. could be added here
