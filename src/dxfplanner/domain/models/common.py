from pydantic import BaseModel, Field
from typing import Optional, Tuple, Union

class Coordinate(BaseModel):
    """Represents a 2D or 3D coordinate."""
    x: float
    y: float
    z: Optional[float] = None

    def to_tuple(self) -> Union[Tuple[float, float], Tuple[float, float, float]]:
        """Returns the coordinate as a tuple (x, y) or (x, y, z)."""
        if self.z is not None:
            return (self.x, self.y, self.z)
        return (self.x, self.y)

class Color(BaseModel):
    """Represents an RGB color."""
    r: int = Field(..., ge=0, le=255)  # Red component (0-255)
    g: int = Field(..., ge=0, le=255)  # Green component (0-255)
    b: int = Field(..., ge=0, le=255)  # Blue component (0-255)

    # ACI (AutoCAD Color Index) is also important for DXF.
    # This could be an alternative representation or an additional field if needed.
    # aci: Optional[int] = Field(None, ge=0, le=256)

class BoundingBox(BaseModel):
    """Represents a 2D bounding box."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    # Could add methods like: contains_point, intersects_bbox, union, etc.
