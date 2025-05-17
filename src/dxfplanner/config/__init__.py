# __init__.py for dxfplanner.config

# Import core configurations and key enums/unions to be available
# directly from `from dxfplanner.config import ...`

from .common_schemas import (
    ColorModel,
    FontProperties,
    ExtentsModel,
    CRSModel
)

from .reader_schemas import (
    DataSourceType,
    BaseReaderConfig,
    ShapefileSourceConfig,
    GeoJSONSourceConfig,
    CsvWktReaderConfig,
    AnySourceConfig
)

from .operation_schemas import (
    GeometryOperationType,
    BaseOperationConfig,
    BufferOperationConfig,
    SimplifyOperationConfig,
    DissolveOperationConfig,
    ReprojectOperationConfig,
    CleanGeometryOperationConfig,
    ExplodeMultipartOperationConfig,
    IntersectionOperationConfig,
    MergeOperationConfig,
    FilterByAttributeOperationConfig,
    FilterCondition,
    FilterOperator,
    LogicalOperator,
    FilterByExtentOperationConfig,
    FieldMappingOperationConfig,
    LabelPlacementConfig,
    AnyOperationConfig
)

from .dxf_writer_schemas import (
    LinetypeConfig,
    TextStyleConfig,
    BlockEntityAttribsConfig,
    BlockPointConfig,
    BlockLineConfig,
    BlockPolylineConfig,
    BlockCircleConfig,
    BlockArcConfig,
    BlockTextConfig,
    AnyBlockEntityConfig,
    BlockDefinitionConfig,
    DxfLayerConfig,
    DxfWriterConfig
)

from .schemas import (
    LayerStyleConfig,
    LayerConfig,
    ProjectConfig
)

# From the new style_schemas.py
from .style_schemas import (
    LayerDisplayPropertiesConfig,
    TextParagraphPropertiesConfig,
    TextStylePropertiesConfig,
    HatchPropertiesConfig,
    StyleObjectConfig,
    StyleRuleConfig,
    LabelingConfig
)

# Define __all__ for explicit public API of the config package
__all__ = [
    # From common_schemas
    "ColorModel", "FontProperties", "ExtentsModel", "CRSModel",

    # From reader_schemas
    "DataSourceType", "BaseReaderConfig", "ShapefileSourceConfig",
    "GeoJSONSourceConfig", "CsvWktReaderConfig", "AnySourceConfig",

    # From operation_schemas
    "GeometryOperationType", "BaseOperationConfig", "BufferOperationConfig",
    "SimplifyOperationConfig", "DissolveOperationConfig", "ReprojectOperationConfig",
    "CleanGeometryOperationConfig", "ExplodeMultipartOperationConfig",
    "IntersectionOperationConfig", "MergeOperationConfig",
    "FilterByAttributeOperationConfig", "FilterCondition", "FilterOperator", "LogicalOperator",
    "FilterByExtentOperationConfig", "FieldMappingOperationConfig",
    "LabelPlacementConfig", "AnyOperationConfig",

    # From dxf_writer_schemas
    "LinetypeConfig", "TextStyleConfig", "BlockEntityAttribsConfig", "BlockPointConfig",
    "BlockLineConfig", "BlockPolylineConfig", "BlockCircleConfig", "BlockArcConfig",
    "BlockTextConfig", "AnyBlockEntityConfig", "BlockDefinitionConfig",
    "DxfLayerConfig", "DxfWriterConfig",

    # From schemas (main config file)
    "LayerStyleConfig", "LayerConfig", "ProjectConfig",

    # From style_schemas.py
    "LayerDisplayPropertiesConfig",
    "TextParagraphPropertiesConfig",
    "TextStylePropertiesConfig",
    "HatchPropertiesConfig",
    "StyleObjectConfig",
    "StyleRuleConfig",
    "LabelingConfig"
]
