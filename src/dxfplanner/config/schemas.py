from typing import Optional, List, Union, Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
from enum import Enum

# Import from new specific schema modules
from .common_schemas import (
    ColorModel, FontProperties, ExtentsModel, CRSModel, LoggingConfig,
    CoordinateServiceConfig, ServicesSettings,
    MappingRuleConfig, AttributeMappingServiceConfig # Added new configs
)
from .reader_schemas import DataSourceType, BaseReaderConfig, ShapefileSourceConfig, GeoJSONSourceConfig, CsvWktReaderConfig, AnySourceConfig
from .operation_schemas import (
    GeometryOperationType, BaseOperationConfig,
    BufferOperationConfig, SimplifyOperationConfig, DissolveOperationConfig,
    ReprojectOperationConfig, CleanGeometryOperationConfig, ExplodeMultipartOperationConfig,
    IntersectionOperationConfig, MergeOperationConfig, FilterByAttributeOperationConfig,
    FilterByExtentOperationConfig, FieldMappingOperationConfig, LabelPlacementOperationConfig,
    IntersectionAttributeOptionsConfig,
    IntersectionInputAttributeOptions, IntersectionOverlayAttributeOptions, IntersectionAttributeConflictResolution,
    AnyOperationConfig, FilterOperator, LogicalOperator, FilterCondition # Ensure these are also available if used directly in LayerConfig/ProjectConfig
)
from .dxf_writer_schemas import (
    LinetypeConfig, TextStyleConfig, BlockEntityAttribsConfig, BlockPointConfig,
    BlockLineConfig, BlockPolylineConfig, BlockCircleConfig, BlockArcConfig,
    BlockTextConfig, AnyBlockEntityConfig, BlockDefinitionConfig, DxfLayerConfig,
    DxfWriterConfig
)
# Import from new style_schemas.py
from .style_schemas import (
    LayerDisplayPropertiesConfig, # For LayerStyleConfig if it uses it directly
    TextStylePropertiesConfig,    # For LayerStyleConfig if it uses it directly
    TextParagraphPropertiesConfig, # ADDED
    HatchPropertiesConfig,      # For LayerStyleConfig if it uses it directly
    StyleObjectConfig,          # For ProjectConfig.style_presets and StyleRuleConfig
    StyleRuleConfig             # For LayerConfig.style_rules
)
from .legend_schemas import ( # ADDED
    LegendLayoutConfig, LegendItemStyleConfig, LegendItemConfig,
    LegendGroupConfig, LegendDefinitionConfig
)


# --- Layer and Main Project Configuration ---

class PipelineConfig(BaseModel):
    name: str
    layers_to_process: List[str]
    layers_to_write: List[str]


class LayerStyleConfig(BaseModel):
    """Defines visual styling for a layer (primarily for display or intermediate use, not direct DXF layer table)."""
    # This could be used for QGIS styling, or pre-DXF visualization.
    # For direct DXF layer properties, use DxfLayerConfig within DxfWriterConfig.
    # This model seems more aligned with component properties rather than a full StyleObjectConfig.
    # Let's assume it holds direct properties that StyleService might consolidate or use.
    fill_color: Optional[ColorModel] = None
    stroke_color: Optional[ColorModel] = None
    stroke_width: Optional[float] = Field(default=1.0, description="Stroke width in pixels or points for rendering.")
    opacity: Optional[float] = Field(default=1.0, description="Opacity from 0.0 (transparent) to 1.0 (opaque).")
    # If this LayerStyleConfig is meant to be a simpler version of StyleObjectConfig:
    layer_props: Optional[LayerDisplayPropertiesConfig] = Field(default_factory=LayerDisplayPropertiesConfig)
    text_props: Optional[TextStylePropertiesConfig] = Field(default_factory=TextStylePropertiesConfig)
    hatch_props: Optional[HatchPropertiesConfig] = Field(default_factory=HatchPropertiesConfig)


class LayerConfig(BaseModel):
    """Configuration for a single data processing layer."""
    name: str = Field(description="Unique name for the layer.")
    source: AnySourceConfig = Field(description="Data source configuration.")
    operations: Optional[List[AnyOperationConfig]] = Field(default=None, description="List of operations to perform on this layer.")
    style: Optional[LayerStyleConfig] = Field(default=None, description="Basic styling information for the layer.") # Kept original style field

    # Fields for StyleService.get_resolved_style_object and feature styling
    style_preset_name: Optional[str] = Field(default=None, description="Name of a style preset to apply to this layer as a base.")
    style_inline_definition: Optional[StyleObjectConfig] = Field(default=None, description="An inline StyleObjectConfig to apply as a base or override preset.")
    style_override: Optional[StyleObjectConfig] = Field(default=None, description="A StyleObjectConfig to specifically override parts of the base style (preset or inline).")
    style_rules: Optional[List[StyleRuleConfig]] = Field(default_factory=list, description="List of rules for feature-specific styling.")

    description: Optional[str] = Field(default=None)
    enabled: bool = Field(default=True, description="Whether this layer processing is enabled.")


class ProjectConfig(BaseSettings):
    """Root configuration for a DXF Planner project."""
    project_name: str = Field(default="DXFPlannerProject", description="Name of the project.")
    version: Optional[str] = Field(default=None, description="Project configuration schema version.")
    default_crs: Optional[CRSModel] = Field(default=None, description="Default Coordinate Reference System for the project if not specified elsewhere.")
    layers: List[LayerConfig] = Field(description="List of layer configurations.")
    dxf_writer: DxfWriterConfig = Field(description="Configuration for the DXF writer and output DXF properties.")
    style_presets: Dict[str, StyleObjectConfig] = Field(default_factory=dict, description="Reusable style presets.")
    legends: Optional[List[LegendDefinitionConfig]] = Field(default_factory=list, description="List of legend definitions for the project.")
    pipelines: Optional[List[PipelineConfig]] = Field(default_factory=list, description="List of processing pipelines.")
    logging: Optional[LoggingConfig] = Field(default_factory=LoggingConfig, description="Logging configuration.")
    services: Optional[ServicesSettings] = Field(default_factory=ServicesSettings, description="Service-specific configurations.")

    # Global settings, logging, etc.
    # log_level: Optional[str] = Field(default="INFO", description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR).")
    # temp_file_path: Optional[str] = Field(default=None, description="Path for temporary files. If None, uses system temp.")

    @validator('layers')
    def layer_names_unique(cls, layers):
        names = [layer.name for layer in layers]
        if len(names) != len(set(names)):
            raise ValueError('Layer names must be unique within a project.')
        return layers

# Re-export all imported names for easier access from other modules if they were importing from schemas.py
# This makes the refactoring less breaking for modules that did `from .config.schemas import X`
__all__ = [
    "ColorModel", "FontProperties", "ExtentsModel", "CRSModel", "LoggingConfig", "CoordinateServiceConfig", "ServicesSettings",
    "MappingRuleConfig", "AttributeMappingServiceConfig", # Added new configs
    "DataSourceType", "BaseReaderConfig", "ShapefileSourceConfig", "GeoJSONSourceConfig", "CsvWktReaderConfig", "AnySourceConfig",
    "GeometryOperationType", "BaseOperationConfig",
    "BufferOperationConfig", "SimplifyOperationConfig", "DissolveOperationConfig",
    "ReprojectOperationConfig", "CleanGeometryOperationConfig", "ExplodeMultipartOperationConfig",
    "IntersectionOperationConfig", "MergeOperationConfig", "FilterByAttributeOperationConfig",
    "FilterByExtentOperationConfig", "FieldMappingOperationConfig", "LabelPlacementOperationConfig",
    "IntersectionAttributeOptionsConfig",
    "IntersectionInputAttributeOptions", "IntersectionOverlayAttributeOptions", "IntersectionAttributeConflictResolution",
    "AnyOperationConfig", "FilterOperator", "LogicalOperator", "FilterCondition",
    "LinetypeConfig", "TextStyleConfig", "BlockEntityAttribsConfig", "BlockPointConfig",
    "BlockLineConfig", "BlockPolylineConfig", "BlockCircleConfig", "BlockArcConfig",
    "BlockTextConfig", "AnyBlockEntityConfig", "BlockDefinitionConfig", "DxfLayerConfig",
    "DxfWriterConfig",
    "LayerStyleConfig", "LayerConfig", "ProjectConfig",
    # Added from style_schemas for StyleService direct imports from this module
    "LayerDisplayPropertiesConfig", "TextStylePropertiesConfig", "TextParagraphPropertiesConfig", "HatchPropertiesConfig",
    "StyleObjectConfig", "StyleRuleConfig",
    # ADDED Legend Schemas
    "LegendLayoutConfig", "LegendItemStyleConfig", "LegendItemConfig",
    "LegendGroupConfig", "LegendDefinitionConfig", "PipelineConfig"
]
