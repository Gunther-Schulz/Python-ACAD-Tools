from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union, Tuple, Literal
from enum import Enum

# --- Core Configuration Models (referenced by core modules like logging) ---
class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    # Add other loguru specific settings if needed, e.g., rotation, retention

# --- Color Model (used in various style configs) ---
ColorModel = Union[str, int, Tuple[int, int, int]] # ACI index, color name, or (R,G,B) tuple

# --- Style Properties Models ---
class LayerDisplayPropertiesConfig(BaseModel):
    color: ColorModel = "BYLAYER"
    linetype: str = "CONTINUOUS"
    lineweight: int = -1  # -1 for BYLAYER, -2 for BYBLOCK, -3 for DEFAULT
    plot: bool = True
    transparency: float = Field(default=0.0, ge=0.0, le=1.0) # 0.0 Opaque, 1.0 Fully Transparent
    linetype_scale: float = Field(default=1.0, gt=0.0)
    locked: bool = False
    frozen: bool = False
    is_on: bool = True

class TextParagraphPropertiesConfig(BaseModel):
    align: Optional[Literal['LEFT', 'CENTER', 'RIGHT', 'JUSTIFIED', 'DISTRIBUTED']] = None
    indent: Optional[float] = None
    left_margin: Optional[float] = None
    right_margin: Optional[float] = None
    tab_stops: List[float] = Field(default_factory=list)

class TextStylePropertiesConfig(BaseModel):
    font: str = "Standard"  # References a DXF text style name
    height: float = Field(default=2.5, gt=0.0)
    color: ColorModel = "BYLAYER"
    width_factor: Optional[float] = Field(default=None, gt=0.0)
    oblique_angle: Optional[float] = Field(default=None, ge=0.0, lt=360.0) # Degrees
    # MTEXT specific properties
    mtext_width: Optional[float] = Field(default=None, gt=0.0)
    attachment_point: Optional[Literal[
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    ]] = None
    flow_direction: Optional[Literal['LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE']] = None
    line_spacing_style: Optional[Literal['AT_LEAST', 'EXACT']] = None
    line_spacing_factor: Optional[float] = Field(default=None, ge=0.25, le=4.0)
    bg_fill_enabled: Optional[bool] = None
    bg_fill_color: Optional[ColorModel] = None # Can be window background, a specific color, or foreground
    bg_fill_scale: Optional[float] = Field(default=None, gt=0.0)
    underline: Optional[bool] = None
    overline: Optional[bool] = None
    strike_through: Optional[bool] = None
    paragraph_props: Optional[TextParagraphPropertiesConfig] = None
    rotation: Optional[float] = Field(default=None, ge=0.0, lt=360.0) # Degrees

class HatchPropertiesConfig(BaseModel):
    pattern_name: str = "SOLID"
    scale: float = Field(default=1.0, gt=0.0)
    angle: float = Field(default=0.0, ge=0.0, lt=360.0) # Degrees
    color: ColorModel = "BYLAYER"
    transparency: float = Field(default=0.0, ge=0.0, le=1.0)

# --- Main Style Object Model (for presets and inline definitions) ---
class StyleObjectConfig(BaseModel):
    layer_props: Optional[LayerDisplayPropertiesConfig] = None
    text_props: Optional[TextStylePropertiesConfig] = None
    hatch_props: Optional[HatchPropertiesConfig] = None

# --- Data Source Configuration Models ---
class DataSourceType(str, Enum):
    SHAPEFILE = "shapefile"
    GEOJSON = "geojson"
    CSV_WKT = "csv_wkt"
    # WMS = "wms" # To be added
    # WMTS = "wmts" # To be added
    # POSTGIS = "postgis" # To be added

class BaseSourceConfig(BaseModel):
    type: DataSourceType

class ShapefileSourceConfig(BaseSourceConfig):
    type: Literal[DataSourceType.SHAPEFILE] = DataSourceType.SHAPEFILE
    path: str
    encoding: Optional[str] = None
    crs: Optional[str] = None

class GeoJsonSourceConfig(BaseSourceConfig):
    type: Literal[DataSourceType.GEOJSON] = DataSourceType.GEOJSON
    path: str

class CsvWktSourceConfig(BaseSourceConfig):
    type: Literal[DataSourceType.CSV_WKT] = DataSourceType.CSV_WKT
    path: str
    wkt_column: str = "wkt"
    delimiter: str = ","
    crs: Optional[str] = None

AnySourceConfig = Union[
    ShapefileSourceConfig,
    GeoJsonSourceConfig,
    CsvWktSourceConfig
]

# --- Operation Configuration Models ---
class OperationType(str, Enum):
    BUFFER = "buffer"
    INTERSECTION = "intersection"
    MERGE = "merge"
    DISSOLVE = "dissolve"
    FILTER_BY_ATTRIBUTE = "filter_by_attribute"
    SIMPLIFY = "simplify"
    FIELD_MAPPER = "field_mapper"
    REPROJECT = "reproject"
    CLEAN_GEOMETRY = "clean_geometry"
    EXPLODE_MULTIPART = "explode_multipart"
    LABEL_PLACEMENT = "label_placement"
    # ... other operation types to be added

class BaseOperationConfig(BaseModel):
    type: OperationType
    # Common fields for all operations, e.g., output_layer_name if applicable
    # output_layer_name: Optional[str] = None

class BufferOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.BUFFER] = OperationType.BUFFER
    source_layer: Optional[str] = None # Name of the layer to buffer
    distance: float
    output_layer_name: Optional[str] = None # Name of the new layer to create with buffered geometry

    distance_field: Optional[str] = Field(default=None, description="Optional field name in feature attributes for per-feature buffer distance.")
    join_style: Literal['ROUND', 'MITRE', 'BEVEL'] = Field(default='ROUND', description="Style for joining buffer corners.")
    cap_style: Literal['ROUND', 'FLAT', 'SQUARE'] = Field(default='ROUND', description="Style for end caps of linear feature buffers.")
    resolution: int = Field(default=16, ge=1, description="Resolution of the buffer approximation (number of segments per quadrant).")
    mitre_limit: float = Field(default=5.0, gt=0, description="Mitre limit for MITRE join style.")
    # single_sided: bool = Field(default=False, description="If True, creates a single-sided buffer for lines (not yet fully supported by simple buffer).")

    make_valid_pre_buffer: bool = Field(default=True, description="Attempt to make input geometries valid before buffering.")
    make_valid_post_buffer: bool = Field(default=True, description="Attempt to make output geometries valid after buffering.")
    skip_islands: bool = Field(default=False, description="If True, removes all islands/holes from the input geometry before buffering (effectively fills holes).")
    preserve_islands: bool = Field(default=False, description="If True, attempts to preserve islands/holes during buffering (experimental, may not work for all cases).")

    # Optional: dissolve_result: bool = False # This would be a post-processing step, not part of core buffer on individual features

# Placeholder for other operations - to be defined as needed
class IntersectionOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.INTERSECTION] = OperationType.INTERSECTION
    input_layers: List[str] # For intersection, source_layer might be ambiguous, input_layers is better.
    # Let's assume for now that the implicit chaining won't apply directly to Intersection's multi-input.
    # If it were to apply, one of the input_layers would be the default.
    # For now, make output_layer_name optional as per the general requirement.
    output_layer_name: Optional[str] = None

# --- New Operation Config Models ---
class SimplifyOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.SIMPLIFY] = OperationType.SIMPLIFY
    source_layer: Optional[str] = None
    tolerance: float
    output_layer_name: Optional[str] = None
    preserve_topology: bool = True

class FieldMappingOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.FIELD_MAPPER] = OperationType.FIELD_MAPPER
    source_layer: Optional[str] = None
    field_map: Dict[str, str]  # {new_field_name: old_field_name_or_expression}
    output_layer_name: Optional[str] = None
    # Potentially add options for type casting or expression evaluation

class ReprojectOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.REPROJECT] = OperationType.REPROJECT
    source_layer: Optional[str] = None
    target_crs: str
    output_layer_name: Optional[str] = None
    # source_crs can be optional if known from data source

class CleanGeometryOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.CLEAN_GEOMETRY] = OperationType.CLEAN_GEOMETRY
    source_layer: Optional[str] = None
    output_layer_name: Optional[str] = None
    # Options like: fix_invalid_geometries, remove_small_parts_threshold

class ExplodeMultipartOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.EXPLODE_MULTIPART] = OperationType.EXPLODE_MULTIPART
    source_layer: Optional[str] = None
    output_layer_name: Optional[str] = None

# --- Label Placement Specific Configuration ---
class LabelSettings(BaseModel): # This is what was referred to as LabelPlacementConfig in interfaces.py
    """Detailed settings for how labels should be placed."""
    label_attribute: Optional[str] = Field(default=None, description="Attribute field from feature to use for label text.")
    fixed_label_text: Optional[str] = Field(default=None, description="A fixed text string to use for all labels.")
    text_height: float = Field(default=2.5, gt=0, description="Default height for the label text. Can be overridden by style.")
    point_position_override: Optional[str] = Field(default=None, description="Specific placement for point labels (e.g., 'TOP_LEFT', 'CENTER'). Consult placement logic for valid values.")
    offset_x: Union[float, str] = Field(default=0.0, description="Offset in X direction. Can be a number or an expression using feature attributes.")
    offset_y: Union[float, str] = Field(default=0.0, description="Offset in Y direction. Can be a number or an expression using feature attributes.")
    spacing_buffer_factor: float = Field(default=0.2, ge=0.0, description="Factor of text height used as a buffer around labels for collision detection.")
    avoid_colliding_labels: bool = Field(default=True, description="Whether to run collision detection between labels.")
    # avoid_features_from_layers: List[str] = Field(default_factory=list, description="List of layer names whose features should be avoided by labels.")
    # avoid_all_other_features: bool = Field(default=False, description="If true, labels will try to avoid all other geometries in the source_layer not being labeled.")


class LabelPlacementOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.LABEL_PLACEMENT] = OperationType.LABEL_PLACEMENT
    source_layer: Optional[str] = Field(default=None, description="Name of the layer whose features will be labeled.")
    output_label_layer_name: Optional[str] = Field(default=None, description="Optional: Name of the new layer to create for the label MTEXT entities. If None, labels are associated with source_layer styling.")
    label_settings: LabelSettings = Field(default_factory=LabelSettings)
    # Optional: Refer to a TextStylePreset for the labels
    # label_text_style_preset: Optional[str] = None


AnyOperationConfig = Union[
    BufferOperationConfig,
    IntersectionOperationConfig, # Add other specific operation configs here
    SimplifyOperationConfig,
    FieldMappingOperationConfig,
    ReprojectOperationConfig,
    CleanGeometryOperationConfig,
    ExplodeMultipartOperationConfig,
    LabelPlacementOperationConfig
]

# --- Legend Configuration Models ---
class LegendItemStyleConfig(BaseModel):
    """Defines display style for a legend item's representative geometry."""
    item_type: Literal['area', 'line', 'diagonal_line', 'empty'] = 'area'
    # References a StyleObjectConfig preset or can be an inline definition
    style_preset_name: Optional[str] = None
    style_inline: Optional[StyleObjectConfig] = None # Overrides preset if both given for specific properties
    apply_hatch_for_area: bool = True # Only for item_type 'area'
    block_symbol_name: Optional[str] = None # Name of a DXF block to use as a symbol
    block_symbol_scale: float = 1.0

class LegendItemConfig(BaseModel):
    name: str
    subtitle: Optional[str] = None
    item_style: LegendItemStyleConfig # Defines how the geometric swatch for the item looks
    # References TextStylePropertiesConfig presets or can be inline
    text_style_preset_name: Optional[str] = None
    text_style_inline: Optional[TextStylePropertiesConfig] = None
    subtitle_text_style_preset_name: Optional[str] = None
    subtitle_text_style_inline: Optional[TextStylePropertiesConfig] = None


class LegendGroupConfig(BaseModel):
    name: str
    subtitle: Optional[str] = None
    items: List[LegendItemConfig] = Field(default_factory=list)
    # References TextStylePropertiesConfig presets or can be inline
    title_text_style_preset_name: Optional[str] = None
    title_text_style_inline: Optional[TextStylePropertiesConfig] = None
    subtitle_text_style_preset_name: Optional[str] = None
    subtitle_text_style_inline: Optional[TextStylePropertiesConfig] = None

class LegendLayoutConfig(BaseModel):
    position_x: float = 0.0
    position_y: float = 0.0
    group_spacing: float = 20.0
    item_spacing: float = 2.0 # Vertical spacing between item swatch and its text, and between items
    item_swatch_width: float = 30.0
    item_swatch_height: float = 15.0
    text_offset_from_swatch: float = 5.0
    subtitle_spacing_after_title: float = 6.0 # Spacing after a group/legend title to its subtitle
    title_spacing_to_content: float = 8.0 # Spacing after a title (or its subtitle) to the content below
    max_text_width: float = 150.0 # Max width for item names/subtitles

class LegendDefinitionConfig(BaseModel):
    id: str = "default_legend"
    title: Optional[str] = None
    subtitle: Optional[str] = None
    groups: List[LegendGroupConfig] = Field(default_factory=list)
    layout: LegendLayoutConfig = Field(default_factory=LegendLayoutConfig)
    # References TextStylePropertiesConfig presets or can be inline
    overall_title_text_style_preset_name: Optional[str] = None
    overall_title_text_style_inline: Optional[TextStylePropertiesConfig] = None
    overall_subtitle_text_style_preset_name: Optional[str] = None
    overall_subtitle_text_style_inline: Optional[TextStylePropertiesConfig] = None
    background_box_enabled: bool = False
    background_box_style_preset_name: Optional[str] = None # For border style of background box
    background_box_style_inline: Optional[StyleObjectConfig] = None # For border style
    background_box_margin: float = 5.0


# --- Labeling Configuration ---
class LabelingConfig(BaseModel):
    attribute_field: str
    # Option 1: Reference a full TextStylePropertiesConfig preset
    text_style_preset_name: Optional[str] = None
    # Option 2: Define inline text style properties (can override parts of preset or be standalone)
    text_style_inline: Optional[TextStylePropertiesConfig] = None
    # DXFPlanner will need logic to merge preset and inline for final label style

# --- Layer Configuration Model ---
class LayerConfig(BaseModel):
    name: str
    source: Optional[AnySourceConfig] = None # A layer might be purely generated
    operations: List[AnyOperationConfig] = Field(default_factory=list)
    # Style application priority: style_inline_definition > style_preset_name + style_override > style_preset_name
    style_preset_name: Optional[str] = None # References a preset in AppConfig.style_presets
    style_inline_definition: Optional[StyleObjectConfig] = None # A full, self-contained style for this layer
    style_override: Optional[StyleObjectConfig] = None # Partial overrides for the preset
    labeling: Optional[LabelingConfig] = None
    enabled: bool = True # To easily toggle layers on/off

# --- I/O Specific Configuration Models (Existing - to be reviewed/integrated) ---
class ShapefileReaderConfig(BaseModel):
    default_encoding: str = "utf-8"

class GeoJsonReaderConfig(BaseModel):
    pass

class CsvWktReaderConfig(BaseModel):
    wkt_column_existing: str = Field("wkt", alias="wkt_column") # Keep alias for now if old configs use wkt_column
    delimiter: str = ","
    crs_existing: Optional[str] = Field(None, alias="crs")

class DxfWriterConfig(BaseModel):
    target_dxf_version: str = "AC1027"  # AutoCAD 2013-2017 (ezdxf R2013)
    default_layer_for_unmapped: str = Field("0", alias="default_layer") # Keep alias
    default_color_for_unmapped: int = Field(256, alias="default_color")  # 256 = ByLayer
    layer_mapping_by_attribute_value: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    default_text_height_for_unmapped: float = Field(2.5, alias="default_text_height")

    # New fields for enhanced document setup and control
    xdata_application_name: str = "DXFPlanner"
    document_properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Key-value pairs for DXF header variables, e.g., {'AUTHOR': 'My Name'}")
    defined_text_styles: Optional[Dict[str, TextStylePropertiesConfig]] = Field(
        default_factory=dict,
        description="Definitions for text styles to be created in the DXF document."
    )
    default_text_style_name: str = Field(
        default="Standard",
        description="Default text style name to use for text entities if not otherwise specified."
    )
    audit_on_save: bool = Field(
        default=True,
        description="If True, performs an audit of the DXF document before saving."
    )
    # For iterative output
    template_file: Optional[str] = Field(default=None, description="Path to a template DXF file to use if output_filepath does not exist.")
    output_filepath_config: Optional[str] = Field(default=None, description="Path to the target output DXF file, specified in config. Can be overridden by CLI.", alias="output_filepath")

# --- Grouped I/O Configurations (Existing - to be reviewed/integrated) ---
class ReaderConfigs(BaseModel):
    shapefile: ShapefileReaderConfig = Field(default_factory=ShapefileReaderConfig)
    geojson: GeoJsonReaderConfig = Field(default_factory=GeoJsonReaderConfig)
    csv_wkt: CsvWktReaderConfig = Field(default_factory=CsvWktReaderConfig)

class WriterConfigs(BaseModel):
    dxf: DxfWriterConfig = Field(default_factory=DxfWriterConfig)

class IOSettings(BaseModel):
    readers: ReaderConfigs = Field(default_factory=ReaderConfigs)
    writers: WriterConfigs = Field(default_factory=WriterConfigs)
    # Root level output path, an alternative to putting it in DxfWriterConfig if it feels more global
    output_filepath: Optional[str] = Field(default=None, description="Path to the target output DXF file, specified in config. Can be overridden by CLI.")

# --- Service Specific Configuration Models (Existing - mostly fine, may need minor tweaks later) ---
class AttributeMappingServiceConfig(BaseModel):
    attribute_for_layer: Optional[str] = None
    attribute_for_color: Optional[str] = None
    attribute_for_text_content: Optional[str] = None
    attribute_for_text_height: Optional[str] = None
    default_dxf_layer_on_mapping_failure: str = "UNMAPPED_DATA"

class CoordinateServiceConfig(BaseModel):
    default_source_crs: Optional[str] = None
    default_target_crs: Optional[str] = None

class DxfGenerationServiceConfig(BaseModel):
    output_file_precision: int = 6
    create_missing_layers: bool = True

class ValidationServiceConfig(BaseModel):
    check_for_valid_geometries: bool = True
    min_points_for_polyline: int = 2

# --- Grouped Service Configurations (Existing) ---
class ServicesSettings(BaseModel):
    attribute_mapping: AttributeMappingServiceConfig = Field(default_factory=AttributeMappingServiceConfig)
    coordinate: CoordinateServiceConfig = Field(default_factory=CoordinateServiceConfig)
    dxf_generation: DxfGenerationServiceConfig = Field(default_factory=DxfGenerationServiceConfig)
    validation: ValidationServiceConfig = Field(default_factory=ValidationServiceConfig)

# --- Root Application Configuration Model ---
class AppConfig(BaseModel):
    """Root configuration model for the DXFPlanner application."""
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    io: IOSettings = Field(default_factory=IOSettings) # This now contains the output_filepath
    services: ServicesSettings = Field(default_factory=ServicesSettings)

    # New additions for detailed pipeline configuration
    style_presets: Dict[str, StyleObjectConfig] = Field(default_factory=dict)
    layers: List[LayerConfig] = Field(default_factory=list)
    legends: List[LegendDefinitionConfig] = Field(default_factory=list)

    # Global DXF settings that might not fit under DxfWriterConfig specific to output action
    # e.g. global unit settings or drawing limits, if ever needed.
    # For now, most DXF output specifics are in DxfWriterConfig.

    class Config:
        validate_assignment = True
