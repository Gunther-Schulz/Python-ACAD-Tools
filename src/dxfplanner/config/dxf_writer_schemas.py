from typing import Optional, List, Union, Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field, validator
from enum import Enum
from .common_schemas import ColorModel, FontProperties # Import from new common_schemas

# --- Linetype and Text Style Config for DxfWriterConfig (specific definitions) ---
class LinetypeConfig(BaseModel):
    name: str
    description: Optional[str] = None
    pattern: List[float] # e.g., [0.5, -0.25, 0, -0.25] for dash-dot

class TextStyleConfig(BaseModel): # For DxfWriterConfig.text_styles for creating STYLE entities
    name: str
    font_file: str # e.g., "arial.ttf", "isocp.shx"
    height: Optional[float] = Field(default=0.0, description="Fixed height for the style. 0.0 for variable height (recommended).")
    width_factor: Optional[float] = Field(default=1.0, description="Width factor.")
    oblique_angle: Optional[float] = Field(default=0.0, description="Oblique angle in degrees.")
    # Other text style attributes can be added here if needed (e.g., backwards, upside_down)

# --- Block Definition Schemas ---
class BlockEntityAttribsConfig(BaseModel):
    """Common styling attributes for entities within a block definition."""
    layer: str = Field(default="0", description="Layer for the entity within the block.")
    color: Optional[ColorModel] = Field(default=None, description="Color of the entity. None means BYBLOCK for ACI, or actual color for RGB.")
    linetype: Optional[str] = Field(default=None, description="Linetype of the entity. None means BYBLOCK.")
    lineweight: Optional[int] = Field(default=None, description="Lineweight of the entity. None means BYBLOCK.")
    # transparency: Optional[float] = Field(default=None, description="Transparency. None means BYLAYER/BYBLOCK.") # TODO: Add if needed

class BlockPointConfig(BlockEntityAttribsConfig):
    type: Literal["POINT"] = "POINT"
    location: Tuple[float, float, float] = Field(description="Location (x, y, z) of the point.")

class BlockLineConfig(BlockEntityAttribsConfig):
    type: Literal["LINE"] = "LINE"
    start_point: Tuple[float, float, float] = Field(description="Start point (x, y, z) of the line.")
    end_point: Tuple[float, float, float] = Field(description="End point (x, y, z) of the line.")

class BlockPolylineConfig(BlockEntityAttribsConfig):
    type: Literal["POLYLINE", "LWPOLYLINE"] = "POLYLINE" # Allow LWPOLYLINE too
    vertices: List[Tuple[float, float, Optional[float]]] = Field(description="List of vertices (x, y, [z optional]) for the polyline. Z is 0 if omitted for LWPOLYLINE.")
    is_closed: bool = Field(default=False, description="Whether the polyline is closed.")
    # elevation: Optional[float] = Field(default=0.0, description="Elevation for LWPOLYLINE if vertices are 2D.") # Implicit from Z or default 0

class BlockCircleConfig(BlockEntityAttribsConfig):
    type: Literal["CIRCLE"] = "CIRCLE"
    center: Tuple[float, float, float] = Field(description="Center point (x, y, z) of the circle.")
    radius: float = Field(description="Radius of the circle.")

class BlockArcConfig(BlockEntityAttribsConfig):
    type: Literal["ARC"] = "ARC"
    center: Tuple[float, float, float] = Field(description="Center point (x, y, z) of the arc.")
    radius: float = Field(description="Radius of the arc.")
    start_angle: float = Field(description="Start angle in degrees.")
    end_angle: float = Field(description="End angle in degrees.")

class BlockTextConfig(BlockEntityAttribsConfig):
    type: Literal["TEXT", "MTEXT"] = "TEXT" # Allow MTEXT too
    insertion_point: Tuple[float, float, float] = Field(description="Insertion point (x, y, z).")
    text_string: str = Field(description="The text content.")
    height: Optional[float] = Field(default=None, description="Text height. If None, uses style height or default.")
    rotation: Optional[float] = Field(default=0.0, description="Text rotation angle in degrees.")
    style: Optional[str] = Field(default=None, description="Text style name. If None, uses current style (e.g., STANDARD).")
    # For MTEXT:
    width: Optional[float] = Field(default=None, description="MTEXT bounding box width (optional).")
    attachment_point: Optional[int] = Field(default=None, description="MTEXT attachment point (1-9).") # 1=TL, 2=TC, 3=TR, 4=ML, ..., 7=BL

# TODO: Add HATCH, SOLID, etc. entity types for blocks if needed.

AnyBlockEntityConfig = Union[
    BlockPointConfig,
    BlockLineConfig,
    BlockPolylineConfig,
    BlockCircleConfig,
    BlockArcConfig,
    BlockTextConfig,
]

class BlockDefinitionConfig(BaseModel):
    """Configuration for a single block definition."""
    name: str = Field(description="Name of the block.")
    base_point: Tuple[float, float, float] = Field(default=(0.0, 0.0, 0.0), description="Base point (x, y, z) for the block definition.")
    entities: List[AnyBlockEntityConfig] = Field(description="List of entities that make up the block.")
    # dxf_attribs: Optional[Dict[str, Any]] = Field(default=None, description="Additional DXF attributes for the BLOCK record.") # e.g. flags

# --- Viewport Detail Configuration (New) ---
class ViewportDetailConfig(BaseModel):
    """Detailed configuration for a paperspace viewport."""
    create_viewport: bool = Field(default=True, description="Whether to create/configure this detailed viewport setup in paperspace.")
    bbox_padding_factor: float = Field(default=0.1, description="Padding factor for calculating initial view extents from entities bbox for $VIEWCTR, $VIEWSIZE.")

    # Paperspace viewport entity properties
    center_x_ps_paper: float = Field(default=105.0, description="X coordinate of the viewport entity center in paper units (e.g., half of A4 width 210mm).")
    center_y_ps_paper: float = Field(default=148.5, description="Y coordinate of the viewport entity center in paper units (e.g., half of A4 height 297mm).")
    width_ps_paper: float = Field(default=190.0, description="Width of the viewport entity in paper units.")
    height_ps_paper: float = Field(default=277.0, description="Height of the viewport entity in paper units.")

    # Modelspace view definition for the viewport
    view_target_ms_x: Optional[float] = Field(default=None, description="Modelspace X coordinate for the viewport to center on. None to use drawing extents center ($VIEWCTR).")
    view_target_ms_y: Optional[float] = Field(default=None, description="Modelspace Y coordinate for the viewport to center on. None to use drawing extents center ($VIEWCTR).")
    view_height_ms: Optional[float] = Field(default=None, description="Height of the modelspace area to be visible in the viewport. None to use drawing extents size ($VIEWSIZE).")
    # paperspace_viewport_scale is handled by how view_height_ms is calculated or set.

    lock_viewport: bool = Field(default=False, description="Whether to lock the viewport after creation.")


# --- DXF Header Variables Configuration (New) ---
class InsUnitsEnum(int, Enum):
    """DXF $INSUNITS values for drawing units."""
    UNITLESS = 0
    INCHES = 1
    FEET = 2
    MILES = 3
    MILLIMETERS = 4
    CENTIMETERS = 5
    METERS = 6
    KILOMETERS = 7
    MICROINCHES = 8
    MILS = 9
    YARDS = 10
    ANGSTROMS = 11
    NANOMETERS = 12
    MICRONS = 13
    DECIMETERS = 14
    DEKAMETERS = 15
    HECTOMETERS = 16
    GIGAMETERS = 17
    ASTRONOMICAL_UNITS = 18
    LIGHT_YEARS = 19
    PARSECS = 20
    US_SURVEY_FEET = 21 # Added based on common usage
    US_SURVEY_INCH = 22
    US_SURVEY_YARD = 23
    US_SURVEY_MILE = 24


class HeaderVariablesConfig(BaseModel):
    """Structured configuration for common DXF header variables."""
    insunits: Optional[InsUnitsEnum] = Field(
        default=InsUnitsEnum.METERS,
        description="Units for inserted blocks (DXF $INSUNITS). Default: 6 (Meters)."
    )
    lunits: Optional[int] = Field(
        default=2,
        description="Linear unit format (DXF $LUNITS). 1=Scientific, 2=Decimal, 3=Engineering, 4=Architectural, 5=Fractional. Default: 2 (Decimal)."
    )
    luprec: Optional[int] = Field(
        default=4,
        description="Linear unit precision (DXF $LUPREC - number of decimal places or denominator). Default: 4."
    )
    measurement: Optional[int] = Field(
        default=1,
        description="Controls drawing units system (DXF $MEASUREMENT). 0=English (imperial), 1=Metric. Default: 1 (Metric)."
    )
    lwdisplay: Optional[bool] = Field( # Changed to bool for clarity, will convert to 1/0 in service
        default=True,
        description="Display lineweights in model space (DXF $LWDISPLAY). Default: True (1)."
    )
    # For other less common or user-defined header variables
    additional_vars: Dict[str, Any] = Field(
        default_factory=dict,
        description="Allows setting any other DXF header variables by their name (e.g., {'$USERI1': 10}). Prefix with '$' as per DXF standard."
    )

    class Config:
        use_enum_values = True # Ensures enum values are used when exporting


# --- Main DxfWriter Configuration ---
class DxfLayerConfig(BaseModel):
    """Configuration for a DXF layer's properties (for the LAYER table)."""
    name: str
    color: Optional[ColorModel] = Field(default=None, description="Layer color. If None, default color (often white/black).")
    linetype: Optional[str] = Field(default="Continuous", description="Linetype name for the layer.")
    lineweight: Optional[int] = Field(default=-3, description="Lineweight for the layer (-3 = Default, -2 = ByBlock, -1 = ByLayer).") # Standard values
    plot_style_name: Optional[str] = Field(default="Color_7", description="Plot style name (for CTB).")
    is_frozen: bool = Field(default=False)
    is_off: bool = Field(default=False)
    is_locked: bool = Field(default=False)
    plot_flag: bool = Field(default=True, description="Whether the layer is plottable.")
    description: Optional[str] = Field(default=None, description="Optional description for the layer.")
    # transparency: Optional[float] = Field(default=None) # Layer transparency

class DxfWriterConfig(BaseModel):
    """Main configuration for the DXF writer."""
    output_filepath: str = Field(description="Path to the output DXF file.")
    template_file: Optional[str] = Field(default=None, description="Path to a DXF template file to use as a base.")
    output_crs: Optional[str] = Field(default=None, description="Target CRS for the output DXF. If None, assumes geometries are already in desired output space or uses project CRS.")
    aci_colors_map_path: Optional[str] = Field(default=None, description="Path to YAML/JSON file mapping ACI index to RGB for custom color lookups or specific ACI interpretations.")

    layer_configs: Optional[List[DxfLayerConfig]] = Field(default=None, description="List of explicit layer definitions for the DXF.")
    default_layer_properties: Optional[DxfLayerConfig] = Field(default=None, description="Default properties for layers not explicitly defined.")

    text_styles: Optional[List[TextStyleConfig]] = Field(default=None, description="List of text styles to define in the DXF.")
    linetypes: Optional[List[LinetypeConfig]] = Field(default=None, description="List of linetypes to define in theDXF.")

    block_definitions: Optional[List[BlockDefinitionConfig]] = Field(default=None, description="List of block definitions to create in the DXF.")

    # Viewport and layout settings
    # General toggles and names
    create_modelspace_viewport: bool = Field(default=True, description="Whether to create a default viewport in modelspace (VPORT *Active).") # This likely sets $CVPORT
    create_paperspace_layout: bool = Field(default=True, description="Whether to create a default paperspace layout with a viewport entity.")
    paperspace_layout_name: str = Field(default="Layout1", description="Name for the default paperspace layout.")
    paperspace_viewport_scale: Optional[float] = Field(default=None, description="Scale for the viewport in paperspace (e.g., 1/50 = 0.02). If None, fits to extents using $VIEWSIZE. This influences view_height_ms if not set directly in ViewportDetailConfig.")

    viewport_settings: Optional[ViewportDetailConfig] = Field(default=None, description="Detailed viewport settings for the paperspace viewport entity. Used if create_paperspace_layout is True.")

    # Other global settings
    dxf_version: Optional[str] = Field(default="AC1027", description="DXF version (e.g., AC1027 for R2013, AC1032 for R2018).")
    header_variables: Optional[HeaderVariablesConfig] = Field(default=None, description="Structured DXF header variable settings.")

    xdata_application_name: str = Field(default="DXFPLANNER", description="Application name for XDATA used by the writer.")
    audit_on_save: bool = Field(default=False, description="Run DXF audit before saving.")
    template_clear_modelspace: bool = Field(default=True, description="Clear modelspace entities if loading from template.") # Added from observed behavior

    target_dxf_version: Optional[str] = Field(default="AC1032", description="Target DXF version for ezdxf.new() if no template. e.g. AC1032 for R2018") # Added from observed behavior

    # Consider a section for default entity properties if not styled by layer_props or StyleService
    # default_entity_color: Optional[ColorModel] = None
    # default_entity_linetype: Optional[str] = None
