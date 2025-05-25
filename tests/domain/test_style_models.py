"""Comprehensive tests for style-related domain models."""
import pytest
from typing import Dict, Any
from pydantic import ValidationError

from src.domain.style_models import (
    TextAttachmentPoint, LineSpacingStyle, FlowDirection,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties,
    NamedStyle, StyleConfig, AciColorMappingItem, ColorConfig
)


class TestTextAttachmentPoint:
    """Test cases for TextAttachmentPoint enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_attachment_point_values(self):
        """Test TextAttachmentPoint enum values."""
        assert TextAttachmentPoint.TOP_LEFT == "TOP_LEFT"
        assert TextAttachmentPoint.TOP_CENTER == "TOP_CENTER"
        assert TextAttachmentPoint.TOP_RIGHT == "TOP_RIGHT"
        assert TextAttachmentPoint.MIDDLE_LEFT == "MIDDLE_LEFT"
        assert TextAttachmentPoint.MIDDLE_CENTER == "MIDDLE_CENTER"
        assert TextAttachmentPoint.MIDDLE_RIGHT == "MIDDLE_RIGHT"
        assert TextAttachmentPoint.BOTTOM_LEFT == "BOTTOM_LEFT"
        assert TextAttachmentPoint.BOTTOM_CENTER == "BOTTOM_CENTER"
        assert TextAttachmentPoint.BOTTOM_RIGHT == "BOTTOM_RIGHT"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_attachment_point_from_string(self):
        """Test creating TextAttachmentPoint from string values."""
        assert TextAttachmentPoint("TOP_LEFT") == TextAttachmentPoint.TOP_LEFT
        assert TextAttachmentPoint("MIDDLE_CENTER") == TextAttachmentPoint.MIDDLE_CENTER
        assert TextAttachmentPoint("BOTTOM_RIGHT") == TextAttachmentPoint.BOTTOM_RIGHT

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_attachment_point_invalid_value(self):
        """Test TextAttachmentPoint with invalid values."""
        with pytest.raises(ValueError):
            TextAttachmentPoint("INVALID")
        with pytest.raises(ValueError):
            TextAttachmentPoint("CENTER")


class TestLineSpacingStyle:
    """Test cases for LineSpacingStyle enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_line_spacing_style_values(self):
        """Test LineSpacingStyle enum values."""
        assert LineSpacingStyle.AT_LEAST == "at_least"
        assert LineSpacingStyle.EXACTLY == "exactly"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_line_spacing_style_from_string(self):
        """Test creating LineSpacingStyle from string values."""
        assert LineSpacingStyle("at_least") == LineSpacingStyle.AT_LEAST
        assert LineSpacingStyle("exactly") == LineSpacingStyle.EXACTLY

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_line_spacing_style_invalid_value(self):
        """Test LineSpacingStyle with invalid values."""
        with pytest.raises(ValueError):
            LineSpacingStyle("invalid")
        with pytest.raises(ValueError):
            LineSpacingStyle("proportional")


class TestFlowDirection:
    """Test cases for FlowDirection enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_flow_direction_values(self):
        """Test FlowDirection enum values."""
        assert FlowDirection.LEFT_TO_RIGHT == "left_to_right"
        assert FlowDirection.RIGHT_TO_LEFT == "right_to_left"
        assert FlowDirection.TOP_TO_BOTTOM == "top_to_bottom"
        assert FlowDirection.BOTTOM_TO_TOP == "bottom_to_top"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_flow_direction_from_string(self):
        """Test creating FlowDirection from string values."""
        assert FlowDirection("left_to_right") == FlowDirection.LEFT_TO_RIGHT
        assert FlowDirection("top_to_bottom") == FlowDirection.TOP_TO_BOTTOM

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_flow_direction_invalid_value(self):
        """Test FlowDirection with invalid values."""
        with pytest.raises(ValueError):
            FlowDirection("invalid")
        with pytest.raises(ValueError):
            FlowDirection("diagonal")


class TestLayerStyleProperties:
    """Test cases for LayerStyleProperties model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_layer_style(self):
        """Test creating empty layer style."""
        style = LayerStyleProperties()

        assert style.color is None
        assert style.linetype is None
        assert style.lineweight is None
        assert style.transparency is None
        assert style.plot is None
        assert style.is_on is None
        assert style.frozen is None
        assert style.locked is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_layer_style(self):
        """Test creating complete layer style."""
        style = LayerStyleProperties(
            color="red",
            linetype="CONTINUOUS",
            lineweight=25,
            transparency=0.5,
            plot=True,
            isOn=True,
            frozen=False,
            locked=False
        )

        assert style.color == "red"
        assert style.linetype == "CONTINUOUS"
        assert style.lineweight == 25
        assert style.transparency == 0.5
        assert style.plot is True
        assert style.is_on is True
        assert style.frozen is False
        assert style.locked is False

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_layer_style_color_types(self):
        """Test different color value types."""
        # String color
        style1 = LayerStyleProperties(color="blue")
        assert style1.color == "blue"

        # Integer ACI color
        style2 = LayerStyleProperties(color=5)
        assert style2.color == 5

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_layer_style_field_aliases(self):
        """Test field aliases work correctly."""
        style = LayerStyleProperties(isOn=True)
        assert style.is_on is True

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_layer_style_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        style = LayerStyleProperties(
            color="red",
            unknown_field="ignored",
            extra_prop=123
        )

        assert style.color == "red"
        assert not hasattr(style, 'unknown_field')
        assert not hasattr(style, 'extra_prop')


class TestTextStyleProperties:
    """Test cases for TextStyleProperties model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_text_style(self):
        """Test creating empty text style."""
        style = TextStyleProperties()

        assert style.font is None
        assert style.color is None
        assert style.height is None
        assert style.rotation is None
        assert style.attachment_point is None
        assert style.align_to_view is None
        assert style.max_width is None
        assert style.flow_direction is None
        assert style.line_spacing_style is None
        assert style.line_spacing_factor is None
        assert style.underline is None
        assert style.overline is None
        assert style.strike_through is None
        assert style.oblique_angle is None
        assert style.bg_fill is None
        assert style.bg_fill_color is None
        assert style.bg_fill_scale is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_text_style(self):
        """Test creating complete text style."""
        style = TextStyleProperties(
            font="Arial",
            color="black",
            height=2.5,
            rotation=45.0,
            attachmentPoint="MIDDLE_CENTER",
            alignToView=True,
            maxWidth=100.0,
            flowDirection="left_to_right",
            lineSpacingStyle="at_least",
            lineSpacingFactor=1.2,
            underline=True,
            overline=False,
            strikeThrough=True,
            obliqueAngle=15.0,
            bgFill=True,
            bgFillColor="white",
            bgFillScale=1.1
        )

        assert style.font == "Arial"
        assert style.color == "black"
        assert style.height == 2.5
        assert style.rotation == 45.0
        assert style.attachment_point == TextAttachmentPoint.MIDDLE_CENTER
        assert style.align_to_view is True
        assert style.max_width == 100.0
        assert style.flow_direction == FlowDirection.LEFT_TO_RIGHT
        assert style.line_spacing_style == LineSpacingStyle.AT_LEAST
        assert style.line_spacing_factor == 1.2
        assert style.underline is True
        assert style.overline is False
        assert style.strike_through is True
        assert style.oblique_angle == 15.0
        assert style.bg_fill is True
        assert style.bg_fill_color == "white"
        assert style.bg_fill_scale == 1.1

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_style_field_aliases(self):
        """Test field aliases work correctly."""
        style = TextStyleProperties(
            attachmentPoint="TOP_LEFT",
            alignToView=False,
            maxWidth=50.0,
            flowDirection="top_to_bottom",
            lineSpacingStyle="exactly",
            lineSpacingFactor=1.0,
            strikeThrough=False,
            obliqueAngle=0.0,
            bgFill=False,
            bgFillColor="yellow",
            bgFillScale=1.0
        )

        assert style.attachment_point == TextAttachmentPoint.TOP_LEFT
        assert style.align_to_view is False
        assert style.max_width == 50.0
        assert style.flow_direction == FlowDirection.TOP_TO_BOTTOM
        assert style.line_spacing_style == LineSpacingStyle.EXACTLY
        assert style.line_spacing_factor == 1.0
        assert style.strike_through is False
        assert style.oblique_angle == 0.0
        assert style.bg_fill is False
        assert style.bg_fill_color == "yellow"
        assert style.bg_fill_scale == 1.0

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_style_enum_validation(self):
        """Test enum field validation."""
        # Valid enum values
        style = TextStyleProperties(
            attachmentPoint="BOTTOM_RIGHT",
            flowDirection="right_to_left",
            lineSpacingStyle="exactly"
        )
        assert style.attachment_point == TextAttachmentPoint.BOTTOM_RIGHT
        assert style.flow_direction == FlowDirection.RIGHT_TO_LEFT
        assert style.line_spacing_style == LineSpacingStyle.EXACTLY

        # Invalid enum values
        with pytest.raises(ValidationError):
            TextStyleProperties(attachmentPoint="INVALID")

        with pytest.raises(ValidationError):
            TextStyleProperties(flowDirection="invalid")

        with pytest.raises(ValidationError):
            TextStyleProperties(lineSpacingStyle="invalid")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_style_color_types(self):
        """Test different color value types."""
        # String color
        style1 = TextStyleProperties(color="red", bgFillColor="blue")
        assert style1.color == "red"
        assert style1.bg_fill_color == "blue"

        # Integer ACI color
        style2 = TextStyleProperties(color=1, bgFillColor=2)
        assert style2.color == 1
        assert style2.bg_fill_color == 2

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_text_style_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        style = TextStyleProperties(
            font="Arial",
            unknown_field="ignored",
            extra_prop=123
        )

        assert style.font == "Arial"
        assert not hasattr(style, 'unknown_field')
        assert not hasattr(style, 'extra_prop')


class TestHatchStyleProperties:
    """Test cases for HatchStyleProperties model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_hatch_style(self):
        """Test creating empty hatch style."""
        style = HatchStyleProperties()

        assert style.pattern_name is None
        assert style.color is None
        assert style.scale is None
        assert style.angle is None
        assert style.spacing is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_hatch_style(self):
        """Test creating complete hatch style."""
        style = HatchStyleProperties(
            patternName="ANSI31",
            color="green",
            scale=2.0,
            angle=45.0,
            spacing=1.5
        )

        assert style.pattern_name == "ANSI31"
        assert style.color == "green"
        assert style.scale == 2.0
        assert style.angle == 45.0
        assert style.spacing == 1.5

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_hatch_style_field_aliases(self):
        """Test field aliases work correctly."""
        style = HatchStyleProperties(patternName="SOLID")
        assert style.pattern_name == "SOLID"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_hatch_style_color_types(self):
        """Test different color value types."""
        # String color
        style1 = HatchStyleProperties(color="blue")
        assert style1.color == "blue"

        # Integer ACI color
        style2 = HatchStyleProperties(color=3)
        assert style2.color == 3

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_hatch_style_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        style = HatchStyleProperties(
            patternName="ANSI32",
            unknown_field="ignored",
            extra_prop=123
        )

        assert style.pattern_name == "ANSI32"
        assert not hasattr(style, 'unknown_field')
        assert not hasattr(style, 'extra_prop')


class TestNamedStyle:
    """Test cases for NamedStyle model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_named_style(self):
        """Test creating empty named style."""
        style = NamedStyle()

        assert style.layer is None
        assert style.text is None
        assert style.hatch is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_named_style_with_layer_only(self):
        """Test named style with only layer properties."""
        layer_props = LayerStyleProperties(color="red", linetype="DASHED")
        style = NamedStyle(layer=layer_props)

        assert style.layer == layer_props
        assert style.layer.color == "red"
        assert style.layer.linetype == "DASHED"
        assert style.text is None
        assert style.hatch is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_named_style_with_text_only(self):
        """Test named style with only text properties."""
        text_props = TextStyleProperties(font="Arial", height=2.5)
        style = NamedStyle(text=text_props)

        assert style.text == text_props
        assert style.text.font == "Arial"
        assert style.text.height == 2.5
        assert style.layer is None
        assert style.hatch is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_named_style_with_hatch_only(self):
        """Test named style with only hatch properties."""
        hatch_props = HatchStyleProperties(patternName="ANSI31", scale=1.5)
        style = NamedStyle(hatch=hatch_props)

        assert style.hatch == hatch_props
        assert style.hatch.pattern_name == "ANSI31"
        assert style.hatch.scale == 1.5
        assert style.layer is None
        assert style.text is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_named_style(self):
        """Test named style with all property types."""
        layer_props = LayerStyleProperties(color="blue", linetype="CONTINUOUS")
        text_props = TextStyleProperties(font="Times", height=3.0)
        hatch_props = HatchStyleProperties(patternName="SOLID", color="yellow")

        style = NamedStyle(
            layer=layer_props,
            text=text_props,
            hatch=hatch_props
        )

        assert style.layer == layer_props
        assert style.text == text_props
        assert style.hatch == hatch_props
        assert style.layer.color == "blue"
        assert style.text.font == "Times"
        assert style.hatch.pattern_name == "SOLID"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_named_style_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        style = NamedStyle(
            layer=LayerStyleProperties(color="red"),
            unknown_field="ignored",
            extra_prop=123
        )

        assert style.layer.color == "red"
        assert not hasattr(style, 'unknown_field')
        assert not hasattr(style, 'extra_prop')


class TestStyleConfig:
    """Test cases for StyleConfig model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_style_config(self):
        """Test creating empty style config."""
        config = StyleConfig()
        assert config.styles == {}

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_style_config_with_styles(self):
        """Test style config with named styles."""
        layer_style = NamedStyle(layer=LayerStyleProperties(color="red"))
        text_style = NamedStyle(text=TextStyleProperties(font="Arial"))

        config = StyleConfig(styles={
            "building_layer": layer_style,
            "label_text": text_style
        })

        assert len(config.styles) == 2
        assert "building_layer" in config.styles
        assert "label_text" in config.styles
        assert config.styles["building_layer"].layer.color == "red"
        assert config.styles["label_text"].text.font == "Arial"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_style_config_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        config = StyleConfig(
            styles={"test": NamedStyle()},
            unknown_field="ignored",
            extra_prop=123
        )

        assert "test" in config.styles
        assert not hasattr(config, 'unknown_field')
        assert not hasattr(config, 'extra_prop')


class TestAciColorMappingItem:
    """Test cases for AciColorMappingItem model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_minimal_aci_color_mapping(self):
        """Test creating ACI color mapping with minimal fields."""
        mapping = AciColorMappingItem(name="red", aciCode=1)

        assert mapping.name == "red"
        assert mapping.aci_code == 1
        assert mapping.rgb is None
        assert mapping.hex_code is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_aci_color_mapping(self):
        """Test creating complete ACI color mapping."""
        mapping = AciColorMappingItem(
            name="red",
            aciCode=1,
            rgb="255,0,0",
            hexCode="#FF0000"
        )

        assert mapping.name == "red"
        assert mapping.aci_code == 1
        assert mapping.rgb == "255,0,0"
        assert mapping.hex_code == "#FF0000"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_aci_color_mapping_field_aliases(self):
        """Test field aliases work correctly."""
        mapping = AciColorMappingItem(
            name="blue",
            aciCode=5,
            hexCode="#0000FF"
        )

        assert mapping.aci_code == 5
        assert mapping.hex_code == "#0000FF"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_aci_code_validation_success(self):
        """Test valid ACI code values."""
        valid_codes = [0, 1, 5, 100, 255]

        for code in valid_codes:
            mapping = AciColorMappingItem(name="test", aciCode=code)
            assert mapping.aci_code == code

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_aci_code_validation_failures(self):
        """Test invalid ACI code values."""
        invalid_codes = [-1, 256, 1000, -100]

        for code in invalid_codes:
            with pytest.raises(ValidationError) as exc_info:
                AciColorMappingItem(name="test", aciCode=code)
            assert "ACI code must be between 0 and 255" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_aci_color_mapping_required_fields(self):
        """Test that required fields are validated."""
        # Missing name
        with pytest.raises(ValidationError) as exc_info:
            AciColorMappingItem(aciCode=1)
        assert "name" in str(exc_info.value)

        # Missing aci_code
        with pytest.raises(ValidationError) as exc_info:
            AciColorMappingItem(name="red")
        assert "aci_code" in str(exc_info.value) or "aciCode" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_aci_color_mapping_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        mapping = AciColorMappingItem(
            name="green",
            aciCode=3,
            unknown_field="ignored",
            extra_prop=123
        )

        assert mapping.name == "green"
        assert mapping.aci_code == 3
        assert not hasattr(mapping, 'unknown_field')
        assert not hasattr(mapping, 'extra_prop')


class TestColorConfig:
    """Test cases for ColorConfig model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_empty_color_config(self):
        """Test creating empty color config."""
        config = ColorConfig()
        assert config.colors == []

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_color_config_with_mappings(self):
        """Test color config with color mappings."""
        red_mapping = AciColorMappingItem(name="red", aciCode=1, rgb="255,0,0")
        blue_mapping = AciColorMappingItem(name="blue", aciCode=5, rgb="0,0,255")

        config = ColorConfig(colors=[red_mapping, blue_mapping])

        assert len(config.colors) == 2
        assert config.colors[0].name == "red"
        assert config.colors[0].aci_code == 1
        assert config.colors[1].name == "blue"
        assert config.colors[1].aci_code == 5

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_color_config_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        config = ColorConfig(
            colors=[AciColorMappingItem(name="test", aciCode=1)],
            unknown_field="ignored",
            extra_prop=123
        )

        assert len(config.colors) == 1
        assert not hasattr(config, 'unknown_field')
        assert not hasattr(config, 'extra_prop')


class TestStyleModelsIntegration:
    """Integration tests for style models working together."""

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_complete_style_configuration(self):
        """Test a complete style configuration with all components."""
        # Create comprehensive layer style
        layer_style = LayerStyleProperties(
            color=1,
            linetype="CONTINUOUS",
            lineweight=25,
            transparency=0.1,
            plot=True,
            isOn=True,
            frozen=False,
            locked=False
        )

        # Create comprehensive text style
        text_style = TextStyleProperties(
            font="Arial",
            color="black",
            height=2.5,
            rotation=0.0,
            attachmentPoint="MIDDLE_CENTER",
            alignToView=False,
            maxWidth=100.0,
            flowDirection="left_to_right",
            lineSpacingStyle="at_least",
            lineSpacingFactor=1.0,
            underline=False,
            overline=False,
            strikeThrough=False,
            obliqueAngle=0.0,
            bgFill=False
        )

        # Create comprehensive hatch style
        hatch_style = HatchStyleProperties(
            patternName="ANSI31",
            color=3,
            scale=1.0,
            angle=45.0,
            spacing=2.0
        )

        # Create named style with all components
        building_style = NamedStyle(
            layer=layer_style,
            text=text_style,
            hatch=hatch_style
        )

        # Create style configuration
        style_config = StyleConfig(styles={
            "building": building_style
        })

        # Verify the complete structure
        assert len(style_config.styles) == 1
        assert "building" in style_config.styles

        style = style_config.styles["building"]
        assert style.layer.color == 1
        assert style.layer.linetype == "CONTINUOUS"
        assert style.text.font == "Arial"
        assert style.text.attachment_point == TextAttachmentPoint.MIDDLE_CENTER
        assert style.hatch.pattern_name == "ANSI31"
        assert style.hatch.angle == 45.0

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_color_mapping_integration(self):
        """Test color mapping integration with style properties."""
        # Create color mappings
        red_mapping = AciColorMappingItem(
            name="red",
            aciCode=1,
            rgb="255,0,0",
            hexCode="#FF0000"
        )
        blue_mapping = AciColorMappingItem(
            name="blue",
            aciCode=5,
            rgb="0,0,255",
            hexCode="#0000FF"
        )

        color_config = ColorConfig(colors=[red_mapping, blue_mapping])

        # Create styles using the same ACI codes
        layer_style = LayerStyleProperties(color=1)  # Red ACI code
        text_style = TextStyleProperties(color=5, bgFillColor=1)  # Blue text, red background

        named_style = NamedStyle(layer=layer_style, text=text_style)
        style_config = StyleConfig(styles={"test": named_style})

        # Verify integration
        assert len(color_config.colors) == 2
        assert color_config.colors[0].aci_code == 1
        assert color_config.colors[1].aci_code == 5

        test_style = style_config.styles["test"]
        assert test_style.layer.color == 1  # Matches red mapping
        assert test_style.text.color == 5   # Matches blue mapping
        assert test_style.text.bg_fill_color == 1  # Matches red mapping

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.style
    @pytest.mark.fast
    def test_enum_consistency_across_style_models(self):
        """Test that enums work consistently across different style models."""
        # Test same enum values in different contexts
        text_style1 = TextStyleProperties(
            attachmentPoint="TOP_LEFT",
            flowDirection="left_to_right",
            lineSpacingStyle="at_least"
        )

        text_style2 = TextStyleProperties(
            attachmentPoint=TextAttachmentPoint.TOP_LEFT,
            flowDirection=FlowDirection.LEFT_TO_RIGHT,
            lineSpacingStyle=LineSpacingStyle.AT_LEAST
        )

        # Verify enum consistency
        assert text_style1.attachment_point == text_style2.attachment_point
        assert text_style1.flow_direction == text_style2.flow_direction
        assert text_style1.line_spacing_style == text_style2.line_spacing_style
        assert text_style1.attachment_point == TextAttachmentPoint.TOP_LEFT
        assert text_style1.flow_direction == FlowDirection.LEFT_TO_RIGHT
        assert text_style1.line_spacing_style == LineSpacingStyle.AT_LEAST
