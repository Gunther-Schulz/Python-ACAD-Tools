"""Pydantic models for application configuration structures."""
from typing import Optional, List, Dict, Union, Any, Tuple, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator, root_validator
from pydantic_settings import BaseSettings
from .common_types import CoordsXY # Assuming CoordsXY might be used, e.g. for text positions if not in style

# Style System Models (based on styles.yaml and StyleManager analysis)

class LayerStyleProperties(BaseModel):
    """Properties for styling a DXF layer."""
    model_config = ConfigDict(extra='ignore') # Allow extra fields from YAML but don't store

    color: Optional[Union[str, int]] = None # ACI code (int) or color name (str)
    linetype: Optional[str] = None
    lineweight: Optional[int] = None # Standard lineweights (e.g., 13, 20, 50)
    plot: Optional[bool] = None
    locked: Optional[bool] = None
    frozen: Optional[bool] = None
    is_on: Optional[bool] = Field(default=True, alias='on') # YAML might use 'on'
    transparency: Optional[float] = None # 0.0 (opaque) to 1.0 (fully transparent)
    linetype_scale: Optional[float] = Field(default=1.0, alias='linetypeScale')

    @field_validator('transparency')
    @classmethod
    def validate_transparency(cls, v):
        if v is not None:
            if not (0.0 <= v <= 1.0):
                raise ValueError('Transparency must be between 0.0 and 1.0')
        return v

class TextStyleParagraphProperties(BaseModel):
    """Properties for MTEXT paragraph formatting."""
    model_config = ConfigDict(extra='ignore')

    align: Optional[str] = None # LEFT, RIGHT, CENTER, JUSTIFIED, DISTRIBUTED
    indent: Optional[float] = None
    left_margin: Optional[float] = Field(default=0.0, alias='leftMargin')
    right_margin: Optional[float] = Field(default=0.0, alias='rightMargin')
    # tab_stops: Optional[List[float]] = Field(default_factory=list, alias='tabStops') # Example if needed

class TextStyleProperties(BaseModel):
    """Properties for styling text entities."""
    model_config = ConfigDict(extra='ignore')

    height: Optional[float] = None
    font: Optional[str] = None
    color: Optional[Union[str, int]] = None # ACI code or color name
    max_width: Optional[float] = Field(default=0.0, alias='maxWidth') # 0.0 means no wrapping
    attachment_point: Optional[str] = Field(None, alias='attachmentPoint') # e.g., TOP_LEFT, MIDDLE_CENTER. Added default None.

    # MTEXT specific properties (optional group)
    flow_direction: Optional[str] = Field(None, alias='flowDirection') # e.g., LEFT_TO_RIGHT. Added default None.
    line_spacing_style: Optional[str] = Field(None, alias='lineSpacingStyle') # e.g., AT_LEAST, EXACT. Added default None.
    line_spacing_factor: Optional[float] = Field(None, alias='lineSpacingFactor') # Added default None.

    bg_fill: Optional[bool] = Field(default=False, alias='bgFill')
    bg_fill_color: Optional[Union[str, int]] = Field(None, alias='bgFillColor') # Added default None.
    bg_fill_scale: Optional[float] = Field(None, alias='bgFillScale') # Added default None.

    underline: Optional[bool] = None
    overline: Optional[bool] = None
    strike_through: Optional[bool] = Field(None, alias='strikeThrough') # Added default None.
    oblique_angle: Optional[float] = Field(None, alias='obliqueAngle') # degrees. Added default None.
    rotation: Optional[float] = None # degrees

    paragraph: Optional[TextStyleParagraphProperties] = None

    # New fields for align_to_view functionality
    align_to_view: Optional[Union[bool, str]] = Field(default=None, alias="alignToView")
    align_attachment_point: bool = Field(default=True, alias="alignAttachmentPoint")

class HatchStyleProperties(BaseModel):
    """Properties for styling hatch entities."""
    model_config = ConfigDict(extra='ignore')

    pattern: Optional[str] = Field(default='SOLID')
    scale: Optional[float] = Field(default=1.0)
    color: Optional[Union[str, int]] = None # ACI code or color name
    transparency: Optional[float] = None # 0.0 to 1.0
    individual_hatches: Optional[bool] = Field(default=True) # From analysis of styles.yaml
    # 'layers' and 'lineweight' were seen in StyleManager _validate_hatch_style,
    # but their context for a style definition itself (vs. a layer config) is unclear.
    # Holding off unless they are clearly part of a named style definition.

    @field_validator('transparency')
    @classmethod
    def validate_transparency(cls, v):
        if v is not None:
            if not (0.0 <= v <= 1.0):
                raise ValueError('Transparency must be between 0.0 and 1.0')
        return v

class NamedStyle(BaseModel):
    """A named style that can contain layer, text, and hatch properties."""
    model_config = ConfigDict(extra='ignore')

    layer: Optional[LayerStyleProperties] = None
    text: Optional[TextStyleProperties] = None
    hatch: Optional[HatchStyleProperties] = None

class StyleConfig(BaseModel):
    """Root model for styles.yaml content."""
    model_config = ConfigDict(extra='ignore')
    styles: Dict[str, NamedStyle] = Field(default_factory=dict)

# Color Mapping Models (based on aci_colors.yaml)
class AciColorMappingItem(BaseModel):
    model_config = ConfigDict(extra='forbid') # Stricter for well-defined data

    name: str
    aciCode: int # YAML uses aciCode
    rgb: Optional[Tuple[int, int, int]] = None # e.g., [255, 0, 0]

class ColorConfig(BaseModel): # This model might represent the direct list content of aci_colors.yaml
    model_config = ConfigDict(extra='ignore')
    colors: List[AciColorMappingItem]
    # If aci_colors.yaml is `key: [colorslist]`, then the field would be `key: List[AciColorMappingItem]`
    # ProjectLoader implies aci_colors.yaml is a list of dicts:
    # self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
    # So, it's likely the YAML is just a list. Pydantic can parse List[Model] directly.
    # If the root of the YAML is the list itself, the config loader service would pass this list to a simple List[AciColorMappingItem] type hint.
    # For now, defining a wrapper `ColorConfig` with a `colors` field is a safe bet if it's loaded into an AppConfig structure.
    # Or, more simply, the AppConfig could have: aci_color_mappings: List[AciColorMappingItem]

# Project Settings Models (based on ProjectLoader and modular YAMLs)

class ProjectMainSettings(BaseModel):
    """Core project settings, typically from project.yaml."""
    model_config = ConfigDict(extra='ignore')

    crs: str
    dxf_filename: str = Field(alias='dxfFilename')
    template: Optional[str] = None
    export_format: str = Field(default='dxf', alias='exportFormat') # Can be 'dxf', 'shp', 'gpkg', 'all'
    dxf_version: str = Field(default='R2010', alias='dxfVersion')
    shapefile_output_dir: Optional[str] = Field(None, alias='shapefileOutputDir')
    output_dxf_path: Optional[str] = Field(None, alias='outputDxfPath') # Full path for output DXF
    output_geopackage_path: Optional[str] = Field(None, alias='outputGeopackagePath') # Full path for output GPKG
    # Any other top-level settings from project.yaml can be added here

class BaseOperationParams(BaseModel):
    """Base model for operation parameters. Each operation type will have its own model."""
    model_config = ConfigDict(extra='forbid') # Stricter for operation params
    type: str # To discriminate operation type, e.g., "buffer", "difference"

class BufferOpParams(BaseOperationParams):
    type: str = "buffer" # Literal type for discrimination
    distance: Optional[float] = 0.0
    distance_field: Optional[str] = Field(None, alias='distanceField')
    mode: Optional[str] = Field(default='normal') # normal, ring
    join_style: Optional[str] = Field(default='mitre', alias='joinStyle') # round, mitre, bevel
    cap_style: Optional[str] = Field(default='square', alias='capStyle') # round, flat, square
    start_cap_style: Optional[str] = Field(None, alias='startCapStyle')
    end_cap_style: Optional[str] = Field(None, alias='endCapStyle')
    make_valid: Optional[bool] = Field(default=True, alias='makeValid')
    skip_islands: Optional[bool] = Field(default=False, alias='skipIslands')
    preserve_islands: Optional[bool] = Field(default=False, alias='preserveIslands')
    layers: List[Union[str, Dict[str, Any]]] # List of source layer names or dicts like {'name': 'src_layer', 'values': [...]}

class CopyOpParams(BaseOperationParams):
    type: str = "copy"
    layers: List[Union[str, Dict[str, Any]]] # Source layer(s)
    # 'values' might be part of the dict in layers list if filtering is per source

class DifferenceOpParams(BaseOperationParams):
    type: Literal["difference"] = "difference"
    layers: List[Union[str, Dict[str, Any]]]

class IntersectionOpParams(BaseOperationParams):
    type: Literal["intersection"] = "intersection"
    layers: List[Union[str, Dict[str, Any]]]

class WmtsWmsOpParams(BaseOperationParams): # Special, often doesn't take a source_layer from project
    type: Union[Literal["wmts"], Literal["wms"]] # Ensure Literal where applicable
    url: str
    # 'layer' here means layer on remote service, not a GDF source_layer from project context usually
    layer: str # Name of the layer on the remote service
    srs: str
    format: Optional[str] = 'image/png'
    target_folder: Optional[str] = Field(None, alias='targetFolder')
    buffer: Optional[float] = 0.0
    zoom: Optional[int] = None
    overwrite: Optional[bool] = False

class MergeOpParams(BaseOperationParams): # Processes a list of layers
    type: Literal["merge"] = "merge" # Ensure Literal
    layers: List[Union[str, Dict[str, Any]]]

class SmoothOpParams(BaseOperationParams): # Unary, needs 'layer'
    type: Literal["smooth"] = "smooth" # Ensure Literal
    layer: Union[str, Dict[str, Any]] # Added for unary op
    strength: Optional[float] = 1.0

class ContourOpParams(BaseOperationParams): # May be unary if applied to a DEM layer from project
    type: Literal["contour"] = "contour" # Ensure Literal
    layer: Optional[Union[str, Dict[str, Any]]] = None # Source DEM layer if applicable
    url: Optional[str] = None
    buffer: Optional[float] = 0.0
    interval: float = 10.0

class DissolveOpParams(BaseOperationParams): # Unary
    type: Literal["dissolve"] = "dissolve" # Ensure Literal
    layer: Union[str, Dict[str, Any]]
    by_column: Optional[Union[str, List[str]]] = Field(default=None, alias="byColumn")
    agg_func: Optional[Union[str, Dict[str, str]]] = Field(default=None, alias="aggFunc")
    as_index: bool = Field(default=False)

class CalculateOpParams(BaseOperationParams): # Unary
    type: Literal["calculate"] = "calculate" # Ensure Literal
    layer: Union[str, Dict[str, Any]] # Added for unary op
    expression: str
    new_field_name: str = Field(alias="newFieldName")

class FilterByAttributeOpParams(BaseOperationParams): # Unary
    type: Literal["filter_by_attribute"] = "filter_by_attribute" # Ensure Literal
    layer: Union[str, Dict[str, Any]]
    column: Optional[str] = None
    values: List[Any]
    keep_matching: bool = Field(default=True, alias="keepMatching")

class SimplifyOpParams(BaseOperationParams): # Unary
    type: Literal["simplify"] = "simplify" # Ensure Literal
    layer: Union[str, Dict[str, Any]]
    tolerance: float
    preserve_topology: bool = Field(default=True, alias="preserveTopology")

class ExplodeMultipartOpParams(BaseOperationParams): # Unary
    type: Literal["explode_multipart"]
    layer: Union[str, Dict[str, Any]] # Added for unary op
    ignore_index: bool = True

# New Pydantic models for FilterByIntersectionOpParams
class FilterLayerItem(BaseModel):
    """Defines a layer used for filtering in an intersection operation."""
    model_config = ConfigDict(extra='forbid')
    layer_name: str
    attribute_filter_column: Optional[str] = None
    attribute_filter_values: Optional[List[Any]] = None
    add_filter_layer_name_column: Optional[str] = None

class FilterByIntersectionOpParams(BaseOperationParams): # Unary for the main source layer
    """Parameters for filtering a source layer by intersection with one or more other layers."""
    type: Literal["filter_by_intersection"]
    layer: Union[str, Dict[str, Any]] # Main source layer to be filtered
    filter_layers: List[FilterLayerItem] # Definition of layers to use as filters
    explode_source_before_filter: bool = True
    filter_geometry_buffer_distance: float = 0.0
    keep_matching: bool = True

class RemoveIslandsOpParams(BaseOperationParams): # Unary
    type: Literal["remove_islands"] = "remove_islands"
    layer: Union[str, Dict[str, Any]]
    preserve_islands: bool = Field(default=False, description="If True, keeps holes (islands). If False (default), removes holes.")

class SnapToGridOpParams(BaseOperationParams): # Unary
    type: Literal["snap_to_grid"] = "snap_to_grid"
    layer: Union[str, Dict[str, Any]]
    grid_size: float = Field(..., gt=0, description="The grid size to snap coordinates to. Must be positive.")

class UnionOpParams(BaseOperationParams): # Binary
    type: Literal["union"] = "union"
    layers: List[Union[str, Dict[str, Any]]] # Expects two layers

class SymmetricDifferenceOpParams(BaseOperationParams): # Binary
    type: Literal["symmetric_difference"] = "symmetric_difference"
    layers: List[Union[str, Dict[str, Any]]] # Expects two layers

class OffsetCurveOpParams(BaseOperationParams): # Unary
    type: Literal["offset_curve"] = "offset_curve"
    layer: Union[str, Dict[str, Any]]
    distance: float
    distance_field: Optional[str] = Field(None, alias="distanceField")
    quad_segs: int = Field(default=8, alias="quadSegs")
    join_style: Literal['round', 'mitre', 'bevel'] = Field(default='round', alias="joinStyle")
    mitre_limit: float = Field(default=5.0, alias="mitreLimit")

class DifferenceByPropertyOpParams(BaseOperationParams):
    type: Literal["difference_by_property"] = "difference_by_property"
    layer: Union[str, Dict[str, Any]] # Main layer
    difference_layer: Union[str, Dict[str, Any]] # Layer to subtract from main
    main_layer_property: str
    difference_layer_property: str
    on_no_match_in_diff: Literal["keep_main_feature", "empty_main_geometry", "remove_main_feature"] = Field(
        default="keep_main_feature", alias="onNoMatchInDiff"
    )
    on_difference_error: Literal["keep_main_feature", "empty_main_geometry", "remove_main_feature"] = Field(
        default="keep_main_feature", alias="onDifferenceError"
    )

class FilterByGeometryPropertiesOpParams(BaseOperationParams):
    type: Literal["filter_by_geometry_properties"] = "filter_by_geometry_properties"
    layer: Union[str, Dict[str, Any]]
    min_area: Optional[float] = Field(default=None, ge=0)
    max_area: Optional[float] = Field(default=None, ge=0)
    min_width: Optional[float] = Field(default=None, ge=0) # Estimated width
    max_width: Optional[float] = Field(default=None, ge=0) # Estimated width
    geometry_types: Optional[List[Literal['polygon', 'line', 'point']]] = Field(default=None, alias="geometryTypes")

    @model_validator(mode='after')
    def check_min_max_consistency(cls, values: Any) -> Any: # Changed to Any for Pydantic v2
        # Pydantic v2: `values` is the model instance itself. Access fields via attribute.
        # This validation might be tricky if fields are None. Let's access directly.
        min_a = getattr(values, 'min_area', None)
        max_a = getattr(values, 'max_area', None)
        min_w = getattr(values, 'min_width', None)
        max_w = getattr(values, 'max_width', None)

        if min_a is not None and max_a is not None and min_a > max_a:
            raise ValueError("min_area cannot be greater than max_area")
        if min_w is not None and max_w is not None and min_w > max_w:
            raise ValueError("min_width cannot be greater than max_width")
        return values

class RotateOpParams(BaseOperationParams):
    type: Literal["rotate"] = "rotate"
    layer: Union[str, Dict[str, Any]]
    angle: float # Angle in degrees
    origin_type: Literal['center', 'centroid', 'point'] = Field(default='center', alias="originType")
    origin_coords: Optional[Tuple[float, float]] = Field(default=None, alias="originCoords") # Used if origin_type is 'point'

    @model_validator(mode='after')
    def check_origin_consistency(cls, values: Any) -> Any:
        origin_t = getattr(values, 'origin_type', None)
        origin_c = getattr(values, 'origin_coords', None)
        if origin_t == 'point' and origin_c is None:
            raise ValueError("origin_coords must be provided when origin_type is 'point'")
        return values

class ScaleOpParams(BaseOperationParams):
    type: Literal["scale"] = "scale"
    layer: Union[str, Dict[str, Any]]
    xfact: float = 1.0
    yfact: float = 1.0
    zfact: float = 1.0 # Will be effectively ignored by shapely.affinity.scale for 2D geoms
    origin_type: Literal['center', 'centroid', 'point'] = Field(default='center', alias="originType")
    origin_coords: Optional[Tuple[float, float]] = Field(default=None, alias="originCoords") # Used if origin_type is 'point'

    @model_validator(mode='after')
    def check_scale_origin_consistency(cls, values: Any) -> Any: # Renamed validator
        origin_t = getattr(values, 'origin_type', None)
        origin_c = getattr(values, 'origin_coords', None)
        if origin_t == 'point' and origin_c is None:
            raise ValueError("origin_coords must be provided for ScaleOpParams when origin_type is 'point'")
        return values

class TranslateOpParams(BaseOperationParams):
    type: Literal["translate"] = "translate"
    layer: Union[str, Dict[str, Any]]
    x_offset: float = Field(default=0.0, alias="xOffset")
    y_offset: float = Field(default=0.0, alias="yOffset")
    z_offset: float = Field(default=0.0, alias="zOffset") # Will be effectively ignored for 2D geometries

class BoundingBoxOpParams(BaseOperationParams):
    type: Literal["bounding_box"] = "bounding_box"
    layers: List[Union[str, Dict[str, Any]]] # List of source layer names or layer definitions
    padding: float = Field(default=0.0)

class EnvelopeOpParams(BaseOperationParams):
    type: Literal["envelope"] = "envelope"
    layers: List[Union[str, Dict[str, Any]]] = Field(..., description="List of source layer identifiers to process.")
    padding: float = Field(0.0, description="Padding to add around the envelope. Can be negative to shrink.")
    min_ratio: Optional[float] = Field(None, description="Minimum length/width ratio of the MBR. If ratio is less, original geometry is returned. Applies before bend processing and to final MBR.")
    cap_style: Literal["square", "round"] = Field("square", description="Style of the envelope caps: 'square' or 'round'.")

    @field_validator('min_ratio')
    @classmethod
    def min_ratio_must_be_positive_or_none(cls, v_min_ratio):
        if v_min_ratio is not None and v_min_ratio < 0:
            raise ValueError('min_ratio must be non-negative if specified.')
        return v_min_ratio

class CreateCirclesOpParams(BaseOperationParams):
    type: Literal["create_circles"] = "create_circles"
    layers: List[Union[str, Dict[str, Any]]] = Field(..., description="List of source layer identifiers to process.")
    radius: Optional[float] = Field(None, description="Fixed radius for all circles. Provide this or radius_field.")
    radius_field: Optional[str] = Field(None, description="Name of the attribute field in the source layer GDF that contains radius values for each feature. Provide this or radius.")

    @model_validator(mode='after')
    @classmethod
    def check_radius_or_radius_field(cls, values):
        radius, radius_field = values.radius, values.radius_field
        if radius is None and radius_field is None:
            raise ValueError('Either "radius" or "radius_field" must be provided.')
        if radius is not None and radius_field is not None:
            raise ValueError('Cannot provide both "radius" and "radius_field". Choose one.')
        if radius is not None and radius <= 0:
            raise ValueError('Fixed "radius" must be positive.')
        return values

class ConnectPointsOpParams(BaseOperationParams):
    type: Literal["connect_points"] = "connect_points"
    layers: List[Union[str, Dict[str, Any]]] = Field(..., description="List of source layer identifiers containing points to connect.")
    max_distance: Optional[float] = Field(None, alias="maxDistance", ge=0, description="Maximum distance to group points. If None, all points are connected into a single line. Must be non-negative if specified.")

# Update AllOperationParams to include the new operation type
AllOperationParams = Union[
    BufferOpParams,
    CalculateOpParams,
    ConnectPointsOpParams,
    CopyOpParams,
    ContourOpParams,
    DifferenceOpParams,
    IntersectionOpParams,
    WmtsWmsOpParams,
    MergeOpParams,
    SmoothOpParams,
    DissolveOpParams,
    FilterByAttributeOpParams,
    SimplifyOpParams,
    ExplodeMultipartOpParams,
    FilterByIntersectionOpParams,
    RemoveIslandsOpParams,
    SnapToGridOpParams,
    UnionOpParams,
    SymmetricDifferenceOpParams,
    OffsetCurveOpParams,
    DifferenceByPropertyOpParams,
    FilterByGeometryPropertiesOpParams,
    RotateOpParams,
    ScaleOpParams,
    TranslateOpParams,
    BoundingBoxOpParams,
    EnvelopeOpParams,
    CreateCirclesOpParams
]

class GeomLayerDefinition(BaseModel):
    """Definition for a geometric layer, typically from geom_layers.yaml."""
    model_config = ConfigDict(extra='ignore')

    name: str
    shape_file: Optional[str] = Field(default=None, alias="shapeFile")
    dxf_layer: Optional[str] = Field(default=None, alias="dxfLayer")
    geojson_file: Optional[str] = Field(default=None, alias="geojsonFile") # New field for GeoJSON source
    select_by_properties: Optional[Dict[str, Any]] = Field(default=None, alias="selectByProperties")
    operations: Optional[List[AllOperationParams]] = Field(default_factory=list)
    close_polygons: bool = Field(default=False, alias="closePolygons")
    target_attribute_map: Optional[Dict[str, str]] = Field(default=None, alias="targetAttributeMap")
    # New fields for preprocessing control
    explode_blocks: bool = Field(default=False, alias="explodeBlocks")
    circles_to_polygons: bool = Field(default=False, alias="circlesToPolygons")
    circles_to_polygons_segments: int = Field(default=64, alias="circlesToPolygonsSegments")
    extract_basepoints: bool = Field(default=False, alias="extractBasepoints")
    basepoint_target_entity_types: Optional[List[str]] = Field(
        default_factory=lambda: ["INSERT", "TEXT", "MTEXT", "POINT"],
        alias="basepointTargetEntityTypes"
    )
    basepoint_attribute_prefix: str = Field(default="bp_", alias="basepointAttributePrefix")
    # TODO: Potentially add 'basepoint_extraction_mode' (e.g., "insert_point", "centroid") for more control

    style: Optional[Union[str, NamedStyle]] = None
    update_dxf: Optional[bool] = Field(default=True, alias="updateDxf")
    label_column: Optional[str] = Field(default=None, alias="label")

class LegendItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str
    style: Optional[Union[str, NamedStyle]] = None # Style name or inline style for the legend item text/symbol

class LegendDefinition(BaseModel):
    """Definition for a map legend, from legends.yaml."""
    model_config = ConfigDict(extra='ignore')
    name: str
    position: CoordsXY # Using the common type
    items: List[LegendItem]
    # Other legend properties (e.g., title_style, frame_style)

class ViewportDefinition(BaseModel): # Placeholder
    model_config = ConfigDict(extra='ignore')
    name: str
    # ... other viewport properties like center, scale, layer_visibility etc.

class BlockInsertDefinition(BaseModel): # Placeholder
    model_config = ConfigDict(extra='ignore')
    block_name: str = Field(alias="blockName")
    layer: str
    # ... insert points, scales, rotations (could be list of instances)

class TextInsertDefinition(BaseModel): # Placeholder
    model_config = ConfigDict(extra='ignore')
    text_string: str = Field(alias="textString")
    layer: str
    position: CoordsXY
    style: Optional[Union[str, NamedStyle]] = None
    # ... other text properties

class PathArrayDefinition(BaseModel): # Placeholder
    model_config = ConfigDict(extra='ignore')
    # ... properties for path array

# WMTS/WMS layers are distinct from geomLayers in ProjectLoader, define them separately
class BaseWebLayerDefinition(BaseModel): # Parent for WMTS/WMS specific project items
    model_config = ConfigDict(extra='ignore')
    name: str
    url: str
    layer_name_on_service: str = Field(alias="layer") # Name of the layer on the remote service
    srs: str
    format: Optional[str] = 'image/png'
    target_folder: Optional[str] = Field(None, alias='targetFolder') # Where to cache tiles/images
    # Base style for the layer if it's visualized directly (e.g. outline)
    style: Optional[Union[str, NamedStyle]] = None
    operations: Optional[List[AllOperationParams]] = Field(default_factory=list) # Ops might use this web layer as a source

class WmtsLayerProjectDefinition(BaseWebLayerDefinition):
    # WMTS specific fields like zoom levels, matrixSet, etc. can be added
    pass

class WmsLayerProjectDefinition(BaseWebLayerDefinition):
    # WMS specific fields like version, transparent, etc. can be added
    pass

class DxfOperationExtract(BaseModel): # Placeholder
    model_config = ConfigDict(extra='forbid')
    # ... properties for DXF extraction operations

class DxfOperationTransfer(BaseModel): # Placeholder
    model_config = ConfigDict(extra='forbid')
    # ... properties for DXF transfer operations

class DxfOperationsConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')
    extracts: Optional[List[DxfOperationExtract]] = Field(default_factory=list)
    transfers: Optional[List[DxfOperationTransfer]] = Field(default_factory=list)

class SpecificProjectConfig(BaseModel):
    """Aggregates all settings for a specific project."""
    model_config = ConfigDict(extra='ignore')

    main: ProjectMainSettings
    geom_layers: List[GeomLayerDefinition] = Field(default_factory=list, alias='geomLayers')
    legends: List[LegendDefinition] = Field(default_factory=list)
    viewports: List[ViewportDefinition] = Field(default_factory=list) # Placeholder
    block_inserts: List[BlockInsertDefinition] = Field(default_factory=list, alias='blockInserts') # Placeholder
    text_inserts: List[TextInsertDefinition] = Field(default_factory=list, alias='textInserts') # Placeholder
    path_arrays: List[PathArrayDefinition] = Field(default_factory=list, alias='pathArrays') # Placeholder
    wmts_layers: List[WmtsLayerProjectDefinition] = Field(default_factory=list, alias='wmtsLayers')
    wms_layers: List[WmsLayerProjectDefinition] = Field(default_factory=list, alias='wmsLayers')
    dxf_operations: Optional[DxfOperationsConfig] = Field(None, alias='dxfOperations')
    # Styles specific to this project, if they override global styles.yaml
    project_specific_styles: Optional[Dict[str, NamedStyle]] = Field(None, alias='styles')


class GlobalProjectSettings(BaseSettings):
    """Global settings, typically from a root projects.yaml, loaded via pydantic-settings."""
    model_config = ConfigDict(env_prefix='APP_') # Example if env vars are APP_FOLDER_PREFIX

    folder_prefix: Optional[str] = Field(None, alias='folderPrefix')
    log_file: Optional[str] = Field(default='./app_log.txt', alias='logFile')
    # Add other global settings here

class AppConfig(BaseSettings):
    """Main application configuration model, root of all settings."""
    # For pydantic-settings to load from .env file or environment variables
    model_config = ConfigDict(env_file='.env', extra='ignore')

    global_settings: GlobalProjectSettings = Field(default_factory=GlobalProjectSettings)

    # These would be loaded by a config service based on the selected project
    # For now, AppConfig can define their types. The actual instance of SpecificProjectConfig
    # and associated StyleConfig/ColorConfig would be dynamically loaded.
    # Alternatively, AppConfig could hold paths to these config files.

    # Option 2: Hold paths or references, actual loading done by a service
    projects_root_dir: str = "projects" # Default, can be overridden by env
    global_styles_file: str = "styles.yaml"
    aci_colors_file: str = "aci_colors.yaml"

    # Example of a setting that could come from .env
    default_project_name: Optional[str] = Field(None, alias="DEFAULT_PROJECT_NAME")

    # Logging level for console, can be overridden by env: APP_LOG_LEVEL_CONSOLE
    log_level_console: str = Field(default="INFO", alias="LOG_LEVEL_CONSOLE")
