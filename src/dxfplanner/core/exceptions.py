class DXFPlannerBaseError(Exception):
    """Base exception for the DXFPlanner application."""
    pass

class ConfigurationError(DXFPlannerBaseError):
    """Error related to application configuration."""
    pass

class GeoDataReadError(DXFPlannerBaseError):
    """Error reading or interpreting input geodata."""
    pass

class DxfGenerationError(DXFPlannerBaseError):
    """Error specifically during DXF file generation."""
    pass # More specific sub-exceptions like DxfWriteError can be added

class DxfWriteError(DxfGenerationError):
    """Error during the actual writing of the DXF file content."""
    pass

class CoordinateTransformError(DXFPlannerBaseError):
    """Error during coordinate system transformation."""
    pass

class GeometryTransformError(DXFPlannerBaseError):
    """Error during geometry transformation to DxfEntity objects."""
    pass

class OrchestrationError(DXFPlannerBaseError):
    """Error during service orchestration."""
    pass

class PipelineError(DXFPlannerBaseError):
    """Error within a processing pipeline step."""
    pass
