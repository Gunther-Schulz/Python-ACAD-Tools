from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field
from .common_schemas import ColorModel # Assuming ColorModel might be used for text/lines
from .style_schemas import TextStylePropertiesConfig, StyleObjectConfig # For styling text and swatches

class LegendLayoutConfig(BaseModel):
    position_x: float = Field(default=0.0, description="X coordinate for the legend's top-left anchor point.")
    position_y: float = Field(default=0.0, description="Y coordinate for the legend's top-left anchor point.")
    max_text_width: float = Field(default=50.0, description="Maximum width for text elements before wrapping.")
    title_spacing_to_content: float = Field(default=5.0, description="Space between legend title and first group/item.")
    group_spacing: float = Field(default=10.0, description="Vertical space between legend groups.")
    item_spacing: float = Field(default=3.0, description="Vertical space between items within a group.")
    swatch_width: float = Field(default=10.0, description="Width of the color/style swatch.")
    swatch_height: float = Field(default=5.0, description="Height of the color/style swatch.")
    swatch_to_text_spacing: float = Field(default=2.0, description="Horizontal space between swatch and item text.")
    column_spacing: float = Field(default=10.0, description="Horizontal space between columns if using multi-column layout.") # For future use
    max_columns: int = Field(default=1, description="Maximum number of columns for items within a group.") # For future use

class LegendItemStyleConfig(BaseModel): # Corresponds to usage in legend_generation_service
    swatch_type: Literal["area", "line", "diagonal_line", "empty"] = Field(default="area", description="Type of swatch to draw.")
    # Potentially direct color/linetype overrides if not using a full StyleObjectConfig
    # For now, assume StyleObjectConfig from layer/preset is primary source for swatch style

class LegendItemConfig(BaseModel):
    label: str = Field(description="Text label for the legend item.")
    layer_name_source: Optional[str] = Field(default=None, description="Layer name to source style from (if style_preset_source is not used).")
    style_preset_source: Optional[str] = Field(default=None, description="Name of a style preset to source style from for the swatch.")
    style_inline_override: Optional[StyleObjectConfig] = Field(default=None, description="Inline style to override the sourced style for the swatch.")
    item_specific_style: Optional[LegendItemStyleConfig] = Field(default_factory=LegendItemStyleConfig, description="Specific styling for the legend item's swatch.")
    item_text_style_preset_name: Optional[str] = Field(default=None, description="Preset name for the item's text style.")
    item_text_style_inline: Optional[TextStylePropertiesConfig] = Field(default=None, description="Inline text style for the item.")
    # value: Optional[str] = Field(default=None, description="Optional value associated with the item (e.g., for classified legends).") # Future use

class LegendGroupConfig(BaseModel):
    name: str = Field(description="Name/title of the legend group.")
    group_text_style_preset_name: Optional[str] = Field(default=None, description="Preset name for the group title's text style.")
    group_text_style_inline: Optional[TextStylePropertiesConfig] = Field(default=None, description="Inline text style for the group title.")
    items: List[LegendItemConfig] = Field(description="List of items within this group.")

class LegendDefinitionConfig(BaseModel):
    id: str = Field(description="Unique identifier for this legend definition.")
    title: Optional[str] = Field(default=None, description="Main title of the legend.")
    subtitle: Optional[str] = Field(default=None, description="Subtitle of the legend.")
    layout: LegendLayoutConfig = Field(default_factory=LegendLayoutConfig)
    groups: List[LegendGroupConfig] = Field(description="List of groups in the legend.")
    overall_title_text_style_preset_name: Optional[str] = Field(default=None, description="Preset name for the main title's text style.")
    overall_title_text_style_inline: Optional[TextStylePropertiesConfig] = Field(default=None, description="Inline text style for the main title.")
    overall_subtitle_text_style_preset_name: Optional[str] = Field(default=None, description="Preset name for the subtitle's text style.")
    overall_subtitle_text_style_inline: Optional[TextStylePropertiesConfig] = Field(default=None, description="Inline text style for the subtitle.")
    background_box_enabled: bool = Field(default=False, description="Enable a background box for the entire legend.")
    # background_box_style_preset: Optional[str] = None # Future: Style for the background box
    # background_box_style_inline: Optional[StyleObjectConfig] = None # Future

__all__ = [
    "LegendLayoutConfig", "LegendItemStyleConfig", "LegendItemConfig",
    "LegendGroupConfig", "LegendDefinitionConfig"
]
