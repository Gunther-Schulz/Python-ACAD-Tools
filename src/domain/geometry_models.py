"""Geometry-related domain models following PROJECT_ARCHITECTURE.MD specification."""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum

from .common_types import CoordinateReferenceSystem


class GeometryType(str, Enum):
    """Supported geometry types."""
    POINT = "Point"
    LINESTRING = "LineString"
    POLYGON = "Polygon"
    MULTIPOINT = "MultiPoint"
    MULTILINESTRING = "MultiLineString"
    MULTIPOLYGON = "MultiPolygon"
    GEOMETRYCOLLECTION = "GeometryCollection"


class OperationType(str, Enum):
    """Available geometry operation types."""
    BUFFER = "buffer"
    INTERSECTION = "intersection"
    UNION = "union"
    DIFFERENCE = "difference"
    SIMPLIFY = "simplify"
    TRANSFORM = "transform"
    FILTER = "filter"
    MERGE = "merge"
    CLIP = "clip"
    DISSOLVE = "dissolve"
    ENVELOPE = "envelope"


class AllOperationParams(BaseModel):
    """Base class for all operation parameters."""
    model_config = ConfigDict(extra='ignore')

    type: OperationType
    name: Optional[str] = None
    description: Optional[str] = None


class BufferOperationParams(AllOperationParams):
    """Parameters for buffer operations."""
    type: OperationType = OperationType.BUFFER
    distance: float
    resolution: int = 16
    cap_style: str = "round"  # round, flat, square
    join_style: str = "round"  # round, mitre, bevel


class FilterOperationParams(AllOperationParams):
    """Parameters for filter operations."""
    type: OperationType = OperationType.FILTER
    filter_layers: List[Dict[str, Any]]
    attribute_filter_column: Optional[str] = None
    attribute_filter_values: Optional[List[Any]] = None
    spatial_predicate: str = "intersects"  # intersects, contains, within, etc.


class TransformOperationParams(AllOperationParams):
    """Parameters for coordinate transformation operations."""
    type: OperationType = OperationType.TRANSFORM
    target_crs: CoordinateReferenceSystem
    source_crs: Optional[CoordinateReferenceSystem] = None


class TranslateOpParams(AllOperationParams):
    """Parameters for translate operations."""
    type: OperationType = OperationType.TRANSFORM
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0


class RotateOpParams(AllOperationParams):
    """Parameters for rotate operations."""
    type: OperationType = OperationType.TRANSFORM
    angle: float  # In degrees
    origin_x: float = 0.0
    origin_y: float = 0.0


class ScaleOpParams(AllOperationParams):
    """Parameters for scale operations."""
    type: OperationType = OperationType.TRANSFORM
    scale_x: float = 1.0
    scale_y: float = 1.0
    origin_x: float = 0.0
    origin_y: float = 0.0


class GeomLayerDefinition(BaseModel):
    """Definition for a geometry layer."""
    model_config = ConfigDict(extra='ignore')

    name: str
    geojson_file: Optional[str] = Field(None, alias='geojsonFile')
    shape_file: Optional[str] = Field(None, alias='shapeFile')
    dxf_layer: Optional[str] = Field(None, alias='dxfLayer')
    style: Optional[str] = None
    label_column: Optional[str] = Field(None, alias='labelColumn')
    operations: Optional[List[AllOperationParams]] = None

    # Layer metadata
    description: Optional[str] = None
    source: Optional[str] = None
    last_updated: Optional[str] = Field(None, alias='lastUpdated')

    @field_validator('operations', mode='before')
    @classmethod
    def validate_operations(cls, v):
        """Validate and convert operation parameters."""
        if v is None:
            return v

        validated_ops = []
        for op in v:
            if isinstance(op, dict):
                op_type = op.get('type')
                if op_type == OperationType.BUFFER:
                    validated_ops.append(BufferOperationParams(**op))
                elif op_type == OperationType.FILTER:
                    validated_ops.append(FilterOperationParams(**op))
                elif op_type == OperationType.TRANSFORM:
                    validated_ops.append(TransformOperationParams(**op))
                else:
                    # Generic operation for unknown types
                    validated_ops.append(AllOperationParams(**op))
            else:
                validated_ops.append(op)

        return validated_ops


# Forward reference resolution will be handled by importing modules
# from .style_models import NamedStyle
# GeomLayerDefinition.model_rebuild()

# Spatial Analysis Operation Parameters
class BufferOpParams(AllOperationParams):
    """Parameters for buffer operations."""
    type: OperationType = OperationType.BUFFER
    distance: float
    resolution: int = 16
    cap_style: str = "round"
    join_style: str = "round"


class DifferenceOpParams(AllOperationParams):
    """Parameters for difference operations."""
    type: OperationType = OperationType.DIFFERENCE
    overlay_layer: str
    keep_geom_type: bool = True


class IntersectionOpParams(AllOperationParams):
    """Parameters for intersection operations."""
    type: OperationType = OperationType.INTERSECTION
    overlay_layer: str
    keep_geom_type: bool = True


class UnionOpParams(AllOperationParams):
    """Parameters for union operations."""
    type: OperationType = OperationType.UNION
    overlay_layer: Optional[str] = None  # If None, union all geometries in layer


class SymmetricDifferenceOpParams(AllOperationParams):
    """Parameters for symmetric difference operations."""
    type: OperationType = OperationType.DIFFERENCE
    overlay_layer: str
    keep_geom_type: bool = True


class BoundingBoxOpParams(AllOperationParams):
    """Parameters for bounding box operations."""
    type: OperationType = OperationType.ENVELOPE
    expand_by: float = 0.0


class EnvelopeOpParams(AllOperationParams):
    """Parameters for envelope operations."""
    type: OperationType = OperationType.ENVELOPE
    expand_by: float = 0.0


class OffsetCurveOpParams(AllOperationParams):
    """Parameters for offset curve operations."""
    type: OperationType = OperationType.BUFFER
    distance: float
    side: str = "both"  # left, right, both


# Geometry Creation Operation Parameters
class CreateCirclesOpParams(AllOperationParams):
    """Parameters for creating circles."""
    type: OperationType = OperationType.BUFFER
    radius: float
    num_points: int = 32


class ConnectPointsOpParams(AllOperationParams):
    """Parameters for connecting points."""
    type: OperationType = OperationType.MERGE
    connection_type: str = "linestring"  # linestring, polygon


# Advanced Operation Parameters
class ContourOpParams(AllOperationParams):
    """Parameters for contour operations."""
    type: OperationType = OperationType.TRANSFORM
    elevation_field: str
    contour_interval: float


class WmtsOpParams(AllOperationParams):
    """Parameters for WMTS operations."""
    type: OperationType = OperationType.TRANSFORM
    wmts_url: str
    layer_name: str
    tile_matrix_set: str


class WmsOpParams(AllOperationParams):
    """Parameters for WMS operations."""
    type: OperationType = OperationType.TRANSFORM
    wms_url: str
    layer_name: str
    srs: str
