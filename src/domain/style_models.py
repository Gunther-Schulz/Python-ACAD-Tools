"""Style-related domain models following PROJECT_ARCHITECTURE.MD specification."""
from typing import Dict, Optional, Union, List, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum


# DXF Lineweight Constants (following ezdxf documentation)
class DXFLineweight:
    """DXF lineweight constants following ezdxf specification.

    Lineweight values are in mm × 100 (e.g., 0.25mm = 25).
    Special values: -3 (Default), -2 (ByBlock), -1 (ByLayer).
    """
    # Special lineweight values
    DEFAULT = -3
    BYBLOCK = -2
    BYLAYER = -1

    # Standard lineweight values (mm × 100)
    VALID_LINEWEIGHTS = (
        0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100,
        106, 120, 140, 158, 200, 211
    )

    @classmethod
    def is_valid_lineweight(cls, value: int) -> bool:
        """Check if a lineweight value is valid according to DXF specification."""
        return value in (cls.DEFAULT, cls.BYBLOCK, cls.BYLAYER) or value in cls.VALID_LINEWEIGHTS


class TextAttachmentPoint(str, Enum):
    """Text attachment point options."""
    TOP_LEFT = "TOP_LEFT"
    TOP_CENTER = "TOP_CENTER"
    TOP_RIGHT = "TOP_RIGHT"
    MIDDLE_LEFT = "MIDDLE_LEFT"
    MIDDLE_CENTER = "MIDDLE_CENTER"
    MIDDLE_RIGHT = "MIDDLE_RIGHT"
    BOTTOM_LEFT = "BOTTOM_LEFT"
    BOTTOM_CENTER = "BOTTOM_CENTER"
    BOTTOM_RIGHT = "BOTTOM_RIGHT"


class LineSpacingStyle(str, Enum):
    """Line spacing style options."""
    AT_LEAST = "at_least"
    EXACTLY = "exactly"


class FlowDirection(str, Enum):
    """Text flow direction options."""
    LEFT_TO_RIGHT = "left_to_right"
    RIGHT_TO_LEFT = "right_to_left"
    TOP_TO_BOTTOM = "top_to_bottom"
    BOTTOM_TO_TOP = "bottom_to_top"


class LayerStyleProperties(BaseModel):
    """Style properties for DXF layers."""
    model_config = ConfigDict(extra='ignore')

    color: Optional[Union[str, int]] = None
    linetype: Optional[str] = None
    linetype_pattern: Optional[List[float]] = Field(None, alias='linetypePattern')
    lineweight: Optional[Union[int, str]] = None
    transparency: Optional[float] = None
    plot: Optional[bool] = None
    is_on: Optional[bool] = Field(None, alias='isOn')
    frozen: Optional[bool] = None
    locked: Optional[bool] = None

    @field_validator('lineweight')
    @classmethod
    def validate_lineweight(cls, v):
        """Validate lineweight follows DXF specification. Accepts int or valid string representations."""
        if v is None:
            return None

        if isinstance(v, str):
            lw_str = v.upper()
            if lw_str == "BYLAYER":
                v_int = DXFLineweight.BYLAYER
            elif lw_str == "BYBLOCK":
                v_int = DXFLineweight.BYBLOCK
            elif lw_str == "DEFAULT":
                v_int = DXFLineweight.DEFAULT
            else:
                try:
                    lw_float = float(v)
                    v_int = int(lw_float * 100)
                except ValueError:
                    raise ValueError(f"Invalid string lineweight value: {v}. Must be a number, 'BYLAYER', 'BYBLOCK', or 'DEFAULT'.")
        elif isinstance(v, int):
            v_int = v
        else:
            raise TypeError(f"Lineweight must be an int or string, got {type(v)}")

        if not DXFLineweight.is_valid_lineweight(v_int):
            raise ValueError(f"Invalid lineweight value: {v_int} (from input '{v}'). Must be one of {DXFLineweight.VALID_LINEWEIGHTS} or special values.")
        return v_int


class TextStyleProperties(BaseModel):
    """Style properties for text entities."""
    model_config = ConfigDict(extra='ignore')

    font: Optional[str] = None
    color: Optional[Union[str, int]] = None
    height: Optional[float] = None
    rotation: Optional[float] = None
    attachment_point: Optional[TextAttachmentPoint] = None
    align_to_view: Optional[bool] = Field(None, alias='alignToView')

    # MTEXT specific properties
    max_width: Optional[float] = Field(None, alias='maxWidth')
    flow_direction: Optional[FlowDirection] = Field(None, alias='flowDirection')
    line_spacing_style: Optional[LineSpacingStyle] = Field(None, alias='lineSpacingStyle')
    line_spacing_factor: Optional[float] = Field(None, alias='lineSpacingFactor')

    # Text formatting
    underline: Optional[bool] = None
    overline: Optional[bool] = None
    strike_through: Optional[bool] = Field(None, alias='strikeThrough')
    oblique_angle: Optional[float] = Field(None, alias='obliqueAngle')

    # Background fill
    bg_fill: Optional[bool] = Field(None, alias='bgFill')
    bg_fill_color: Optional[Union[str, int]] = Field(None, alias='bgFillColor')
    bg_fill_scale: Optional[float] = Field(None, alias='bgFillScale')


class HatchStyleProperties(BaseModel):
    """Properties specific to hatch styling."""
    model_config = ConfigDict(extra='ignore', validate_assignment=True)

    pattern_name: Optional[str] = None
    scale: Optional[float] = None
    angle: Optional[float] = None
    color: Optional[Union[str, int]] = None
    spacing: Optional[float] = None


class NamedStyle(BaseModel):
    """A complete named style definition."""
    model_config = ConfigDict(extra='ignore')

    layer: Optional[LayerStyleProperties] = None
    text: Optional[TextStyleProperties] = None
    hatch: Optional[HatchStyleProperties] = None


class StyleConfig(BaseModel):
    """Configuration for all styles."""
    model_config = ConfigDict(extra='ignore')

    styles: Dict[str, NamedStyle] = Field(default_factory=dict)


class AciColorMappingItem(BaseModel):
    """Mapping between color names and ACI codes."""
    model_config = ConfigDict(extra='ignore')

    name: str
    aci_code: int = Field(alias='aciCode')
    rgb: Optional[Union[str, List[int]]] = None
    hex_code: Optional[str] = Field(None, alias='hexCode')

    @field_validator('aci_code')
    @classmethod
    def validate_aci_code(cls, v):
        """Validate ACI code is in valid range."""
        if not (0 <= v <= 255):
            raise ValueError(f"ACI code must be between 0 and 255, got {v}")
        return v

    @field_validator('rgb')
    @classmethod
    def validate_rgb(cls, v):
        """Convert RGB list to string format if needed."""
        if v is None:
            return v
        if isinstance(v, list):
            if len(v) == 3 and all(isinstance(x, int) and 0 <= x <= 255 for x in v):
                return f"rgb({v[0]}, {v[1]}, {v[2]})"
            else:
                raise ValueError(f"RGB list must contain exactly 3 integers between 0-255, got {v}")
        elif isinstance(v, str):
            return v
        else:
            raise ValueError(f"RGB must be a string or list of 3 integers, got {type(v)}")
        return v


class ColorConfig(BaseModel):
    """Configuration for color mappings."""
    model_config = ConfigDict(extra='ignore')

    colors: List[AciColorMappingItem] = Field(default_factory=list)
