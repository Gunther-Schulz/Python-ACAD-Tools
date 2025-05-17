from typing import Optional, Tuple, List, Union
from pydantic import BaseModel, Field, validator
from enum import Enum

# --- Common Reusable Pydantic Models ---

class ColorModel(BaseModel):
    """Represents a color, either as ACI or RGB."""
    aci: Optional[int] = Field(default=None, description="AutoCAD Color Index (1-255).")
    rgb: Optional[Tuple[int, int, int]] = Field(default=None, description="RGB tuple (e.g., (255, 0, 0) for red).")

    @validator('aci')
    def aci_range(cls, v):
        if v is not None and not (1 <= v <= 255):
            raise ValueError('ACI color index must be between 1 and 255')
        return v

    @validator('rgb')
    def rgb_range(cls, v):
        if v is not None:
            if not (isinstance(v, tuple) and len(v) == 3):
                raise ValueError('RGB color must be a tuple of 3 integers')
            for val in v:
                if not (0 <= val <= 255):
                    raise ValueError('RGB values must be between 0 and 255')
        return v

    @validator('rgb', always=True) # always=True ensures this runs even if rgb is None, to check aci
    def check_one_color_defined(cls, v, values):
        if v is None and values.get('aci') is None:
            raise ValueError('Either ACI or RGB must be defined for a color')
        if v is not None and values.get('aci') is not None:
            raise ValueError('Cannot define both ACI and RGB for a color')
        return v

class FontProperties(BaseModel):
    """Defines font properties for text styling."""
    font_file: str = Field(description="Path or name of the font file (e.g., 'arial.ttf', 'isocp.shx').")
    height: Optional[float] = Field(default=None, description="Text height. None for default or style-defined height.")
    width_factor: Optional[float] = Field(default=1.0, description="Text width factor.")

class ExtentsModel(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

class CRSModel(BaseModel):
    """Represents a Coordinate Reference System."""
    name: Optional[str] = Field(default=None, description="Name of the CRS (e.g., 'EPSG:4326').")
    proj_string: Optional[str] = Field(default=None, description="PROJ string representation of the CRS.")
    # TODO: Add more specific CRS validation if necessary

    @validator('proj_string', always=True)
    def check_one_crs_defined(cls, v, values):
        if v is None and values.get('name') is None:
            raise ValueError('Either name or proj_string must be defined for a CRS')
        return v
