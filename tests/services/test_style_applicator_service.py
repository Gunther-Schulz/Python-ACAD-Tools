"""Unit tests for StyleApplicatorService.

Tests the refactored StyleApplicatorService that uses IDXFAdapter for DXF operations
instead of direct ezdxf calls (Sub-Task 1.B of REFACTORING_PLAN.MD).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock, ANY
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon

from src.services.style_applicator_service import StyleApplicatorService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.logging_service_interface import ILoggingService
from src.interfaces.config_loader_interface import IConfigLoader
from src.domain.style_models import (
    NamedStyle, LayerStyleProperties, TextStyleProperties, HatchStyleProperties,
    TextAttachmentPoint, DXFLineweight, StyleConfig, AciColorMappingItem
)
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.exceptions import DXFProcessingError
# Attempt to import ezdxf entities for spec if available, otherwise use object
try:
    from ezdxf.entities import DXFGraphic
    from ezdxf.entities.layer import Layer as EzdxfLayer
    EZDXF_AVAILABLE_FOR_SPEC = True
except ImportError:
    DXFGraphic = object
    EzdxfLayer = object
    EZDXF_AVAILABLE_FOR_SPEC = False


class TestStyleApplicatorServiceBasic:
    """Test class for StyleApplicatorService basic functionality."""

    @pytest.fixture
    def mock_logger_service(self):
        """Create mock logger service."""
        mock_service = Mock(spec=ILoggingService)
        mock_logger = MagicMock() # Use MagicMock for easier side_effect configuration
        # Configure the debug method to print its arguments
        mock_logger.debug.side_effect = lambda msg: print(f"MOCK_LOGGER_DEBUG: {msg}")
        mock_logger.info.side_effect = lambda msg: print(f"MOCK_LOGGER_INFO: {msg}")
        mock_logger.warning.side_effect = lambda msg: print(f"MOCK_LOGGER_WARNING: {msg}")
        mock_logger.error.side_effect = lambda msg, exc_info=False: print(f"MOCK_LOGGER_ERROR: {msg}")

        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def mock_config_loader(self):
        """Create mock config loader."""
        mock_loader = Mock(spec=IConfigLoader)
        mock_loader.get_aci_color_mappings.return_value = []
        return mock_loader

    @pytest.fixture
    def mock_dxf_adapter(self):
        """Create mock DXF adapter."""
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        """Create StyleApplicatorService instance with mocked dependencies."""
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    def test_initialization(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        """Test service initialization."""
        service = StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

        assert service._config_loader == mock_config_loader
        assert service._dxf_adapter == mock_dxf_adapter
        assert service._aci_map is None  # Lazy loaded

    def test_resolve_aci_color_string(self, style_applicator_service):
        """Test ACI color resolution with string color."""
        style_applicator_service._aci_map = {"red": 1, "blue": 5}

        result = style_applicator_service._resolve_aci_color("red")
        assert result == 1

    def test_resolve_aci_color_integer(self, style_applicator_service):
        """Test ACI color resolution with integer color."""
        result = style_applicator_service._resolve_aci_color(5)
        assert result == 5

    def test_resolve_aci_color_none(self, style_applicator_service):
        """Test ACI color resolution with None."""
        result = style_applicator_service._resolve_aci_color(None)
        assert result is None

    def test_resolve_aci_color_unknown_string(self, style_applicator_service):
        """Test ACI color resolution with unknown string."""
        style_applicator_service._aci_map = {"red": 1}

        result = style_applicator_service._resolve_aci_color("unknown")
        assert result == 7  # DEFAULT_ACI_COLOR

    def test_get_style_for_layer_style_reference(self, style_applicator_service):
        """Test getting style when layer definition references style by name."""
        style = NamedStyle(layer=LayerStyleProperties(color="red"))
        layer_def = GeomLayerDefinition(name="test_layer", style="my_style")
        style_config = StyleConfig(styles={"my_style": style})

        result = style_applicator_service.get_style_for_layer("test_layer", layer_def, style_config)

        assert result == style

    def test_get_style_for_layer_fallback_to_layer_name(self, style_applicator_service):
        """Test getting style by layer name when no definition style exists."""
        style = NamedStyle(layer=LayerStyleProperties(color="blue"))
        style_config = StyleConfig(styles={"test_layer": style})

        result = style_applicator_service.get_style_for_layer("test_layer", None, style_config)

        assert result == style

    def test_apply_style_to_geodataframe_empty(self, style_applicator_service):
        """Test applying style to empty GeoDataFrame."""
        gdf = gpd.GeoDataFrame()
        style = NamedStyle(layer=LayerStyleProperties(color="red"))

        result = style_applicator_service.apply_style_to_geodataframe(gdf, style, "test_layer")

        assert result.empty

    def test_apply_style_to_geodataframe_layer_properties(self, style_applicator_service):
        """Test applying layer style properties to GeoDataFrame."""
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
        style = NamedStyle(layer=LayerStyleProperties(
            color="red",
            linetype="DASHED",
            lineweight=25  # Valid DXF lineweight
        ))
        style_applicator_service._aci_map = {"red": 1}

        result = style_applicator_service.apply_style_to_geodataframe(gdf, style, "test_layer")

        assert "_style_color_aci" in result.columns
        assert result["_style_color_aci"].iloc[0] == 1
        assert result["_style_linetype"].iloc[0] == "DASHED"
        assert result["_style_lineweight"].iloc[0] == 25

    def test_ensure_dxf_linetype_builtin(self, style_applicator_service):
        """Test ensuring built-in linetypes (should not create)."""
        mock_drawing = Mock()
        mock_adapter = style_applicator_service._dxf_adapter # Get the mock adapter

        # Test built-in linetypes
        for linetype_name in [None, "BYLAYER", "BYBLOCK", "CONTINUOUS", "continuous"]:
            # Correctly create LayerStyleProperties, handling the None case for linetype_name
            layer_props = LayerStyleProperties(linetype=linetype_name) if linetype_name is not None else LayerStyleProperties(linetype=None)
            style_applicator_service._ensure_dxf_linetype(mock_drawing, layer_props)

        # Should not call adapter
        mock_adapter.create_linetype.assert_not_called()

    def test_ensure_dxf_linetype_common(self, style_applicator_service):
        """Test ensuring common predefined linetypes."""
        mock_drawing = Mock()
        mock_adapter = style_applicator_service._dxf_adapter

        layer_props = LayerStyleProperties(linetype="DASHED")
        style_applicator_service._ensure_dxf_linetype(mock_drawing, layer_props)

        # The service looks up predefined patterns/descriptions for some common linetypes
        # For "DASHED", it should use pattern=[1.2, -0.7] and description="Dashed ----"
        mock_adapter.create_linetype.assert_called_once_with(
            doc=mock_drawing,
            ltype_name="DASHED",
            pattern=[1.2, -0.7], # Specific pattern for DASHED
            description="Dashed ----" # Specific description for DASHED
        )

    def test_ensure_dxf_text_style_valid_font(self, style_applicator_service):
        """Test text style creation with valid font."""
        mock_drawing = Mock()
        text_props = TextStyleProperties(font="Arial")

        result = style_applicator_service._ensure_dxf_text_style(mock_drawing, text_props)

        assert result == "Style_Arial"
        style_applicator_service._dxf_adapter.create_text_style.assert_called_once_with(
            doc=mock_drawing,
            style_name="Style_Arial",
            font_name="Arial"
        )

    def test_ensure_dxf_text_style_whitespace_font(self, style_applicator_service):
        """Test text style creation with whitespace-only font name."""
        mock_drawing = Mock()
        text_props = TextStyleProperties(font="   ")  # Only whitespace

        result = style_applicator_service._ensure_dxf_text_style(mock_drawing, text_props)

        # The actual implementation creates a style name from whitespace
        assert result == "Style____"
        style_applicator_service._dxf_adapter.create_text_style.assert_called_once()

    def test_apply_style_to_dxf_entity_adapter_unavailable(self, style_applicator_service):
        """Test applying style when adapter is unavailable."""
        style_applicator_service._dxf_adapter.is_available.return_value = False
        mock_entity = Mock()
        mock_drawing = Mock()
        style = NamedStyle(layer=LayerStyleProperties(color="red"))

        with pytest.raises(DXFProcessingError, match="ezdxf library not available"):
            style_applicator_service.apply_style_to_dxf_entity(mock_entity, style, mock_drawing)

    def test_apply_styles_to_dxf_layer_adapter_unavailable(self, style_applicator_service):
        """Test applying styles to layer when adapter is unavailable."""
        style_applicator_service._dxf_adapter.is_available.return_value = False
        mock_drawing = Mock()
        style = NamedStyle(layer=LayerStyleProperties(color="red"))

        with pytest.raises(DXFProcessingError, match="ezdxf library not available or adapter failed"):
            style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "test_layer", style)

    def test_apply_styles_to_dxf_layer_success(self, style_applicator_service):
        """Test successful application of styles to a layer."""
        mock_drawing = Mock()
        mock_layer_entity = Mock(spec=EzdxfLayer) # Mock an ezdxf Layer object
        # Ensure .dxf attribute exists and is a MagicMock for attribute assignment flexibility
        type(mock_layer_entity).dxf = PropertyMock(return_value=MagicMock())
        mock_layer_entity.dxf.name = "test_layer" # Set a name for logging/lookup

        mock_adapter = style_applicator_service._dxf_adapter
        mock_adapter.get_layer.return_value = mock_layer_entity
        mock_adapter.create_dxf_layer.return_value = None # Not creating new in this path

        style = NamedStyle(layer=LayerStyleProperties(
            color="red",
            linetype="CENTER",
            lineweight=50, # Corrected: Pass integer value for lineweight
            plot=True,
            isOn=True,  # MODIFIED: Attempt using the alias
            frozen=False,
            locked=False
        ))
        style_applicator_service._aci_map = {"red": 1} # Ensure color resolves

        style_applicator_service.apply_styles_to_dxf_layer(mock_drawing, "test_layer", style)

        # Verify adapter calls
        mock_adapter.get_layer.assert_called_with(mock_drawing, "test_layer")

        # Ensure linetype 'CENTER' was attempted to be created (it might exist or be created)
        # The ensure_dxf_linetype method handles the creation logic internally.
        # We check that the set_layer_properties gets the correct linetype string.

        # Check arguments passed to set_layer_properties
        # The method signature in EzdxfAdapter is set_layer_properties(self, doc, layer_name, **kwargs)
        # So the actual call from StyleApplicatorService should be something like:
        # self._dxf_adapter.set_layer_properties(doc=dxf_drawing, layer_name=layer_name, **layer_props_to_set)

        # Find the call to set_layer_properties in all method_calls on the adapter
        set_props_call_args = None
        for method_name, args, kwargs in mock_adapter.method_calls:
            if method_name == 'set_layer_properties':
                set_props_call_args = (args, kwargs)
                break

        assert set_props_call_args is not None, "set_layer_properties was not called on the adapter"

        called_pos_args, called_kwargs = set_props_call_args

        # DEBUG: Print the actual kwargs received by the mock
        # print(f"DEBUG_TEST: called_kwargs in test_apply_styles_to_dxf_layer_success: {called_kwargs}") # TEMP DEBUG REMOVED

        # First two positional arguments for EzdxfAdapter.set_layer_properties are doc and layer_name
        assert called_kwargs.get('doc') == mock_drawing
        assert called_kwargs.get('layer_name') == "test_layer"
        assert called_kwargs.get('color') == 1
        assert called_kwargs.get('linetype') == "CENTER" # Should be CENTER from the style
        assert called_kwargs.get('lineweight') == 50 # Corrected: Assert integer value
        assert called_kwargs.get('plot') is True
        assert called_kwargs.get('on') is True
        assert called_kwargs.get('frozen') is False
        assert called_kwargs.get('locked') is False

    def test_clear_caches(self, style_applicator_service):
        """Test clearing caches."""
        style_applicator_service._aci_map = {"red": 1, "blue": 5}

        style_applicator_service.clear_caches()

        assert style_applicator_service._aci_map is None

    def test_get_cache_info_loaded(self, style_applicator_service):
        """Test getting cache info when caches are loaded."""
        style_applicator_service._aci_map = {"red": 1, "blue": 5}

        result = style_applicator_service.get_cache_info()

        assert result == {
            "aci_map_entries": 2,
            "aci_map_loaded": True
        }


class TestStyleApplicatorServiceGeometryProcessing:
    """Test class for geometry processing in add_geodataframe_to_dxf method."""

    @pytest.fixture
    def mock_logger_service(self):
        """Create mock logger service."""
        mock_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def mock_config_loader(self):
        """Create mock config loader."""
        mock_loader = Mock(spec=IConfigLoader)
        mock_loader.get_aci_color_mappings.return_value = []
        return mock_loader

    @pytest.fixture
    def mock_dxf_adapter(self):
        """Create mock DXF adapter."""
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        """Create StyleApplicatorService instance with mocked dependencies."""
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    @pytest.fixture
    def mock_drawing_and_msp(self):
        """Create mock drawing and modelspace."""
        mock_drawing = Mock()
        mock_msp = Mock()
        mock_drawing.get_modelspace.return_value = mock_msp  # Actual method name
        return mock_drawing, mock_msp

    def test_add_geodataframe_to_dxf_adapter_unavailable(self, style_applicator_service):
        """Test adding GeoDataFrame when adapter is unavailable."""
        style_applicator_service._dxf_adapter.is_available.return_value = False
        mock_drawing = Mock()
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})

        with pytest.raises(DXFProcessingError, match="ezdxf library not available"):
            style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "test_layer")

    def test_add_geodataframe_to_dxf_empty_gdf(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding empty GeoDataFrame."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        gdf = gpd.GeoDataFrame()

        style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "test_layer")

        # Should return early for empty GDF without creating layer
        mock_drawing.get_modelspace.assert_not_called()

    def test_add_geodataframe_to_dxf_point_geometry(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding Point geometry to DXF."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_msp

        gdf = gpd.GeoDataFrame({'geometry': [Point(10, 20)]})
        mock_entity = Mock()
        style_applicator_service._dxf_adapter.add_point.return_value = mock_entity

        style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "test_layer")

        style_applicator_service._dxf_adapter.add_point.assert_called_once_with(
            mock_msp, location=(10.0, 20.0, 0.0), dxfattribs={'layer': 'test_layer'}
        )

    def test_add_geodataframe_to_dxf_polygon_with_hatch_solid(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding Polygon geometry with solid hatch style."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_msp

        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        gdf = gpd.GeoDataFrame({'geometry': [polygon]})

        # Style with solid hatch (no pattern_name)
        # Using a specific ACI color directly for simplicity in assertion
        style = NamedStyle(
            layer=LayerStyleProperties(color=3), # For the boundary polyline
            hatch=HatchStyleProperties(color=1)  # ACI 1 for RED hatch
        )
        # No need to mock _aci_map if we use ACI codes directly in style or expect default

        mock_hatch_entity = Mock(name="MockHatchEntity")
        # The boundary entity will be created by add_lwpolyline
        mock_boundary_entity = Mock(name="MockBoundaryLWPolyline")
        mock_boundary_entity.dxf = MagicMock() # Ensure it has a dxf attribute

        style_applicator_service._dxf_adapter.add_hatch.return_value = mock_hatch_entity
        style_applicator_service._dxf_adapter.add_lwpolyline.return_value = mock_boundary_entity
        # Ensure set_entity_properties is available on the adapter mock for the boundary styling
        style_applicator_service._dxf_adapter.set_entity_properties = Mock(name="SetEntityPropsMock")

        style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "test_layer", style)

        # Verify layer creation/styling (minimal for this test focus)
        # If apply_styles_to_dxf_layer was not mocked, it would call adapter methods for layer
        # For now, assume layer 'test_layer' is handled; focus on hatch and boundary.
        # A more complete test would mock/assert layer calls if apply_styles_to_dxf_layer is not mocked.

        # Boundary polyline added
        style_applicator_service._dxf_adapter.add_lwpolyline.assert_called_once_with(
            mock_msp,
            points=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            close=True,
            dxfattribs={'layer': 'test_layer'}
        )

        # Properties set on the boundary polyline by the internal call to apply_style_to_dxf_entity
        # The style for the boundary comes from NamedStyle.layer
        style_applicator_service._dxf_adapter.set_entity_properties.assert_any_call(
            entity=mock_boundary_entity,
            color=3,          # Color from NamedStyle.layer
            linetype="BYLAYER", # Service default when None in style
            lineweight=-1,    # Service default (LINEWEIGHT_BYLAYER) when None in style
            transparency=None # Service passes None if not in style
        )

        # Hatch entity added and styled
        style_applicator_service._dxf_adapter.add_hatch.assert_called_once_with(
            mock_msp, color=1, dxfattribs={'layer': 'test_layer'} # Hatch color from NamedStyle.hatch
        )
        style_applicator_service._dxf_adapter.set_hatch_solid_fill.assert_called_once_with(
            hatch_entity=mock_hatch_entity, color=1 # Hatch color from NamedStyle.hatch
        )

    def test_add_geodataframe_to_dxf_polygon_with_hatch_pattern(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding Polygon geometry with pattern hatch style."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_msp

        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        gdf = gpd.GeoDataFrame({'geometry': [polygon]})

        style = NamedStyle(
            layer=LayerStyleProperties(color=5), # For the boundary polyline, ACI 5 for BLUE
            hatch=HatchStyleProperties(
                patternName="ANSI31",
                color=3, # ACI 3 for GREEN hatch pattern
                scale=2.0,
                angle=45.0
            )
        )
        # No need to mock _aci_map or _resolve_aci_color if using direct ACI codes or testing default behavior

        mock_hatch_entity = Mock(name="MockHatchEntityForPattern")
        mock_hatch_entity.paths = Mock()
        mock_hatch_entity.paths.add_polyline_path = Mock()

        mock_boundary_entity = Mock(name="MockBoundaryLWPolylineForPattern")
        mock_boundary_entity.dxf = MagicMock() # Ensure it has a dxf attribute for styling

        style_applicator_service._dxf_adapter.add_hatch = Mock(return_value=mock_hatch_entity, name="AddHatchMock")
        style_applicator_service._dxf_adapter.add_hatch_boundary_path = Mock(name="AddBoundaryPathMock")
        style_applicator_service._dxf_adapter.set_hatch_pattern_fill = Mock(name="SetPatternFillMock")
        style_applicator_service._dxf_adapter.add_lwpolyline = Mock(return_value=mock_boundary_entity, name="AddLwpolylineMock")

        # Ensure set_entity_properties is available on the adapter mock for the boundary styling
        style_applicator_service._dxf_adapter.set_entity_properties = Mock(name="SetEntityPropsMockForPattern")

        style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "pattern_test_layer", style)

        # Boundary polyline added
        style_applicator_service._dxf_adapter.add_lwpolyline.assert_called_once_with(
            mock_msp,
            points=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            close=True,
            dxfattribs={'layer': 'pattern_test_layer'}
        )

        # Properties set on the boundary polyline by the internal call to apply_style_to_dxf_entity
        # The style for the boundary comes from NamedStyle.layer
        style_applicator_service._dxf_adapter.set_entity_properties.assert_any_call(
            entity=mock_boundary_entity,
            color=5,          # Color from NamedStyle.layer
            linetype="BYLAYER", # Service default when None in style
            lineweight=-1,    # Service default (LINEWEIGHT_BYLAYER) when None in style
            transparency=None # Service passes None if not in style
        )

        # Hatch entity added and styled for pattern
        # For pattern hatches, color is None in add_hatch call (color is set in set_hatch_pattern_fill)
        style_applicator_service._dxf_adapter.add_hatch.assert_called_once_with(
            mock_msp, color=None, dxfattribs={'layer': 'pattern_test_layer'}
        )
        style_applicator_service._dxf_adapter.add_hatch_boundary_path.assert_any_call(
            mock_hatch_entity, points=[(0.0,0.0), (10.0,0.0), (10.0,10.0), (0.0,10.0), (0.0,0.0)], flags=1
        )
        style_applicator_service._dxf_adapter.set_hatch_pattern_fill.assert_called_once_with(
            hatch_entity=mock_hatch_entity,
            pattern_name="ANSI31",
            color=3, # Color from NamedStyle.hatch
            scale=2.0,
            angle=45.0
        )

    def test_add_geodataframe_to_dxf_multipoint(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding MultiPoint geometry."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        # Ensure the adapter's get_modelspace is configured to return the mock_msp
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_msp

        multipoint = MultiPoint([Point(0, 0), Point(10, 10), Point(20, 20)])
        gdf = gpd.GeoDataFrame({'geometry': [multipoint]})

        mock_entity = Mock()
        style_applicator_service._dxf_adapter.add_point.return_value = mock_entity

        style_applicator_service.add_geodataframe_to_dxf(mock_drawing, gdf, "test_layer")

        # Should create points for each sub-geometry
        assert style_applicator_service._dxf_adapter.add_point.call_count == 3
        style_applicator_service._dxf_adapter.add_point.assert_any_call(
            mock_msp, location=(0.0,0.0,0.0), dxfattribs={'layer': 'test_layer'}
        )
        style_applicator_service._dxf_adapter.add_point.assert_any_call(
            mock_msp, location=(10.0,10.0,0.0), dxfattribs={'layer': 'test_layer'}
        )
        style_applicator_service._dxf_adapter.add_point.assert_any_call(
            mock_msp, location=(20.0,20.0,0.0), dxfattribs={'layer': 'test_layer'}
        )

    def test_add_geodataframe_to_dxf_with_labels(self, style_applicator_service, mock_drawing_and_msp):
        """Test adding Polygon geometry with labels from layer definition."""
        mock_drawing, mock_msp = mock_drawing_and_msp
        style_applicator_service._dxf_adapter.get_modelspace.return_value = mock_msp

        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        gdf = gpd.GeoDataFrame({
            'geometry': [polygon],
            'name': ['Test Polygon Label']
        })
        label_only_style = NamedStyle(
            layer=LayerStyleProperties(color=7),
            text=TextStyleProperties(font="Arial", height=2.5, color=1)
        )
        layer_def = GeomLayerDefinition(name="label_test_layer", labelColumn='name', style="label_style_ref")

        style_applicator_service._dxf_adapter.add_text = Mock(name="AddTextMock")
        style_applicator_service._dxf_adapter.add_mtext = Mock(name="AddMtextMock")
        style_applicator_service._dxf_adapter.create_text_style = Mock(return_value=Mock(name="MockTextStyleEntity"), name="CreateTextStyleMock")

        mock_polygon_boundary_entity = Mock(name="MockBoundaryForLabelTestSimplified")
        mock_polygon_boundary_entity.dxf = MagicMock()
        style_applicator_service._dxf_adapter.add_lwpolyline = Mock(return_value=mock_polygon_boundary_entity, name="AddLwpolylineForLabelSimplified")
        style_applicator_service._dxf_adapter.set_entity_properties = Mock(name="SetEntityPropsForLabelBoundarySimplified")

        # We are now testing the main flow, assuming _get_label_text_for_feature works (tested separately)
        # The mock for _calculate_label_position is to check it gets called when a label *should* be processed.
        # The mock for _add_label_to_dxf is to check it gets called with the results.
        with patch.object(style_applicator_service, '_calculate_label_position', return_value=(5.0, 5.0), name="CalcLabelPosMockPatched") as mock_calc_label_pos, \
             patch.object(style_applicator_service, '_add_label_to_dxf', name="AddLabelToDXFMock") as mock_add_label_method:

            # No more side_effect for calc_pos_side_effect needed for diagnostics
            # mock_calc_label_pos.side_effect = calc_pos_side_effect

            style_applicator_service.add_geodataframe_to_dxf(
                mock_drawing, gdf, "label_test_layer", layer_definition=layer_def, style=label_only_style
            )

            # Verify _calculate_label_position was called for the polygon
            mock_calc_label_pos.assert_called_once_with(ANY, 'Polygon')

            # Verify _add_label_to_dxf was called with expected label text
            mock_add_label_method.assert_called_once()
            pos_args, kw_args = mock_add_label_method.call_args # Get pos_args and kw_args

            # All arguments are passed positionally in the service
            assert pos_args[0] == mock_msp # First actual arg is modelspace
            assert pos_args[1] == 'Test Polygon Label'  # label_text
            assert pos_args[2] == (5.0, 5.0)           # position
            assert pos_args[3] == "label_test_layer"   # layer_name
            assert pos_args[4] == label_only_style     # style
            assert pos_args[5] == mock_drawing         # dxf_drawing
            assert not kw_args                        # No keyword arguments should be passed

        # Verify _ensure_dxf_text_style was called (this happens inside the original _add_label_to_dxf)
        # Since we mocked _add_label_to_dxf, this assertion might no longer be correct if _add_label_to_dxf was fully replaced.
        # If _add_label_to_dxf mock is simple, this should be tested by _add_label_to_dxf's own unit tests.
        # For now, we confirm _add_label_to_dxf itself was called with correct high-level args.
        # Let's comment out the create_text_style assertion as its part of the mocked method now.
        # style_applicator_service._dxf_adapter.create_text_style.assert_called_once_with(
        #     doc=mock_drawing, style_name="Style_Arial", font_name="Arial"
        # )


class TestStyleApplicatorServicePrivateMethods:
    """Test class for private methods of StyleApplicatorService."""

    @pytest.fixture
    def mock_logger_service(self):
        """Create mock logger service."""
        mock_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def mock_config_loader(self):
        """Create mock config loader."""
        mock_loader = Mock(spec=IConfigLoader)
        mock_loader.get_aci_color_mappings.return_value = []
        return mock_loader

    @pytest.fixture
    def mock_dxf_adapter(self):
        """Create mock DXF adapter."""
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        """Create StyleApplicatorService instance with mocked dependencies."""
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    def test_calculate_label_position_point(self, style_applicator_service):
        """Test label position calculation for Point geometry."""
        point_geom = Point(10, 20)

        result = style_applicator_service._calculate_label_position(point_geom, "Point")

        # For points, the implementation adds a small offset to avoid overlap
        assert result == (10.1, 20.1)

    def test_calculate_label_position_linestring(self, style_applicator_service):
        """Test label position calculation for LineString geometry."""
        line_geom = LineString([(0, 0), (10, 10)])

        result = style_applicator_service._calculate_label_position(line_geom, "LineString")

        # Should be at midpoint
        assert result == (5.0, 5.0)

    def test_calculate_label_position_polygon(self, style_applicator_service):
        """Test label position calculation for Polygon geometry."""
        polygon_geom = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])

        result = style_applicator_service._calculate_label_position(polygon_geom, "Polygon")

        # Should use representative_point or centroid
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_calculate_label_position_exception_fallback(self, style_applicator_service):
        """Test label position calculation when all methods fail."""
        # Create a mock geometry that raises exceptions
        mock_geom = Mock()

        # Mock representative_point to fail
        mock_representative_point_method = Mock(side_effect=Exception("Representative point error"))
        type(mock_geom).representative_point = mock_representative_point_method

        # Mock centroid property access to fail
        type(mock_geom).centroid = PropertyMock(side_effect=Exception("Centroid access error"))

        # Mock bounds to provide fallback values
        mock_geom.bounds = (0, 0, 10, 10)  # (minx, miny, maxx, maxy)

        result = style_applicator_service._calculate_label_position(mock_geom, "TestType")

        # Should fallback to bounds center
        assert result == (5.0, 5.0)

    def test_add_label_to_dxf_simple_text(self, style_applicator_service):
        """Test adding simple text label to DXF."""
        mock_msp = Mock()
        mock_drawing = Mock()
        mock_text_entity = Mock()
        style_applicator_service._dxf_adapter.add_text.return_value = mock_text_entity

        style_applicator_service._add_label_to_dxf(
            mock_msp, "Test Label", (10, 20), "test_layer", None, mock_drawing
        )

        style_applicator_service._dxf_adapter.add_text.assert_called_once()
        # Check that the text was passed correctly
        call_args = style_applicator_service._dxf_adapter.add_text.call_args
        assert "Test Label" in str(call_args)

    def test_add_label_to_dxf_mtext_with_newlines(self, style_applicator_service):
        """Test adding MTEXT label with newlines."""
        mock_msp = Mock()
        mock_drawing = Mock()

        style_applicator_service._add_label_to_dxf(
            mock_msp, "Line 1\\nLine 2", (10, 20), "test_layer", None, mock_drawing
        )

        style_applicator_service._dxf_adapter.add_mtext.assert_called_once()

    def test_resolve_attachment_point_valid(self, style_applicator_service):
        """Test resolving valid attachment point."""
        with patch('src.services.style_applicator_service.MTextEntityAlignment') as mock_enum:
            mock_enum.TOP_LEFT = 1
            mock_enum.MIDDLE_CENTER = 5

            result = style_applicator_service._resolve_attachment_point("TOP_LEFT")

            assert result == 1

    def test_mtext_attachment_to_text_align_top_left(self, style_applicator_service):
        """Test MTEXT attachment to text alignment conversion for TOP_LEFT."""
        with patch('src.services.style_applicator_service.MTextEntityAlignment') as mock_enum:
            mock_enum.TOP_LEFT = 1
            result = style_applicator_service._mtext_attachment_to_text_align(mock_enum.TOP_LEFT)

            assert result == (0, 3)  # LEFT, TOP

    def test_mtext_attachment_to_text_align_unknown(self, style_applicator_service):
        """Test MTEXT attachment to text alignment conversion for unknown value."""
        result = style_applicator_service._mtext_attachment_to_text_align(999)  # Unknown

        assert result == (1, 2)  # Default CENTER, MIDDLE

    def test_align_text_entity_to_view_basic(self, style_applicator_service):
        """Test basic text entity alignment (smoke test for complex method)."""
        mock_entity = Mock()
        mock_entity.dxftype.return_value = "TEXT"
        mock_drawing = Mock()
        text_props = TextStyleProperties(attachment_point=TextAttachmentPoint.MIDDLE_CENTER)

        # This method has complex implementation with TODOs, just test it doesn't crash
        style_applicator_service._align_text_entity_to_view(mock_entity, mock_drawing, text_props)

        # The method should complete without error (smoke test)
        assert True


# New Test Class for the _get_label_text_for_feature helper
class TestStyleApplicatorServiceGetLabelTextHelper:

    @pytest.fixture
    def mock_logger_service(self):
        mock_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def mock_config_loader(self):
        mock_loader = Mock(spec=IConfigLoader)
        mock_loader.get_aci_color_mappings.return_value = []
        return mock_loader

    @pytest.fixture
    def mock_dxf_adapter(self):
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_dxf_adapter):
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    # Tests for _get_label_text_for_feature
    def test_get_label_text_from_layer_def_valid(self, style_applicator_service):
        row = pd.Series({'label_col': 'Test Label', 'other_col': 'xyz'})
        layer_def = GeomLayerDefinition(name='test', labelColumn='label_col')
        result = style_applicator_service._get_label_text_for_feature(row, layer_def, None, 'Polygon')
        assert result == 'Test Label'

    def test_get_label_text_from_layer_def_empty_text(self, style_applicator_service):
        row = pd.Series({'label_col': '   ', 'other_col': 'xyz'})
        layer_def = GeomLayerDefinition(name='test', labelColumn='label_col')
        result = style_applicator_service._get_label_text_for_feature(row, layer_def, None, 'Polygon')
        assert result is None

    def test_get_label_text_from_layer_def_col_not_in_row(self, style_applicator_service):
        row = pd.Series({'other_col': 'xyz'})
        layer_def = GeomLayerDefinition(name='test', labelColumn='label_col')
        result = style_applicator_service._get_label_text_for_feature(row, layer_def, None, 'Polygon')
        assert result is None

    def test_get_label_text_layer_def_no_label_col(self, style_applicator_service):
        row = pd.Series({'label_col': 'Test Label'})
        layer_def = GeomLayerDefinition(name='test') # No label_column
        result = style_applicator_service._get_label_text_for_feature(row, layer_def, None, 'Polygon')
        assert result is None

    def test_get_label_text_no_layer_def(self, style_applicator_service):
        row = pd.Series({'label_col': 'Test Label'})
        result = style_applicator_service._get_label_text_for_feature(row, None, None, 'Polygon')
        assert result is None

    # Tests for non-polygon general annotation part of _get_label_text_for_feature
    def test_get_label_text_non_polygon_style_text_common_cols_name(self, style_applicator_service):
        row = pd.Series({'name': 'Point Name', 'id': 'p1'})
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        result = style_applicator_service._get_label_text_for_feature(row, None, style_with_text, 'Point')
        assert result == 'Point Name'

    def test_get_label_text_non_polygon_style_text_common_cols_label(self, style_applicator_service):
        row = pd.Series({'label': 'My Point Label', 'name': 'Point Name'})
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        # 'label' should take precedence over 'name' based on defined order
        result = style_applicator_service._get_label_text_for_feature(row, None, style_with_text, 'Point')
        assert result == 'My Point Label'

    def test_get_label_text_non_polygon_style_text_col_empty(self, style_applicator_service):
        row = pd.Series({'name': '   ', 'id': 'p1'})
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        result = style_applicator_service._get_label_text_for_feature(row, None, style_with_text, 'Point')
        assert result == 'p1'

    def test_get_label_text_non_polygon_no_style_text(self, style_applicator_service):
        row = pd.Series({'name': 'Point Name'})
        # No style.text, so common cols should not be checked by this part of logic
        result = style_applicator_service._get_label_text_for_feature(row, None, None, 'Point')
        assert result is None

    def test_get_label_text_non_polygon_style_text_no_common_cols(self, style_applicator_service):
        row = pd.Series({'other_data': 'some_value'})
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        result = style_applicator_service._get_label_text_for_feature(row, None, style_with_text, 'Point')
        assert result is None # No common columns like 'name', 'label', etc. found

    def test_get_label_text_polygon_ignores_common_cols_via_style_text(self, style_applicator_service):
        # Polygons should primarily use layer_definition.label_column
        # The non-polygon common column search path should not activate for polygons
        row = pd.Series({'name': 'Polygon Name from common col', 'label_col': 'Label from LayerDef'})
        layer_def = GeomLayerDefinition(name='test', labelColumn='label_col')
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial')) # Style.text is present

        result = style_applicator_service._get_label_text_for_feature(row, layer_def, style_with_text, 'Polygon')
        assert result == 'Label from LayerDef' # Should prioritize layer_def for polygons

    def test_get_label_text_from_layer_def_with_non_polygon_fallback_not_triggered(self, style_applicator_service):
        row = pd.Series({'label_col': 'Test Label', 'name': 'Common Name'})
        layer_def = GeomLayerDefinition(name='test', labelColumn='label_col')
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        # Even if style.text exists, if layer_def yields a label, that should be it for a Point.
        result = style_applicator_service._get_label_text_for_feature(row, layer_def, style_with_text, 'Point')
        assert result == 'Test Label'

    def test_get_label_text_non_polygon_style_text_legacy_row_name_attr(self, style_applicator_service):
        # Test the hasattr(row, 'name') fallback for non-polygons
        # Create a mock row that doesn't have 'name' in index but has it as an attribute
        class MockRow:
            def __init__(self, name_attr, other_val):
                self.name = name_attr # direct attribute
                self.other = other_val
                self.index = ['other'] # 'name' not in index
            def __getitem__(self, key):
                if key == 'other': return self.other
                raise KeyError(key)
            def __contains__(self, key):
                 return key in self.index

        row = MockRow(name_attr='Legacy Name Attr', other_val='val')
        style_with_text = NamedStyle(text=TextStyleProperties(font='Arial'))
        result = style_applicator_service._get_label_text_for_feature(row, None, style_with_text, 'Point')
        assert result == 'Legacy Name Attr'


# NEW TEST CLASS
class TestApplyStyleToDXFEntity:
    """Tests for the StyleApplicatorService._apply_style_to_dxf_entity method."""

    # COPIED FIXTURES (similar to TestStyleApplicatorServiceBasic)
    @pytest.fixture
    def mock_logger_service(self) -> Mock:
        mock_service = Mock(spec=ILoggingService)
        mock_logger = MagicMock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def mock_config_loader(self) -> Mock:
        mock_loader = Mock(spec=IConfigLoader)
        mock_loader.get_aci_color_mappings.return_value = [
            AciColorMappingItem(name="red", aciCode=1),     # MODIFIED: Use alias 'aciCode'
            AciColorMappingItem(name="green", aciCode=3),   # MODIFIED: Use alias 'aciCode'
            AciColorMappingItem(name="blue", aciCode=5)    # MODIFIED: Use alias 'aciCode'
        ] # Example mappings, ensure it returns a list of AciColorMappingItem
        return mock_loader

    @pytest.fixture
    def mock_dxf_adapter(self) -> Mock:
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def style_applicator_service(
        self, mock_config_loader: Mock, mock_logger_service: Mock, mock_dxf_adapter: Mock
    ) -> StyleApplicatorService:
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_dxf_adapter)

    @pytest.fixture
    def mock_drawing_and_msp(self) -> tuple[Mock, Mock]: # Simplified mock drawing if adapter provides msp
        """Provides a mock DXF Drawing and a mock Modelspace."""
        mock_drawing = Mock(name="MockDrawing")
        mock_msp = Mock(name="MockModelspace")
        # If tests need adapter.get_modelspace(mock_drawing) to return mock_msp:
        # This would typically be set up in the test or a more specific fixture
        # For now, just returning two mocks.
        return mock_drawing, mock_msp

    @pytest.fixture
    def empty_style_config(self) -> StyleConfig:
        return StyleConfig(styles={}, layer_styles={})
    # END COPIED FIXTURES

    @pytest.fixture
    def mock_lwpolyline_entity(self) -> Mock:
        """Fixture to create a mock LWPOLYLINE DXF entity."""
        entity = Mock(spec=DXFGraphic)
        entity.dxftype.return_value = "LWPOLYLINE"
        entity.dxf = Mock() # Mock the .dxf attribute group
        entity.dxf.handle = "LWPOLY_HANDLE"
        return entity

    def test_apply_common_layer_properties_to_lwpolyline(
        self,
        style_applicator_service: StyleApplicatorService,
        mock_lwpolyline_entity: Mock,
        mock_drawing_and_msp: tuple[Mock, Mock],
        empty_style_config: StyleConfig # Added for clarity, used by service for color resolution
    ):
        """Test applying color, linetype, and lineweight from LayerStyleProperties."""
        mock_drawing, _ = mock_drawing_and_msp
        # Ensure _resolve_aci_color can work; it uses _get_aci_color_map which uses config_loader
        # The mock_config_loader fixture now provides default ACI mappings.
        # style_applicator_service._style_config_cache = empty_style_config # No longer needed to set this directly

        style = NamedStyle(
            layer=LayerStyleProperties(
                color="red",       # ACI color 1
                linetype="DASHED",
                lineweight=30      # e.g., 0.30mm
            )
        )

        # Mock dependent service calls
        style_applicator_service._ensure_dxf_linetype = Mock(name="EnsureLinetypeMock")

        style_applicator_service.apply_style_to_dxf_entity(
            mock_lwpolyline_entity, style, mock_drawing
        )

        # Assertions
        style_applicator_service._ensure_dxf_linetype.assert_called_once_with(
            mock_drawing, style.layer
        )

        expected_common_props = {
            'color': 1,  # "red" resolves to ACI 1 via mock_config_loader
            'linetype': "DASHED",
            'lineweight': 30,
            'transparency': None # Not specified in style
        }

        style_applicator_service._dxf_adapter.set_entity_properties.assert_called_once_with(
            entity=mock_lwpolyline_entity,
            color=expected_common_props['color'],
            linetype=expected_common_props['linetype'],
            lineweight=expected_common_props['lineweight'],
            transparency=expected_common_props['transparency']
        )

    def test_apply_bylayer_linetype_to_lwpolyline(
        self,
        style_applicator_service: StyleApplicatorService,
        mock_lwpolyline_entity: Mock,
        mock_drawing_and_msp: tuple[Mock, Mock]
    ):
        """Test applying BYLAYER linetype, should not call _ensure_dxf_linetype."""
        mock_drawing, _ = mock_drawing_and_msp

        style = NamedStyle(
            layer=LayerStyleProperties(
                color="green",
                linetype="BYLAYER", # Test this specific linetype
                lineweight=50
            )
        )

        style_applicator_service._ensure_dxf_linetype = Mock(name="EnsureLinetypeMock")

        style_applicator_service.apply_style_to_dxf_entity(
            mock_lwpolyline_entity, style, mock_drawing
        )

        style_applicator_service._ensure_dxf_linetype.assert_not_called()

        expected_common_props = {
            'color': 3,  # "green" resolves to ACI 3 via mock_config_loader
            'linetype': "BYLAYER", # Should be passed as is
            'lineweight': 50,
            'transparency': None
        }

        style_applicator_service._dxf_adapter.set_entity_properties.assert_called_once_with(
            entity=mock_lwpolyline_entity,
            color=expected_common_props['color'],
            linetype=expected_common_props['linetype'],
            lineweight=expected_common_props['lineweight'],
            transparency=expected_common_props['transparency']
        )

    @pytest.fixture
    def mock_text_entity(self) -> Mock:
        """Fixture to create a mock TEXT DXF entity."""
        # Use MagicMock directly for more flexibility if spec is causing issues
        entity = MagicMock(name="MockTextEntity")
        entity.dxftype.return_value = "TEXT"

        # Configure the .dxf attribute to be a MagicMock
        dxf_attrs_mock = MagicMock(name="dxf_attributes_mock")
        entity.dxf = dxf_attrs_mock

        dxf_attrs_mock.handle = "TEXT_HANDLE_ON_DXF_MOCK"
        dxf_attrs_mock.style = None

        return entity

    def test_apply_text_properties_to_text_entity(
        self,
        style_applicator_service: StyleApplicatorService,
        mock_text_entity: Mock,
        mock_drawing_and_msp: tuple[Mock, Mock]
    ):
        """Test applying various text properties to a TEXT entity."""
        mock_drawing, _ = mock_drawing_and_msp

        style = NamedStyle(
            layer=LayerStyleProperties(
                color="blue", # Layer color ACI 5
                linetype="CONTINUOUS" # This is a built-in type
            ),
            text=TextStyleProperties(
                font="Arial",
                height=2.5,
                rotation=15.0,
                color="red" # Text-specific color ACI 1, should override layer color
            )
        )

        # Mock dependent service calls
        style_applicator_service._ensure_dxf_text_style = Mock(return_value="Style_Arial_Test")
        style_applicator_service._ensure_dxf_linetype = Mock(name="EnsureLinetypeMock") # Mock it

        style_applicator_service.apply_style_to_dxf_entity(
            mock_text_entity, style, mock_drawing
        )

        # Assertions for text style creation
        style_applicator_service._ensure_dxf_text_style.assert_called_once_with(
            mock_drawing, style.text
        )

        # For "CONTINUOUS" linetype, _ensure_dxf_linetype should NOT be called
        style_applicator_service._ensure_dxf_linetype.assert_not_called()

        # Assertions for common properties (color should be text color, linetype BYLAYER for CONTINUOUS)
        style_applicator_service._dxf_adapter.set_entity_properties.assert_called_once_with(
            entity=mock_text_entity,
            color=1,  # Text color "red" (ACI 1)
            linetype="BYLAYER", # "CONTINUOUS" maps to "BYLAYER" for entity properties
            lineweight=-1, # Default from LayerStyleProperties if not set (BYLAYER)
            transparency=None
        )

        # Assertions for direct .dxf attribute settings for TEXT
        assert mock_text_entity.dxf.style == "Style_Arial_Test"
        assert mock_text_entity.dxf.height == 2.5
        assert mock_text_entity.dxf.rotation == 15.0

    # Add more tests for other style combinations and entity types here

# Make sure class is properly closed if it was the last one
