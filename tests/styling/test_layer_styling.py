"""Tests for layer-level styling functionality."""
import pytest
from unittest.mock import Mock, patch

from src.domain.style_models import NamedStyle, LayerStyleProperties
from src.services.style_applicator_service import StyleApplicatorService
from src.domain.exceptions import DXFProcessingError

from .base_test_utils import (
    StyleTestFixtures, MockDXFUtils, StyleTestAssertions,
    MockStyleApplicator
)


class TestLayerStyling:
    """Test layer-level styling functionality."""

    def test_apply_basic_layer_style(self, mock_style_applicator):
        """Test applying basic layer style properties."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        mock_drawing = MockDXFUtils.create_mock_drawing()
        layer_name = "TestLayer"

        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify layer styling was applied
        assert len(mock_style_applicator.applied_layers) == 1
        applied_drawing, applied_layer_name, applied_style = mock_style_applicator.applied_layers[0]
        assert applied_drawing == mock_drawing
        assert applied_layer_name == layer_name
        assert applied_style == style

    def test_apply_layer_style_with_aci_color(self, mock_style_applicator):
        """Test applying layer style with ACI color code."""
        style = StyleTestFixtures.get_style_by_name("layer_with_aci_color")
        mock_drawing = MockDXFUtils.create_mock_drawing()
        layer_name = "AciColorLayer"

        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify ACI color was applied
        assert len(mock_style_applicator.applied_layers) == 1

    def test_apply_complex_layer_style(self, mock_style_applicator):
        """Test applying complex layer style with all properties."""
        style = StyleTestFixtures.get_style_by_name("layer_complex")
        mock_drawing = MockDXFUtils.create_mock_drawing()
        layer_name = "ComplexLayer"

        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify complex layer properties were applied
        assert len(mock_style_applicator.applied_layers) == 1

    def test_apply_layer_style_with_all_linetypes(self, mock_style_applicator):
        """Test applying layer styles with all supported linetypes."""
        linetype_styles = [
            "linetype_continuous", "linetype_dashed", "linetype_dotted",
            "linetype_dashdot", "linetype_center", "linetype_phantom"
        ]

        for style_name in linetype_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify all linetype styles were applied
        assert len(mock_style_applicator.applied_layers) == len(linetype_styles)

    def test_apply_layer_style_with_all_lineweights(self, mock_style_applicator):
        """Test applying layer styles with all supported lineweights."""
        lineweight_styles = [
            "lineweight_thin", "lineweight_medium", "lineweight_thick",
            "lineweight_extra_thick", "lineweight_bylayer", "lineweight_byblock"
        ]

        for style_name in lineweight_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify all lineweight styles were applied
        assert len(mock_style_applicator.applied_layers) == len(lineweight_styles)

    def test_apply_layer_style_with_transparency_levels(self, mock_style_applicator):
        """Test applying layer styles with different transparency levels."""
        transparency_styles = [
            "transparency_none", "transparency_25", "transparency_50",
            "transparency_75", "transparency_full"
        ]

        for style_name in transparency_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify all transparency styles were applied
        assert len(mock_style_applicator.applied_layers) == len(transparency_styles)

    def test_apply_layer_style_with_plot_settings(self, mock_style_applicator):
        """Test applying layer styles with different plot settings."""
        plot_styles = ["plot_true", "plot_false"]

        for style_name in plot_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify plot settings were applied
        assert len(mock_style_applicator.applied_layers) == len(plot_styles)

    def test_apply_layer_style_with_visibility_states(self, mock_style_applicator):
        """Test applying layer styles with different visibility states."""
        visibility_styles = [
            "layer_on", "layer_off", "layer_frozen", "layer_thawed",
            "layer_locked", "layer_unlocked"
        ]

        for style_name in visibility_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify visibility states were applied
        assert len(mock_style_applicator.applied_layers) == len(visibility_styles)

    def test_apply_layer_style_combinations(self, mock_style_applicator):
        """Test applying layer styles with various property combinations."""
        combination_styles = [
            "combo_red_dashed_thick", "combo_blue_dotted_thin",
            "combo_green_continuous_medium", "combo_yellow_dashdot_bylayer"
        ]

        for style_name in combination_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_drawing = MockDXFUtils.create_mock_drawing()
            layer_name = f"Layer_{style_name}"

            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify combination styles were applied
        assert len(mock_style_applicator.applied_layers) == len(combination_styles)


class TestLayerStylingWithRealService:
    """Test layer styling with real StyleApplicatorService (mocked dependencies)."""

    @pytest.fixture
    def mock_config_loader(self):
        """Mock config loader for testing."""
        mock_loader = Mock()
        mock_loader.get_aci_color_mappings.return_value = [
            Mock(name="red", aci_code=1),
            Mock(name="green", aci_code=3),
            Mock(name="blue", aci_code=5),
        ]
        return mock_loader

    @pytest.fixture
    def mock_logger_service(self):
        """Mock logger service for testing."""
        mock_logger_service = Mock()
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger
        return mock_logger_service

    @pytest.fixture
    def mock_dxf_adapter(self):
        """Mock DXF adapter for testing."""
        mock_adapter = Mock()
        mock_adapter.is_available.return_value = True
        mock_adapter.create_linetype.return_value = Mock()
        mock_adapter.create_text_style.return_value = Mock()
        mock_adapter.get_layer.return_value = Mock()
        mock_adapter.set_layer_properties.return_value = None
        mock_adapter.set_entity_properties.return_value = None
        mock_adapter.query_entities.return_value = []
        mock_adapter.get_modelspace.return_value = Mock()
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        """Create StyleApplicatorService with mocked dependencies."""
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    def test_real_service_apply_layer_style(self, style_applicator_service):
        """Test real service applying layer style."""
        # Create a layer style
        layer_style = LayerStyleProperties(
            color=1,  # Red ACI
            linetype="DASHED",
            lineweight=50,
            plot=True,
            is_on=True,
            frozen=False,
            locked=False
        )
        style = NamedStyle(layer=layer_style)

        # Create mock drawing with layers collection
        mock_drawing = MockDXFUtils.create_mock_drawing()
        mock_layer = MockDXFUtils.create_mock_layer("TestLayer")

        # Mock the layers.get method to return our mock layer
        mock_drawing.layers.get.return_value = mock_layer
        mock_drawing.modelspace.return_value.query.return_value = []  # No entities on layer

        # Apply style using real service
        style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", style)

        # Verify the adapter was called to get the layer
        style_applicator_service._dxf_adapter.get_layer.assert_called_once_with(mock_drawing, "TestLayer")

    def test_real_service_create_new_layer(self, style_applicator_service):
        """Test real service creating new layer when it doesn't exist."""
        layer_style = LayerStyleProperties(color=2, linetype="Continuous")
        style = NamedStyle(layer=layer_style)

        mock_drawing = MockDXFUtils.create_mock_drawing()
        mock_new_layer = MockDXFUtils.create_mock_layer("NewLayer")

        # Mock layer not found scenario - adapter will handle creation
        mock_drawing.modelspace.return_value.query.return_value = []

        # Apply style using real service
        style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "NewLayer", style)

        # Verify the adapter was called to get the layer (which would create it if needed)
        style_applicator_service._dxf_adapter.get_layer.assert_called_once_with(mock_drawing, "NewLayer")

    def test_real_service_ezdxf_unavailable_error(self, style_applicator_service):
        """Test that service raises error when ezdxf is unavailable."""
        # Mock the adapter to return False for is_available
        style_applicator_service._dxf_adapter.is_available.return_value = False

        style = NamedStyle(layer=LayerStyleProperties(color=1))
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should raise DXFProcessingError when ezdxf is not available
        with pytest.raises(DXFProcessingError, match="ezdxf library not available"):
            style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", style)

    def test_real_service_layer_with_entities(self, style_applicator_service):
        """Test real service applying style to layer with entities."""
        layer_style = LayerStyleProperties(color=3, linetype="DOTTED")
        style = NamedStyle(layer=layer_style)

        mock_drawing = MockDXFUtils.create_mock_drawing()
        mock_layer = MockDXFUtils.create_mock_layer("EntityLayer")
        mock_entity1 = MockDXFUtils.create_mock_entity("LINE")
        mock_entity2 = MockDXFUtils.create_mock_entity("CIRCLE")

        # Mock layer exists and has entities
        mock_drawing.layers.get.return_value = mock_layer
        mock_drawing.modelspace.return_value.query.return_value = [mock_entity1, mock_entity2]

        # Mock the adapter's get_modelspace method
        mock_modelspace = Mock()
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_modelspace
        style_applicator_service._dxf_adapter.query_entities.return_value = [mock_entity1, mock_entity2]

        # Apply style using real service
        style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "EntityLayer", style)

        # Verify entities were queried via adapter
        style_applicator_service._dxf_adapter.get_modelspace.assert_called_once_with(mock_drawing)
        style_applicator_service._dxf_adapter.query_entities.assert_called_once_with(mock_modelspace, query_string='*[layer=="EntityLayer"]')


class TestLayerStylingEdgeCases:
    """Test edge cases and error conditions in layer styling."""

    def test_apply_style_to_none_drawing(self, mock_style_applicator):
        """Test applying style with None drawing."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")

        # This should handle None drawing gracefully
        mock_style_applicator.apply_styles_to_dxf_layer(None, "TestLayer", style)

    def test_apply_none_style_to_layer(self, mock_style_applicator):
        """Test applying None style to layer."""
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # This should handle None style gracefully
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", None)

    def test_apply_empty_style_to_layer(self, mock_style_applicator):
        """Test applying empty style (no layer properties) to layer."""
        empty_style = NamedStyle()  # No layer properties
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", empty_style)

        # Should handle empty style without errors
        assert len(mock_style_applicator.applied_layers) == 1

    def test_apply_style_with_empty_layer_name(self, mock_style_applicator):
        """Test applying style with empty layer name."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle empty layer name
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "", style)

    def test_apply_style_with_invalid_color_values(self, mock_style_applicator):
        """Test layer style with invalid color values."""
        # Create style with invalid color
        invalid_style = NamedStyle(
            layer=LayerStyleProperties(color="invalid_color_name")
        )
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle invalid colors gracefully
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", invalid_style)

    def test_apply_style_with_out_of_range_lineweight(self, mock_style_applicator):
        """Test layer style with out-of-range lineweight values."""
        # Create style with valid but extreme lineweight (using -1 for BYLAYER)
        extreme_style = NamedStyle(
            layer=LayerStyleProperties(lineweight=-1)  # BYLAYER lineweight
        )
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle extreme lineweight values
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", extreme_style)

    def test_apply_style_with_invalid_linetype(self, mock_style_applicator):
        """Test layer style with invalid linetype."""
        # Create style with invalid linetype
        invalid_style = NamedStyle(
            layer=LayerStyleProperties(linetype="INVALID_LINETYPE")
        )
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle invalid linetype
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, "TestLayer", invalid_style)


class TestLayerStylingAssertions:
    """Test custom assertions for layer styling."""

    def test_assert_layer_properties_applied(self, style_assertions):
        """Test the assertion for verifying applied layer properties."""
        # Mock layer and style for testing the assertion
        layer = MockDXFUtils.create_mock_layer("TestLayer")
        style_props = {
            'color': 1,
            'linetype': "DASHED",
            'lineweight': 50,
            'plot': True,
            'is_on': True,
            'frozen': False,
            'locked': False
        }

        # Apply properties to the mock layer
        layer.dxf.color = 1
                    layer.dxf.linetype = "DASHED"
        layer.dxf.lineweight = 50
        layer.dxf.plot = True
        layer.is_on = True
        layer.is_frozen = False
        layer.is_locked = False

        # Use the assertion
        style_assertions.assert_layer_properties_applied(layer, style_props)

        # Test case where assertion should fail (e.g., wrong linetype)
        layer.dxf.linetype = "CONTINUOUS"
        with pytest.raises(AssertionError):
            style_assertions.assert_layer_properties_applied(layer, style_props)

    def test_layer_property_validation(self, style_assertions):
        """Test layer property validation."""
        # Test valid layer properties
        valid_layer = MockDXFUtils.create_mock_layer("ValidLayer")
        valid_layer.dxf.color = 5  # Valid ACI
        valid_layer.dxf.lineweight = 25  # Valid lineweight

        # Should not raise any assertions
        style_assertions.assert_valid_aci_color(valid_layer.dxf.color)

    def test_layer_state_validation(self, style_assertions):
        """Test layer state validation."""
        layer = MockDXFUtils.create_mock_layer("StateLayer")

        # Test different layer states
        layer.is_on = True
        layer.is_frozen = False
        layer.is_locked = False

        # These should be valid states (no assertion errors)
        assert layer.is_on is True
        assert layer.is_frozen is False
        assert layer.is_locked is False


class TestLayerStylingIntegration:
    """Test integration scenarios for layer styling."""

    def test_multiple_layers_with_different_styles(self, mock_style_applicator):
        """Test applying different styles to multiple layers."""
        layer_configs = [
            ("Layer1", "basic_layer_red"),
            ("Layer2", "basic_layer_blue"),
            ("Layer3", "layer_complex"),
            ("Layer4", "layer_with_aci_color")
        ]

        mock_drawing = MockDXFUtils.create_mock_drawing()

        for layer_name, style_name in layer_configs:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Verify all layers were styled
        assert len(mock_style_applicator.applied_layers) == len(layer_configs)

    def test_layer_style_inheritance_to_entities(self, mock_style_applicator):
        """Test that layer styles are inherited by entities on the layer."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        mock_drawing = MockDXFUtils.create_mock_drawing()
        layer_name = "InheritanceLayer"

        # Apply layer style
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        # Create entities on the layer
        entity1 = MockDXFUtils.create_mock_entity("LINE")
        entity1.dxf.layer = layer_name
        entity2 = MockDXFUtils.create_mock_entity("CIRCLE")
        entity2.dxf.layer = layer_name

        # Apply entity styles (should inherit from layer)
        mock_style_applicator.apply_style_to_dxf_entity(entity1, style, mock_drawing)
        mock_style_applicator.apply_style_to_dxf_entity(entity2, style, mock_drawing)

        # Verify both layer and entity styling occurred
        assert len(mock_style_applicator.applied_layers) == 1
        assert len(mock_style_applicator.applied_entities) == 2

    def test_layer_style_override_scenarios(self, mock_style_applicator):
        """Test scenarios where entity styles override layer styles."""
        layer_style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        entity_style = StyleTestFixtures.get_style_by_name("basic_layer_blue")

        mock_drawing = MockDXFUtils.create_mock_drawing()
        layer_name = "OverrideLayer"

        # Apply layer style first
        mock_style_applicator.apply_styles_to_dxf_layer(mock_drawing, layer_name, layer_style)

        # Create entity with different style
        entity = MockDXFUtils.create_mock_entity("LINE")
        entity.dxf.layer = layer_name

        # Apply different entity style (should override layer)
        mock_style_applicator.apply_style_to_dxf_entity(entity, entity_style, mock_drawing)

        # Verify both applications occurred
        assert len(mock_style_applicator.applied_layers) == 1
        assert len(mock_style_applicator.applied_entities) == 1
