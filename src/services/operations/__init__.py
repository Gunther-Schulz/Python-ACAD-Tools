"""Operations module for geometry processing following existing patterns."""
from .base_operation_handler import BaseOperationHandler
from .operation_registry import OperationRegistry
from .transformation_handlers import TranslateHandler, RotateHandler, ScaleHandler
from .spatial_analysis_handlers import (
    BufferHandler, DifferenceHandler, IntersectionHandler, UnionHandler,
    SymmetricDifferenceHandler, BoundingBoxHandler, EnvelopeHandler, OffsetCurveHandler
)
from .geometry_creation_handlers import CreateCirclesHandler, ConnectPointsHandler
# TODO: Fix missing operation parameters before enabling these handlers
# from .data_processing_handlers import (
#     CopyHandler, MergeHandler, SimplifyHandler, DissolveHandler,
#     ExplodeMultipartHandler, RemoveIslandsHandler, SnapToGridHandler,
#     SmoothHandler, DifferenceByPropertyHandler
# )
# from .filtering_handlers import (
#     FilterByAttributeHandler, FilterByGeometryPropertiesHandler,
#     CalculateHandler, FilterByIntersectionHandler
# )
# from .advanced_handlers import ContourHandler, WmtsHandler, WmsHandler

__all__ = [
    'BaseOperationHandler',
    'OperationRegistry',
    'TranslateHandler',
    'RotateHandler',
    'ScaleHandler',
    'BufferHandler',
    'DifferenceHandler',
    'IntersectionHandler',
    'UnionHandler',
    'SymmetricDifferenceHandler',
    'BoundingBoxHandler',
    'EnvelopeHandler',
    'OffsetCurveHandler',
    'CreateCirclesHandler',
    'ConnectPointsHandler',
    # TODO: Re-enable these after fixing missing operation parameters
    # 'CopyHandler',
    # 'MergeHandler',
    # 'SimplifyHandler',
    # 'DissolveHandler',
    # 'ExplodeMultipartHandler',
    # 'RemoveIslandsHandler',
    # 'SnapToGridHandler',
    # 'SmoothHandler',
    # 'DifferenceByPropertyHandler',
    # 'FilterByAttributeHandler',
    # 'FilterByGeometryPropertiesHandler',
    # 'CalculateHandler',
    # 'FilterByIntersectionHandler',
    # 'ContourHandler',
    # 'WmtsHandler',
    # 'WmsHandler',
]
