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
    linetype: str = "BYLAYER"
    lineweight: int = -1  # -1 for BYLAYER, -2 for BYBLOCK, -3 for DEFAULT
    plot: bool = True
    transparency: float = Field(default=0.0, ge=0.0, le=1.0) # 0.0 Opaque, 1.0 Fully Transparent
    linetype_scale: float = Field(default=1.0, gt=0.0)

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
    # ... other operation types to be added

class BaseOperationConfig(BaseModel):
    type: OperationType
    # Common fields for all operations, e.g., output_layer_name if applicable
    # output_layer_name: Optional[str] = None

class BufferOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.BUFFER] = OperationType.BUFFER
    source_layer: str # Name of the layer to buffer
    distance: float
    output_layer_name: str # Name of the new layer to create with buffered geometry
    # Optional: dissolve_result: bool = False
    # Optional: cap_style: Literal['round', 'flat', 'square'] = 'round'
    # Optional: join_style: Literal['round', 'mitre', 'bevel'] = 'round'

# Placeholder for other operations - to be defined as needed
class IntersectionOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.INTERSECTION] = OperationType.INTERSECTION
    input_layers: List[str]
    output_layer_name: str

# --- New Operation Config Models ---
class SimplifyOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.SIMPLIFY] = OperationType.SIMPLIFY
    source_layer: str
    tolerance: float
    output_layer_name: str
    preserve_topology: bool = True

class FieldMappingOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.FIELD_MAPPER] = OperationType.FIELD_MAPPER
    source_layer: str
    field_map: Dict[str, str]  # {new_field_name: old_field_name_or_expression}
    output_layer_name: str
    # Potentially add options for type casting or expression evaluation

class ReprojectOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.REPROJECT] = OperationType.REPROJECT
    source_layer: str
    target_crs: str
    output_layer_name: str
    # source_crs can be optional if known from data source

class CleanGeometryOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.CLEAN_GEOMETRY] = OperationType.CLEAN_GEOMETRY
    source_layer: str
    output_layer_name: str
    # Options like: fix_invalid_geometries, remove_small_parts_threshold

class ExplodeMultipartOperationConfig(BaseOperationConfig):
    type: Literal[OperationType.EXPLODE_MULTIPART] = OperationType.EXPLODE_MULTIPART
    source_layer: str
    output_layer_name: str

AnyOperationConfig = Union[
    BufferOperationConfig,
    IntersectionOperationConfig, # Add other specific operation configs here
    SimplifyOperationConfig,
    FieldMappingOperationConfig,
    ReprojectOperationConfig,
    CleanGeometryOperationConfig,
    ExplodeMultipartOperationConfig
]

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
    io: IOSettings = Field(default_factory=IOSettings)
    services: ServicesSettings = Field(default_factory=ServicesSettings)

    # New additions for detailed pipeline configuration
    style_presets: Dict[str, StyleObjectConfig] = Field(default_factory=dict)
    layers: List[LayerConfig] = Field(default_factory=list)

    # Example for project-specific global settings:
    # project_name: str = "DefaultProject"
    # output_directory: str = "./output_dxf"

    class Config:
        validate_assignment = True
