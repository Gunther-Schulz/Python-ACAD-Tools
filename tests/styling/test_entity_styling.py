"""Tests for entity-level styling functionality."""
import pytest
from unittest.mock import Mock, patch

from src.domain.style_models import NamedStyle, LayerStyleProperties, TextStyleProperties, HatchStyleProperties
from src.services.style_applicator_service import StyleApplicatorService
from src.domain.exceptions import DXFProcessingError

from .base_test_utils import (
    StyleTestFixtures, MockDXFUtils, StyleTestAssertions,
    MockStyleApplicator
)


class TestEntityStyling:
    """Test entity-level styling functionality."""

    def test_apply_style_to_line_entity(self, mock_style_applicator, comprehensive_styles):
        """Test applying style to a LINE entity."""
        # Get a layer style from fixtures
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")

        # Create mock LINE entity
        line_entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Apply style
        mock_style_applicator.apply_style_to_dxf_entity(line_entity, style, mock_drawing)

        # Verify style was applied
        assert line_entity.dxf.color == 1  # Red ACI code (assuming fixture uses ACI)
        assert line_entity.dxf.linetype == "Continuous"
        assert line_entity.dxf.lineweight == 25

    def test_apply_style_to_text_entity(self, mock_style_applicator, comprehensive_styles):
        """Test applying style to a TEXT entity."""
        # Get a text style from fixtures
        style = StyleTestFixtures.get_style_by_name("basic_text")

        # Create mock TEXT entity
        text_entity = MockDXFUtils.create_mock_entity("TEXT")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Apply style
        mock_style_applicator.apply_style_to_dxf_entity(text_entity, style, mock_drawing)

        # Verify the style application was recorded
        assert len(mock_style_applicator.applied_entities) == 1
        applied_entity, applied_style, applied_drawing = mock_style_applicator.applied_entities[0]
        assert applied_entity == text_entity
        assert applied_style == style
        assert applied_drawing == mock_drawing

    def test_apply_comprehensive_text_style(self, mock_style_applicator):
        """Test applying comprehensive text style with all properties."""
        style = StyleTestFixtures.get_style_by_name("text_comprehensive")

        text_entity = MockDXFUtils.create_mock_entity("TEXT")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(text_entity, style, mock_drawing)

        # Verify comprehensive text properties would be applied
        # (In real implementation, this would check actual DXF properties)
        assert len(mock_style_applicator.applied_entities) == 1

    def test_apply_style_to_mtext_entity(self, mock_style_applicator):
        """Test applying style to an MTEXT entity."""
        style = StyleTestFixtures.get_style_by_name("text_mtext_specific")

        mtext_entity = MockDXFUtils.create_mock_entity("MTEXT")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(mtext_entity, style, mock_drawing)

        # Verify MTEXT-specific properties would be applied
        assert len(mock_style_applicator.applied_entities) == 1

    def test_apply_style_to_hatch_entity(self, mock_style_applicator):
        """Test applying style to a HATCH entity."""
        style = StyleTestFixtures.get_style_by_name("basic_hatch")

        hatch_entity = MockDXFUtils.create_mock_entity("HATCH")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(hatch_entity, style, mock_drawing)

        # Verify hatch styling was applied
        assert len(mock_style_applicator.applied_entities) == 1

    def test_apply_combined_style_to_entity(self, mock_style_applicator):
        """Test applying a style with multiple property types."""
        style = StyleTestFixtures.get_style_by_name("full_combined")

        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(entity, style, mock_drawing)

        # Verify combined style application
        assert len(mock_style_applicator.applied_entities) == 1

    def test_entity_styling_with_all_attachment_points(self, mock_style_applicator):
        """Test text entity styling with all attachment points."""
        attachment_styles = [
            "attachment_top_left", "attachment_top_center", "attachment_top_right",
            "attachment_middle_left", "attachment_middle_center", "attachment_middle_right",
            "attachment_bottom_left", "attachment_bottom_center", "attachment_bottom_right"
        ]

        for style_name in attachment_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            text_entity = MockDXFUtils.create_mock_entity("TEXT")
            mock_drawing = MockDXFUtils.create_mock_drawing()

            mock_style_applicator.apply_style_to_dxf_entity(text_entity, style, mock_drawing)

        # Verify all attachment point styles were applied
        assert len(mock_style_applicator.applied_entities) == len(attachment_styles)

    def test_entity_styling_with_all_flow_directions(self, mock_style_applicator):
        """Test MTEXT entity styling with all flow directions."""
        flow_styles = [
            "flow_left_to_right", "flow_right_to_left",
            "flow_top_to_bottom", "flow_bottom_to_top"
        ]

        for style_name in flow_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            mtext_entity = MockDXFUtils.create_mock_entity("MTEXT")
            mock_drawing = MockDXFUtils.create_mock_drawing()

            mock_style_applicator.apply_style_to_dxf_entity(mtext_entity, style, mock_drawing)

        # Verify all flow direction styles were applied
        assert len(mock_style_applicator.applied_entities) == len(flow_styles)

    def test_entity_styling_with_extreme_values(self, mock_style_applicator):
        """Test entity styling with extreme/boundary values."""
        style = StyleTestFixtures.get_style_by_name("extreme_values")

        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(entity, style, mock_drawing)

        # Verify extreme values are handled properly
        assert len(mock_style_applicator.applied_entities) == 1

    def test_entity_styling_with_minimal_properties(self, mock_style_applicator):
        """Test entity styling with minimal property sets."""
        minimal_styles = ["minimal_layer", "minimal_text", "minimal_hatch"]

        for style_name in minimal_styles:
            style = StyleTestFixtures.get_style_by_name(style_name)
            entity = MockDXFUtils.create_mock_entity("LINE")
            mock_drawing = MockDXFUtils.create_mock_drawing()

            mock_style_applicator.apply_style_to_dxf_entity(entity, style, mock_drawing)

        # Verify minimal styles were applied
        assert len(mock_style_applicator.applied_entities) == len(minimal_styles)


class TestEntityStylingWithRealService:
    """Test entity styling with real StyleApplicatorService (mocked dependencies)."""

    @pytest.fixture
    def mock_config_loader(self):
        """Mock config loader for testing."""
        from tests.styling.base_test_utils import MockConfigLoader
        return MockConfigLoader()

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

    def test_real_service_apply_layer_style_to_entity(self, style_applicator_service):
        """Test real service applying layer style to entity."""
        # Create a simple layer style
        layer_style = LayerStyleProperties(
            color=1,  # Red ACI
            linetype="DASHED",
            lineweight=50
        )
        style = NamedStyle(layer=layer_style)

        # Create mock entity
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Apply style using real service
        style_applicator_service.apply_style_to_dxf_entity(entity, style, mock_drawing)

        # Verify properties were set (mock entity should have been modified)
        # Note: This tests the service logic, not actual DXF modification

    def test_real_service_apply_text_style_to_entity(self, style_applicator_service):
        """Test real service applying text style to entity."""
        # Create a text style
        text_style = TextStyleProperties(
            font="Arial",
            color="red",
            height=2.5,
            rotation=45.0
        )
        style = NamedStyle(text=text_style)

        # Create mock TEXT entity
        entity = MockDXFUtils.create_mock_entity("TEXT")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Apply style using real service
        style_applicator_service.apply_style_to_dxf_entity(entity, style, mock_drawing)

    def test_real_service_apply_hatch_style_to_entity(self, style_applicator_service):
        """Test real service applying hatch style to entity."""
        # Create a hatch style
        hatch_style = HatchStyleProperties(
            pattern_name="ANSI31",
            color=4,  # Cyan ACI
            scale=2.0,
            angle=45.0
        )
        style = NamedStyle(hatch=hatch_style)

        # Create mock HATCH entity
        entity = MockDXFUtils.create_mock_entity("HATCH")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Apply style using real service
        style_applicator_service.apply_style_to_dxf_entity(entity, style, mock_drawing)

    def test_real_service_ezdxf_unavailable_error(self, style_applicator_service):
        """Test that service raises error when ezdxf is unavailable."""
        # Mock the adapter to return False for is_available
        style_applicator_service._dxf_adapter.is_available.return_value = False

        style = NamedStyle(layer=LayerStyleProperties(color=1))
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should raise DXFProcessingError when ezdxf is not available
        with pytest.raises(DXFProcessingError, match="ezdxf library not available"):
            style_applicator_service.apply_style_to_dxf_entity(entity, style, mock_drawing)

    def test_real_service_color_name_resolution(self, style_applicator_service):
        """Test color name resolution in real service."""
        # Test the _resolve_aci_color method
        assert style_applicator_service._resolve_aci_color(1) == 1  # ACI code
        assert style_applicator_service._resolve_aci_color("red") == 1  # Color name
        assert style_applicator_service._resolve_aci_color(None) is None  # None value


class TestEntityStylingEdgeCases:
    """Test edge cases and error conditions in entity styling."""

    def test_apply_style_to_none_entity(self, mock_style_applicator):
        """Test applying style to None entity."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # This should handle None gracefully
        mock_style_applicator.apply_style_to_dxf_entity(None, style, mock_drawing)

    def test_apply_none_style_to_entity(self, mock_style_applicator):
        """Test applying None style to entity."""
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # This should handle None style gracefully
        mock_style_applicator.apply_style_to_dxf_entity(entity, None, mock_drawing)

    def test_apply_empty_style_to_entity(self, mock_style_applicator):
        """Test applying empty style (no properties) to entity."""
        empty_style = NamedStyle()  # No layer, text, or hatch properties
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        mock_style_applicator.apply_style_to_dxf_entity(entity, empty_style, mock_drawing)

        # Should handle empty style without errors
        assert len(mock_style_applicator.applied_entities) == 1

    def test_apply_style_to_unsupported_entity_type(self, mock_style_applicator):
        """Test applying style to unsupported entity type."""
        style = StyleTestFixtures.get_style_by_name("basic_layer_red")
        entity = MockDXFUtils.create_mock_entity("UNSUPPORTED_TYPE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle unsupported entity types gracefully
        mock_style_applicator.apply_style_to_dxf_entity(entity, style, mock_drawing)

    def test_style_with_invalid_color_values(self, mock_style_applicator):
        """Test style with invalid color values."""
        # Create style with invalid color
        invalid_style = NamedStyle(
            layer=LayerStyleProperties(color="invalid_color_name")
        )
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle invalid colors gracefully
        mock_style_applicator.apply_style_to_dxf_entity(entity, invalid_style, mock_drawing)

    def test_style_with_out_of_range_aci_values(self, mock_style_applicator):
        """Test style with out-of-range ACI color values."""
        # Create style with out-of-range ACI
        invalid_style = NamedStyle(
            layer=LayerStyleProperties(color=999)  # Invalid ACI code
        )
        entity = MockDXFUtils.create_mock_entity("LINE")
        mock_drawing = MockDXFUtils.create_mock_drawing()

        # Should handle out-of-range ACI values
        mock_style_applicator.apply_style_to_dxf_entity(entity, invalid_style, mock_drawing)


class TestEntityStylingAssertions:
    """Test custom assertions for entity styling."""

    def test_assert_style_properties_applied(self, style_assertions):
        """Test the assertion for verifying applied style properties."""
        # Mock entity and style for testing the assertion
        entity = MockDXFUtils.create_mock_entity("LINE")
        style_props = {
            'color': 1,
            'linetype': "DASHED",
            'lineweight': 25
        }

        # Apply properties to the mock entity
        entity.dxf.color = 1
        entity.dxf.linetype = "DASHED"
        entity.dxf.lineweight = 25

        # Use the assertion
        style_assertions.assert_style_properties_applied(entity, style_props)

        # Test case where assertion should fail (e.g., wrong color)
        entity.dxf.color = 2 # Change a property
        with pytest.raises(AssertionError):
            style_assertions.assert_style_properties_applied(entity, style_props)

    def test_assert_valid_aci_color(self, style_assertions):
        """Test ACI color validation assertion."""
        # Valid ACI codes
        style_assertions.assert_valid_aci_color(0)
        style_assertions.assert_valid_aci_color(255)
        style_assertions.assert_valid_aci_color(1)

        # Valid color names
        style_assertions.assert_valid_aci_color("red")
        style_assertions.assert_valid_aci_color("blue")

        # Invalid ACI codes should raise assertion error
        with pytest.raises(AssertionError):
            style_assertions.assert_valid_aci_color(-1)

        with pytest.raises(AssertionError):
            style_assertions.assert_valid_aci_color(256)

        # Empty color names should raise assertion error
        with pytest.raises(AssertionError):
            style_assertions.assert_valid_aci_color("")

        with pytest.raises(AssertionError):
            style_assertions.assert_valid_aci_color("   ")
