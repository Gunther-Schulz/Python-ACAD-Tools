from typing import Optional, List, Union, Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field, validator
from enum import Enum
from .common_schemas import ColorModel, FontProperties, ExtentsModel, CRSModel # Import from new common_schemas
from .style_schemas import LabelingConfig

# --- Operation Config Enums and Base ---
class GeometryOperationType(str, Enum):
    BUFFER = "BUFFER"
    SIMPLIFY = "SIMPLIFY"
    DISSOLVE = "DISSOLVE"
    REPROJECT = "REPROJECT"
    CLEAN_GEOMETRY = "CLEAN_GEOMETRY"
    EXPLODE_MULTIPART = "EXPLODE_MULTIPART"
    INTERSECTION = "INTERSECTION"
    MERGE = "MERGE"
    FILTER_BY_ATTRIBUTE = "FILTER_BY_ATTRIBUTE"
    FILTER_BY_EXTENT = "FILTER_BY_EXTENT"
    FIELD_MAPPING = "FIELD_MAPPING"
    LABEL_PLACEMENT = "LABEL_PLACEMENT"
    # TODO: Add more as they are supported

class BaseOperationConfig(BaseModel):
    """Base model for all geometry operation configurations."""
    type: GeometryOperationType
    # Common fields for operations can be added here if needed in the future.
    # For example, a 'name' or 'description' for the operation step.
    output_layer_name: Optional[str] = Field(default=None, description="Optional name for the output layer/feature stream of this operation. If None, a default or intermediate name may be used.")


# --- Specific Operation Configs ---

class BufferOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.BUFFER] = GeometryOperationType.BUFFER
    distance: float = Field(description="Buffer distance in the units of the geometry's CRS.")
    resolution: int = Field(default=16, description="Resolution of the buffer approximation.")
    join_style: Literal["round", "mitre", "bevel"] = Field(default="round", description="Style of line joins.")
    cap_style: Literal["round", "flat", "square"] = Field(default="round", description="Style of line endings (caps).")
    mitre_limit: float = Field(default=5.0, description="Mitre limit for 'mitre' join style.")
    distance_field: Optional[str] = Field(default=None, description="Optional attribute field name on features to source per-feature buffer distance.")
    # single_sided: bool = Field(default=False, description="If True, creates a single-sided buffer for lines (not yet fully supported by simple buffer).") # Keep commented out for now
    make_valid_pre_buffer: bool = Field(default=True, description="Attempt to make input geometries valid before buffering.")
    make_valid_post_buffer: bool = Field(default=True, description="Attempt to make output geometries valid after buffering.")
    skip_islands: bool = Field(default=False, description="If True, removes all islands/holes from the input geometry before buffering (effectively fills holes).")
    preserve_islands: bool = Field(default=False, description="If True, attempts to preserve islands within polygons during buffering. If False, islands might be filled. Works in conjunction with skip_islands.")


class SimplifyOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.SIMPLIFY] = GeometryOperationType.SIMPLIFY
    tolerance: float = Field(description="Simplification tolerance in the units of the geometry's CRS.")
    preserve_topology: bool = Field(default=True, description="Whether to preserve topology during simplification.")


class DissolveOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.DISSOLVE] = GeometryOperationType.DISSOLVE
    by_attribute: Optional[str] = Field(default=None, description="Attribute field to dissolve by. If None, all geometries are dissolved together.")
    # TODO: Add aggregation options for attributes if needed


class ReprojectOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.REPROJECT] = GeometryOperationType.REPROJECT
    target_crs: CRSModel = Field(description="Target Coordinate Reference System.")


class CleanGeometryOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.CLEAN_GEOMETRY] = GeometryOperationType.CLEAN_GEOMETRY
    # Specific cleaning options can be added here, e.g., precision
    # For now, it might just use a default "make_valid" strategy.
    buffer_amount: float = Field(default=0.0, description="Applies a zero-buffer to attempt to fix invalid geometries. Sometimes a very small positive buffer helps more.")


class ExplodeMultipartOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.EXPLODE_MULTIPART] = GeometryOperationType.EXPLODE_MULTIPART
    # No specific parameters needed for now.


# --- Intersection Attribute Handling Schemas ---
class IntersectionInputAttributeOptions(BaseModel):
    keep_attributes: Union[Literal["all", "none"], List[str]] = Field(
        default="all",
        description="Specifies which attributes from the input feature to keep. 'all', 'none', or a list of attribute names."
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Optional prefix to add to all kept input attribute names."
    )

class IntersectionOverlayAttributeOptions(BaseModel):
    # Due to unary_union of overlay features, we can't easily pick attributes from specific original overlay features.
    # This allows adding fixed attributes or attributes derived from the overlay *layer's* general properties if an intersection occurs.
    add_attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        description="A dictionary of fixed key-value attributes to add to the intersected feature if it intersects with the overlay geometry."
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Optional prefix for keys in 'add_attributes' if they are added."
    )
    # Consider: layer_properties_to_include: Optional[List[str]] = None # To fetch from LayerConfig of overlay_layer_name

class IntersectionAttributeConflictResolution(str, Enum):
    PREFER_INPUT = "prefer_input"
    PREFER_OVERLAY = "prefer_overlay" # "overlay" refers to attributes from add_attributes
    # Add more strategies if needed, e.g., ERROR, RENAME_OVERLAY

class IntersectionAttributeOptionsConfig(BaseModel):
    input_options: IntersectionInputAttributeOptions = Field(default_factory=IntersectionInputAttributeOptions)
    overlay_options: Optional[IntersectionOverlayAttributeOptions] = Field(default=None) # Optional, if no attributes from overlay are desired
    conflict_resolution: IntersectionAttributeConflictResolution = Field(
        default=IntersectionAttributeConflictResolution.PREFER_INPUT,
        description="Strategy to resolve attribute name conflicts if attributes are added from overlay_options."
    )


class IntersectionOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.INTERSECTION] = GeometryOperationType.INTERSECTION
    # Renamed from intersect_layer_name to overlay_layer_name for clarity, as it's one layer.
    overlay_layer_name: str = Field(description="Name of the other layer (overlay) to intersect with.")
    attribute_options: Optional[IntersectionAttributeOptionsConfig] = Field(
        default=None, # If None, default behavior might be to keep all input attributes and add nothing from overlay.
        description="Configuration for handling attributes of intersected features."
    )


class MergeOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.MERGE] = GeometryOperationType.MERGE
    layers_to_merge: List[str] = Field(description="List of layer/feature stream names to merge.")
    # TODO: Add attribute handling strategies (e.g., prefixing, selection)

# --- FilterByAttribute Schemas (as previously defined and corrected) ---
class FilterOperator(str, Enum):
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN_OR_EQUAL = "<="
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"

class LogicalOperator(str, Enum):
    AND = "AND"
    OR = "OR"

class FilterCondition(BaseModel):
    attribute: str
    operator: FilterOperator
    value: Any # Can be string, number, list (for IN/NOT_IN)
    # Ensure value is appropriate for operator (e.g., list for IN, None for IS_NULL)

class FilterByAttributeOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.FILTER_BY_ATTRIBUTE] = GeometryOperationType.FILTER_BY_ATTRIBUTE
    conditions: List[FilterCondition] = Field(
        description="A list of filter conditions to apply."
    )
    logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="Logical operator to combine the conditions (AND or OR)."
    )
    # Example for (new) conditions: [FilterCondition(attribute='TYPE', operator=FilterOperator.EQUALS, value='residential'),
    #                               FilterCondition(attribute='AREA', operator=FilterOperator.GREATER_THAN, value=1000)]
    # Example for logical_operator: LogicalOperator.AND

# --- FilterByExtent Schemas ---
class ExtentFilterMode(str, Enum):
    INTERSECTS = "intersects"
    CONTAINS = "contains"
    WITHIN = "within"
    DISJOINT = "disjoint"
    TOUCHES = "touches"
    CROSSES = "crosses"
    OVERLAPS = "overlaps"

class FilterByExtentOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.FILTER_BY_EXTENT] = GeometryOperationType.FILTER_BY_EXTENT
    extent: ExtentsModel = Field(description="The bounding box to filter by.")
    mode: ExtentFilterMode = Field(
        default=ExtentFilterMode.INTERSECTS,
        description="Spatial relationship mode to determine how features relate to the extent."
    )

class FieldMappingOperationConfig(BaseOperationConfig):
    type: Literal[GeometryOperationType.FIELD_MAPPING] = GeometryOperationType.FIELD_MAPPING
    mapping: Dict[str, str] = Field(description="Dictionary of old_field_name: new_field_name.")
    copy_unmapped_fields: bool = Field(
        default=True,
        description="If True, fields not in the source of the 'mapping' are copied to the output with their original names."
    )
    drop_unmapped_fields: bool = Field(
        default=False,
        description="If True, unmapped fields are dropped. If False and copy_unmapped_fields is False, unmapped fields are also dropped. This takes precedence if copy_unmapped_fields is True (i.e. if drop=True, copy=True -> fields are dropped)."
    )

class LabelPlacementOperationConfig(BaseOperationConfig): # Renamed from LabelPlacementConfig
    type: Literal[GeometryOperationType.LABEL_PLACEMENT] = GeometryOperationType.LABEL_PLACEMENT
    label_attribute: str = Field(description="Attribute field to use for labels.")
    label_settings: Optional[LabelingConfig] = Field(default=None, description="Detailed labeling configuration. If None, labeling might be disabled or use very basic defaults controlled by StyleService.")
    # TODO: Add offset, rotation, leader line options, conflict resolution strategy (These should go into LabelingConfig)
    source_layer: Optional[str] = Field(default=None, description="Optional source layer for labels if different from the current layer being processed. If None, uses the current layer.")
    output_label_layer_name: Optional[str] = Field(default=None, description="Optional explicit name for the output layer containing only labels. If None, labels might be added to a default label layer or the operation's output_layer_name.")

# --- Union of all Operation Configs ---
AnyOperationConfig = Union[
    BufferOperationConfig,
    SimplifyOperationConfig,
    DissolveOperationConfig,
    ReprojectOperationConfig,
    CleanGeometryOperationConfig,
    ExplodeMultipartOperationConfig,
    IntersectionOperationConfig,
    MergeOperationConfig,
    FilterByAttributeOperationConfig,
    FilterByExtentOperationConfig,
    FieldMappingOperationConfig,
    LabelPlacementOperationConfig # Changed here
]
