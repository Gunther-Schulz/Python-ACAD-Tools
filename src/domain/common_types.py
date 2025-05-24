"""Common, simple type aliases and data structures used across the domain."""
from typing import Tuple, Union

# Type alias for XY coordinates
CoordsXY = Tuple[float, float]

# Type alias for XYZ coordinates (optional, if needed later)
# CoordsXYZ = Tuple[float, float, float]

# Type alias for Coordinate Reference System
CoordinateReferenceSystem = Union[str, int]  # Can be EPSG code (int) or string like "EPSG:4326"

# Example of a simple common data structure if needed later:
# from pydantic import BaseModel
# class BoundingBox(BaseModel):
#     min_x: float
#     min_y: float
#     max_x: float
#     max_y: float
