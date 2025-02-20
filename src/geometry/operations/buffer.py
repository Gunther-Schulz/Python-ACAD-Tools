"""Buffer operation implementation."""

from dataclasses import dataclass
from typing import Optional, List
from shapely.geometry import base as shapely_base
from ..types.base import GeometryData, GeometryMetadata
from .base import UnaryOperation, OperationValidator

@dataclass
class BufferParameters:
    """Parameters for buffer operation."""
    distance: float
    resolution: int = 16
    cap_style: int = 1  # round=1, flat=2, square=3
    join_style: int = 1  # round=1, mitre=2, bevel=3
    mitre_limit: float = 5.0
    single_sided: bool = False

class BufferValidator(OperationValidator[BufferParameters]):
    """Validator for buffer operation parameters."""
    
    def __init__(self):
        self.errors: List[str] = []
    
    def validate(self, params: BufferParameters) -> bool:
        """Validate buffer parameters."""
        self.errors = []
        
        if not isinstance(params.distance, (int, float)):
            self.errors.append("Distance must be a number")
        
        if not isinstance(params.resolution, int) or params.resolution < 4:
            self.errors.append("Resolution must be an integer >= 4")
        
        if params.cap_style not in {1, 2, 3}:
            self.errors.append("Cap style must be 1 (round), 2 (flat), or 3 (square)")
        
        if params.join_style not in {1, 2, 3}:
            self.errors.append("Join style must be 1 (round), 2 (mitre), or 3 (bevel)")
        
        if not isinstance(params.mitre_limit, (int, float)) or params.mitre_limit <= 0:
            self.errors.append("Mitre limit must be a positive number")
        
        return len(self.errors) == 0
    
    def get_validation_errors(self) -> List[str]:
        """Get validation errors."""
        return self.errors

class BufferOperation(UnaryOperation[BufferParameters, GeometryData]):
    """Implementation of buffer operation."""
    
    def __init__(self):
        super().__init__(validator=BufferValidator())
    
    def process_geometry(
        self,
        geometry: GeometryData,
        params: BufferParameters
    ) -> GeometryData:
        """Apply buffer to geometry."""
        # Create buffer
        buffered = geometry.geometry.buffer(
            distance=params.distance,
            resolution=params.resolution,
            cap_style=params.cap_style,
            join_style=params.join_style,
            mitre_limit=params.mitre_limit,
            single_sided=params.single_sided
        )
        
        # Create new metadata
        new_metadata = GeometryMetadata(
            source_type=geometry.metadata.source_type,
            source_crs=geometry.metadata.source_crs,
            attributes=geometry.metadata.attributes.copy()
        )
        
        # Add operation to log
        new_metadata.operations_log = geometry.metadata.operations_log.copy()
        new_metadata.operations_log.append(
            f"buffer: distance={params.distance}, "
            f"resolution={params.resolution}, "
            f"cap_style={params.cap_style}, "
            f"join_style={params.join_style}, "
            f"mitre_limit={params.mitre_limit}, "
            f"single_sided={params.single_sided}"
        )
        
        # Return new geometry data
        return GeometryData(
            id=f"{geometry.id}_buffered",
            geometry=buffered,
            metadata=new_metadata
        ) 