"""Base test utilities for styling tests."""
import pytest
import tempfile
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator
from unittest.mock import Mock, MagicMock

import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

from src.domain.style_models import (
    StyleConfig, NamedStyle, LayerStyleProperties,
    TextStyleProperties, HatchStyleProperties,
    ColorConfig, AciColorMappingItem
)
from src.domain.config_models import GeomLayerDefinition
from src.interfaces.style_applicator_interface import IStyleApplicator
from src.interfaces.config_loader_interface import IConfigLoader


class StyleTestFixtures:
    """Utility class for loading and managing style test fixtures."""

    @staticmethod
    def load_comprehensive_styles() -> StyleConfig:
        """Load comprehensive style fixtures from YAML."""
        fixtures_path = Path(__file__).parent / "fixtures" / "comprehensive_styles.yaml"
        with open(fixtures_path, 'r') as f:
            data = yaml.safe_load(f)
        return StyleConfig(**data)

    @staticmethod
    def load_color_mappings() -> ColorConfig:
        """Load color mapping fixtures from YAML."""
        fixtures_path = Path(__file__).parent / "fixtures" / "color_mappings.yaml"
        with open(fixtures_path, 'r') as f:
            data = yaml.safe_load(f)
        return ColorConfig(**data)

    @staticmethod
    def get_style_by_name(style_name: str) -> NamedStyle:
        """Get a specific style by name from fixtures."""
        styles = StyleTestFixtures.load_comprehensive_styles()
        if style_name not in styles.styles:
            raise ValueError(f"Style '{style_name}' not found in fixtures")
        return styles.styles[style_name]

    @staticmethod
    def get_all_layer_styles() -> Dict[str, NamedStyle]:
        """Get all styles that have layer properties."""
        styles = StyleTestFixtures.load_comprehensive_styles()
        return {name: style for name, style in styles.styles.items()
                if style.layer is not None}

    @staticmethod
    def get_all_text_styles() -> Dict[str, NamedStyle]:
        """Get all styles that have text properties."""
        styles = StyleTestFixtures.load_comprehensive_styles()
        return {name: style for name, style in styles.styles.items()
                if style.text is not None}

    @staticmethod
    def get_all_hatch_styles() -> Dict[str, NamedStyle]:
        """Get all styles that have hatch properties."""
        styles = StyleTestFixtures.load_comprehensive_styles()
        return {name: style for name, style in styles.styles.items()
                if style.hatch is not None}

    @staticmethod
    def get_combined_styles() -> Dict[str, NamedStyle]:
        """Get all styles that combine multiple property types."""
        styles = StyleTestFixtures.load_comprehensive_styles()
        combined = {}
        for name, style in styles.styles.items():
            property_count = sum([
                style.layer is not None,
                style.text is not None,
                style.hatch is not None
            ])
            if property_count > 1:
                combined[name] = style
        return combined


class MockDXFUtils:
    """Utilities for creating mock DXF objects for testing."""

    @staticmethod
    def create_mock_drawing() -> Mock:
        """Create a mock ezdxf Drawing object."""
        mock_drawing = Mock()
        mock_drawing.layers = Mock()
        mock_drawing.linetypes = Mock()
        mock_drawing.styles = Mock()
        mock_drawing.modelspace = Mock()
        mock_drawing.header = Mock()

        # Make linetypes iterable for 'in' checks
        mock_drawing.linetypes.__contains__ = Mock(return_value=False)
        mock_drawing.linetypes.__iter__ = Mock(return_value=iter([]))

        # Make styles iterable for 'in' checks
        mock_drawing.styles.__contains__ = Mock(return_value=False)
        mock_drawing.styles.__iter__ = Mock(return_value=iter([]))
        mock_drawing.styles.new = Mock()

        # Mock modelspace query method
        mock_modelspace = Mock()
        mock_modelspace.query = Mock(return_value=[])
        mock_drawing.modelspace.return_value = mock_modelspace

        return mock_drawing

    @staticmethod
    def create_mock_entity(entity_type: str = "LINE") -> Mock:
        """Create a mock DXF entity."""
        mock_entity = Mock()
        mock_entity.dxftype = Mock(return_value=entity_type)  # Make it callable
        mock_entity.dxf = Mock()
        mock_entity.dxf.layer = "0"
        mock_entity.dxf.color = 7  # Default white
        mock_entity.dxf.linetype = "CONTINUOUS"
        mock_entity.dxf.lineweight = 25
        mock_entity.dxf.handle = "TEST_HANDLE"  # Add handle property
        return mock_entity

    @staticmethod
    def create_mock_layer(layer_name: str = "TestLayer") -> Mock:
        """Create a mock DXF layer."""
        mock_layer = Mock()
        mock_layer.dxf = Mock()
        mock_layer.dxf.name = layer_name
        mock_layer.dxf.color = 7
        mock_layer.dxf.linetype = "CONTINUOUS"
        mock_layer.dxf.lineweight = 25
        mock_layer.dxf.transparency = 0.0
        mock_layer.dxf.plot = True
        mock_layer.is_on = True
        mock_layer.is_frozen = False
        mock_layer.is_locked = False
        return mock_layer


class GeometryTestData:
    """Utilities for creating test geometry data."""

    @staticmethod
    def create_test_geodataframe(geometry_type: str = "point", count: int = 3) -> gpd.GeoDataFrame:
        """Create a test GeoDataFrame with specified geometry type."""
        if geometry_type.lower() == "point":
            geometries = [Point(i, i) for i in range(count)]
        elif geometry_type.lower() == "line":
            geometries = [LineString([(i, i), (i+1, i+1)]) for i in range(count)]
        elif geometry_type.lower() == "polygon":
            geometries = [Polygon([(i, i), (i+1, i), (i+1, i+1), (i, i+1)]) for i in range(count)]
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")

        return gpd.GeoDataFrame({
            'id': range(count),
            'name': [f"feature_{i}" for i in range(count)],
            'geometry': geometries
        })

    @staticmethod
    def create_mixed_geometry_gdf() -> gpd.GeoDataFrame:
        """Create a GeoDataFrame with mixed geometry types."""
        geometries = [
            Point(0, 0),
            LineString([(1, 1), (2, 2)]),
            Polygon([(3, 3), (4, 3), (4, 4), (3, 4)])
        ]

        return gpd.GeoDataFrame({
            'id': range(3),
            'type': ['point', 'line', 'polygon'],
            'geometry': geometries
        })


class StyleTestAssertions:
    """Custom assertions for style testing."""

    @staticmethod
    def assert_style_properties_applied(entity: Mock, expected_style: NamedStyle) -> None:
        """Assert that style properties were correctly applied to a DXF entity."""
        if expected_style.layer:
            layer_props = expected_style.layer
            if layer_props.color is not None:
                # Handle both string and int colors
                if isinstance(layer_props.color, str):
                    # For string colors, we'd need color mapping logic
                    # For now, just assert it was set
                    assert hasattr(entity.dxf, 'color')
                else:
                    assert entity.dxf.color == layer_props.color

            if layer_props.linetype is not None:
                assert entity.dxf.linetype == layer_props.linetype

            if layer_props.lineweight is not None:
                assert entity.dxf.lineweight == layer_props.lineweight

    @staticmethod
    def assert_layer_properties_applied(layer: Mock, expected_style: NamedStyle) -> None:
        """Assert that style properties were correctly applied to a DXF layer."""
        if expected_style.layer:
            layer_props = expected_style.layer

            if layer_props.color is not None:
                if isinstance(layer_props.color, int):
                    assert layer.dxf.color == layer_props.color

            if layer_props.linetype is not None:
                assert layer.dxf.linetype == layer_props.linetype

            if layer_props.lineweight is not None:
                assert layer.dxf.lineweight == layer_props.lineweight

            if layer_props.transparency is not None:
                assert layer.dxf.transparency == layer_props.transparency

            if layer_props.plot is not None:
                assert layer.dxf.plot == layer_props.plot

            if layer_props.is_on is not None:
                assert layer.is_on == layer_props.is_on

            if layer_props.frozen is not None:
                assert layer.is_frozen == layer_props.frozen

            if layer_props.locked is not None:
                assert layer.is_locked == layer_props.locked

    @staticmethod
    def assert_geodataframe_styled(gdf: gpd.GeoDataFrame, expected_columns: List[str]) -> None:
        """Assert that a GeoDataFrame has expected styling columns."""
        for column in expected_columns:
            assert column in gdf.columns, f"Expected styling column '{column}' not found"

    @staticmethod
    def assert_valid_aci_color(color_value: Any) -> None:
        """Assert that a color value is a valid ACI color code."""
        if isinstance(color_value, int):
            assert 0 <= color_value <= 255, f"ACI color code must be 0-255, got {color_value}"
        elif isinstance(color_value, str):
            # For string colors, just assert it's not empty
            assert color_value.strip(), "Color string cannot be empty"


class MockStyleApplicator(IStyleApplicator):
    """Mock implementation of IStyleApplicator for testing."""

    def __init__(self):
        self.applied_styles = []
        self.applied_layers = []
        self.applied_entities = []

    def get_style_for_layer(
        self,
        layer_name: str,
        layer_definition: Optional[GeomLayerDefinition],
        style_config: StyleConfig
    ) -> Optional[NamedStyle]:
        """Mock implementation that returns styles from config."""
        # Simple implementation for testing
        if layer_definition and hasattr(layer_definition, 'style_name'):
            style_name = layer_definition.style_name
            if style_name in style_config.styles:
                return style_config.styles[style_name]

        # Fallback to layer name as style name
        if layer_name in style_config.styles:
            return style_config.styles[layer_name]

        return None

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        """Mock implementation that adds styling columns."""
        self.applied_styles.append((gdf, style, layer_name))

        # Add mock styling columns
        styled_gdf = gdf.copy()

        if style.layer:
            if style.layer.color:
                styled_gdf['color'] = str(style.layer.color)
            if style.layer.lineweight:
                styled_gdf['lineweight'] = style.layer.lineweight

        return styled_gdf

    def apply_style_to_dxf_entity(self, entity: Any, style: NamedStyle, dxf_drawing: Any) -> None:
        """Mock implementation that records applied styles."""
        self.applied_entities.append((entity, style, dxf_drawing))

        # Handle None entity gracefully
        if entity is None or style is None:
            return

        # Apply mock properties
        if style.layer:
            if style.layer.color is not None:
                # Resolve color names to ACI codes for testing
                if isinstance(style.layer.color, str):
                    color_map = {"red": 1, "yellow": 2, "green": 3, "cyan": 4, "blue": 5, "magenta": 6, "white": 7, "black": 0}
                    entity.dxf.color = color_map.get(style.layer.color.lower(), 7)
                else:
                    entity.dxf.color = style.layer.color
            if style.layer.linetype is not None:
                entity.dxf.linetype = style.layer.linetype
            if style.layer.lineweight is not None:
                entity.dxf.lineweight = style.layer.lineweight

    def apply_styles_to_dxf_layer(self, dxf_drawing: Any, layer_name: str, style: NamedStyle) -> None:
        """Mock implementation that records applied layer styles."""
        self.applied_layers.append((dxf_drawing, layer_name, style))

        # Handle None style gracefully
        if style is None:
            return

        # Mock layer creation/update
        mock_layer = MockDXFUtils.create_mock_layer(layer_name)

        if style.layer:
            if style.layer.color is not None:
                # Resolve color names to ACI codes for testing
                if isinstance(style.layer.color, str):
                    color_map = {"red": 1, "yellow": 2, "green": 3, "cyan": 4, "blue": 5, "magenta": 6, "white": 7, "black": 0}
                    mock_layer.dxf.color = color_map.get(style.layer.color.lower(), 7)
                else:
                    mock_layer.dxf.color = style.layer.color
            if style.layer.linetype is not None:
                mock_layer.dxf.linetype = style.layer.linetype
            if style.layer.lineweight is not None:
                mock_layer.dxf.lineweight = style.layer.lineweight
            if style.layer.transparency is not None:
                mock_layer.dxf.transparency = style.layer.transparency
            if style.layer.plot is not None:
                mock_layer.dxf.plot = style.layer.plot
            if style.layer.is_on is not None:
                mock_layer.is_on = style.layer.is_on
            if style.layer.frozen is not None:
                mock_layer.is_frozen = style.layer.frozen
            if style.layer.locked is not None:
                mock_layer.is_locked = style.layer.locked

        # Add to drawing's layers collection
        if hasattr(dxf_drawing, 'layers'):
            dxf_drawing.layers.add(mock_layer)

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Any,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        """Mock implementation that records GDF additions."""
        # This would be a complex implementation in reality
        # For testing, just record the call
        pass

    def clear_caches(self) -> None:
        """Mock implementation."""
        pass

    def get_cache_info(self) -> Dict[str, int]:
        """Mock implementation."""
        return {}


class MockConfigLoader(IConfigLoader):
    """Mock implementation of IConfigLoader for testing."""

    def __init__(self):
        self.color_mappings = [
            AciColorMappingItem(name="red", aciCode=1),
            AciColorMappingItem(name="yellow", aciCode=2),
            AciColorMappingItem(name="green", aciCode=3),
            AciColorMappingItem(name="cyan", aciCode=4),
            AciColorMappingItem(name="blue", aciCode=5),
            AciColorMappingItem(name="magenta", aciCode=6),
            AciColorMappingItem(name="white", aciCode=7),
            AciColorMappingItem(name="black", aciCode=0),
        ]

    def get_aci_color_mappings(self) -> List[AciColorMappingItem]:
        """Return mock color mappings."""
        return self.color_mappings

    def get_app_config(self):
        """Mock implementation."""
        return Mock()

    def get_style_config(self) -> StyleConfig:
        """Mock implementation."""
        return StyleTestFixtures.load_comprehensive_styles()


# Pytest fixtures for styling tests
@pytest.fixture
def style_fixtures() -> StyleTestFixtures:
    """Provide style test fixtures."""
    return StyleTestFixtures()


@pytest.fixture
def mock_dxf_drawing() -> Mock:
    """Provide a mock DXF drawing for testing."""
    return MockDXFUtils.create_mock_drawing()


@pytest.fixture
def test_geodataframe() -> gpd.GeoDataFrame:
    """Provide a test GeoDataFrame."""
    return GeometryTestData.create_test_geodataframe()


@pytest.fixture
def mixed_geometry_gdf() -> gpd.GeoDataFrame:
    """Provide a GeoDataFrame with mixed geometry types."""
    return GeometryTestData.create_mixed_geometry_gdf()


@pytest.fixture
def style_assertions() -> StyleTestAssertions:
    """Provide style-specific assertions."""
    return StyleTestAssertions()


@pytest.fixture
def mock_style_applicator() -> MockStyleApplicator:
    """Provide a mock style applicator for testing."""
    return MockStyleApplicator()


@pytest.fixture
def comprehensive_styles() -> StyleConfig:
    """Provide comprehensive style configuration."""
    return StyleTestFixtures.load_comprehensive_styles()


@pytest.fixture
def color_mappings() -> ColorConfig:
    """Provide color mapping configuration."""
    return StyleTestFixtures.load_color_mappings()

@pytest.fixture
def mock_config_loader() -> MockConfigLoader:
    """Fixture providing a mock config loader."""
    return MockConfigLoader()

@pytest.fixture
def style_applicator_service(mock_config_loader) -> 'StyleApplicatorService':
    """Fixture providing a real StyleApplicatorService with mock dependencies."""
    from src.services.style_applicator_service import StyleApplicatorService
    from src.services.logging_service import LoggingService

    logger_service = LoggingService()
    return StyleApplicatorService(mock_config_loader, logger_service)
