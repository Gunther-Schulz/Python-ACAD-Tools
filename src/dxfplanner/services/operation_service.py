"""
Service responsible for orchestrating and applying a sequence of data processing operations.
"""
from typing import AsyncIterator, List, Dict, Type
from dxfplanner.config.schemas import ProjectConfig, AnyOperationConfig, OperationType
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.core.exceptions import DXFPlannerBaseError, ConfigurationError
from dxfplanner.core.logging_config import get_logger

# Import concrete operation implementations
from dxfplanner.geometry.operations import BufferOperation, SimplifyOperation, FieldMappingOperation, ReprojectOperation, CleanGeometryOperation, ExplodeMultipartOperation

logger = get_logger(__name__)

class OperationServiceError(DXFPlannerBaseError):
    """Custom exception for OperationService errors."""
    pass

class OperationService:
    """
    Orchestrates a sequence of data processing operations on features.
    """
    def __init__(self, project_config: ProjectConfig):
        self._project_config = project_config
        self._operation_map: Dict[OperationType, Type[IOperation]] = {
            OperationType.BUFFER: BufferOperation,
            OperationType.SIMPLIFY: SimplifyOperation,
            OperationType.FIELD_MAPPER: FieldMappingOperation,
            OperationType.REPROJECT: ReprojectOperation,
            OperationType.CLEAN_GEOMETRY: CleanGeometryOperation,
            OperationType.EXPLODE_MULTIPART: ExplodeMultipartOperation,
            # Map other operation types to their classes
        }
        logger.info("OperationService initialized.")
