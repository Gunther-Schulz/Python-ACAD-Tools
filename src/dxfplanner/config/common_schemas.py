from typing import Optional, Tuple, List, Union, Any
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

class LoggingConfig(BaseModel):
    level: str = Field(default="INFO", description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL).")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Logging format string.")
    # file_path: Optional[str] = Field(default=None, description="Optional file path to log to. If None, logs to console.")

class MappingRuleConfig(BaseModel):
    dxf_property_name: str = Field(description="Target DXF property name (e.g., 'layer', 'color_256', 'text_content').")
    source_expression: str = Field(description="Asteval expression to get the value from feature properties (e.g., 'properties.attribute_name').")
    condition: Optional[str] = Field(default=None, description="Optional asteval expression; rule applies if true or not set.")
    target_type: Optional[str] = Field(default=None, description="Optional type to cast value to (e.g., 'str', 'int', 'float', 'aci_color').")
    on_error_value: Optional[Any] = Field(default=None, description="Value to use if expression evaluation or casting fails.")
    priority: int = Field(default=0, description="Priority of the rule (lower numbers processed first).")

class AttributeMappingServiceConfig(BaseModel):
    mapping_rules: List[MappingRuleConfig] = Field(default_factory=list, description="List of attribute mapping rules.")
    default_dxf_layer_on_mapping_failure: Optional[str] = Field(default=None, description="Default DXF layer if no rule assigns one.")

class CoordinateServiceConfig(BaseModel):
    default_source_crs: Optional[str] = Field(default=None, description="Default source CRS string if not found in data (e.g., 'EPSG:4326').")
    default_target_crs: Optional[str] = Field(default=None, description="Default target CRS string for outputs (e.g., 'EPSG:25832').")

class ServicesSettings(BaseModel):
    coordinate: Optional[CoordinateServiceConfig] = Field(default_factory=CoordinateServiceConfig)
    # Future: add other service-specific configs here
    # attribute_mapping: Optional[AttributeMappingServiceConfig] = Field(default_factory=AttributeMappingServiceConfig)
    # validation: Optional[ValidationServiceConfig] = Field(default_factory=ValidationServiceConfig)
