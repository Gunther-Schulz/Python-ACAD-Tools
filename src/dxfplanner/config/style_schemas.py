from typing import Optional, List, Dict, Any, Literal, Tuple
from pydantic import BaseModel, Field
from enum import Enum

from .common_schemas import ColorModel # Assuming ColorModel is in common_schemas.py

# --- Layer Display Properties ---
class LayerDisplayPropertiesConfig(BaseModel):
    """Defines display properties for entities on a layer."""
    color: Optional[ColorModel] = Field(default=None, description="Color of entities on the layer.")
    linetype: Optional[str] = Field(default=None, description="Linetype for entities (e.g., 'CONTINUOUS', 'DASHED').")
    lineweight: Optional[int] = Field(default=None, description="Lineweight in 1/100mm (e.g., 25 for 0.25mm). -1=ByLayer, -2=ByBlock, -3=Default.")
    transparency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Transparency (0.0=opaque, 1.0=fully transparent).")
    plot: Optional[bool] = Field(default=True, description="Whether entities on this layer are plottable.")
    # visible: Optional[bool] = Field(default=True) # Already in DxfEntity, layer visibility is via DxfLayerConfig.is_off

# --- Text Styling Properties ---
class TextParagraphPropertiesConfig(BaseModel):
    """Properties related to paragraph formatting for MTEXT."""
    alignment: Optional[Literal[
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    ]] = Field(default=None, description="MTEXT attachment point.") # This is attachment_point for MTEXT
    line_spacing_factor: Optional[float] = Field(default=None, ge=0.25, le=4.0, description="MTEXT line spacing factor.")
    # flow_direction: Optional[Literal['Horizontal', 'Vertical']] = None # DXF MTEXT flow direction

class TextStylePropertiesConfig(BaseModel):
    """Defines properties for applying text styling to TEXT or MTEXT entities."""
    font_name_or_style_preset: Optional[str] = Field(default=None, description="Name of a DXF TEXTSTYLE or a predefined font (e.g., 'Arial', 'ISOCP.shx').")
    height: Optional[float] = Field(default=None, gt=0.0, description="Text height. If None, uses DXF TEXTSTYLE height or default.")
    width_factor: Optional[float] = Field(default=None, gt=0.0, description="Text width factor.")
    oblique_angle: Optional[float] = Field(default=None, ge=0.0, lt=360.0, description="Text oblique angle in degrees.")
    rotation_degrees: Optional[float] = Field(default=0.0, description="Text rotation angle in degrees.")
    color: Optional[ColorModel] = Field(default=None, description="Color of the text. Overrides layer color if set.")
    # For MTEXT primarily, these relate to the bounding box and internal formatting
    mtext_width: Optional[float] = Field(default=None, gt=0.0, description="MTEXT bounding box width (optional, for word wrapping).")
    paragraph_props: Optional[TextParagraphPropertiesConfig] = Field(default_factory=TextParagraphPropertiesConfig, description="Paragraph formatting for MTEXT.")
    # For TEXT (single line text) alignment:
    halign: Optional[Literal['LEFT', 'CENTER', 'RIGHT', 'ALIGNED', 'MIDDLE', 'FIT']] = Field(default=None, description="Horizontal alignment for TEXT entities.")
    valign: Optional[Literal['BASELINE', 'BOTTOM', 'MIDDLE', 'TOP']] = Field(default=None, description="Vertical alignment for TEXT entities.")
    # attachment_point from TextParagraphPropertiesConfig is for MTEXT DXF group code 71
    # halign/valign are for TEXT DXF group codes 72/73
    # StyleService will need to map paragraph_props.alignment to MTEXT attachment_point
    # and use halign/valign for TEXT entities.
    attachment_point: Optional[Literal[
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    ]] = Field(default=None, description="Generic attachment point, maps to MTEXT attachment or informs TEXT alignment point.")


# --- Hatch Styling Properties ---
class HatchPropertiesConfig(BaseModel):
    """Defines properties for applying HATCH patterns."""
    pattern_name: Optional[str] = Field(default="SOLID", description="Name of the hatch pattern (e.g., 'SOLID', 'ANSI31').")
    scale: Optional[float] = Field(default=1.0, gt=0.0, description="Hatch pattern scale.")
    angle: Optional[float] = Field(default=0.0, ge=0.0, lt=360.0, description="Hatch pattern angle in degrees.")
    color: Optional[ColorModel] = Field(default=None, description="Color of the hatch. Overrides layer color if set.")
    style: Optional[Literal['NORMAL', 'OUTERMOST', 'IGNORE']] = Field(default='NORMAL', description="Hatch style (Normal, Outer, Ignore).")
    # background_color: Optional[ColorModel] = None # For SOLID patterns if different from foreground

# --- Composite Style Object ---
class StyleObjectConfig(BaseModel):
    """A composite object defining all aspects of styling for a feature or layer element."""
    layer_props: Optional[LayerDisplayPropertiesConfig] = Field(default_factory=LayerDisplayPropertiesConfig)
    text_props: Optional[TextStylePropertiesConfig] = Field(default_factory=TextStylePropertiesConfig)
    hatch_props: Optional[HatchPropertiesConfig] = Field(default_factory=HatchPropertiesConfig)
    # Future: point_symbol_props, etc.

    class Config:
        extra = "allow" # Allow other fields if needed for extensions

# --- Style Rule for Feature-Specific Styling ---
class StyleRuleConfig(BaseModel):
    """Defines a rule for applying specific styles based on feature attributes."""
    name: Optional[str] = Field(default=None, description="Optional name for the style rule.")
    condition: str = Field(description="Condition string to evaluate against feature attributes (e.g., \"type == 'road'\" or \"area > 1000\").")
    priority: int = Field(default=0, description="Priority of the rule (lower numbers apply first). Rules with same priority apply in definition order.")
    style_override: StyleObjectConfig = Field(description="The style object to apply/merge if the condition is met.")
    terminate: bool = Field(default=False, description="If True, no further style rules are processed for the feature if this rule's condition is met.")

# --- Labeling Configuration (New) ---
class LabelingConfig(BaseModel):
    """Configuration for defining how labels are generated and styled."""
    enabled: bool = Field(default=True, description="Whether labeling is active based on this configuration.")
    label_attribute: Optional[str] = Field(default=None, description="Attribute field from the GeoFeature to use for the label text. If None, fixed_text might be used.")
    fixed_text: Optional[str] = Field(default=None, description="A fixed string to use as the label text. Overrides label_attribute if both are set.")
    text_style: Optional[TextStylePropertiesConfig] = Field(default_factory=TextStylePropertiesConfig, description="Detailed styling for the label text.")

    # Placement related fields (simplified for now)
    offset_xy: Optional[Tuple[float, float]] = Field(default=(0.0, 0.0), description="(dx, dy) offset from the anchor point for the label.")
    # placement_strategy: Optional[Literal["point_center", "line_middle", "polygon_centroid"]] = Field(default="point_center", description="Strategy for determining the label's anchor point.") # Future
    # leader_line_style: Optional[LineStyleConfig] # Future, if leader lines are supported

    layer_name: Optional[str] = Field(default=None, description="Target layer for the label entities. If None, uses feature's layer or a default label layer.")
    xdata_app_id: Optional[str] = Field(default="DXFPLANNER_LABEL", description="Application ID for XDATA attached to label entities.")
    xdata_tags: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom XDATA key-value pairs for label entities.")

    class Config:
        extra = "forbid" # Ensure no unexpected fields are passed
