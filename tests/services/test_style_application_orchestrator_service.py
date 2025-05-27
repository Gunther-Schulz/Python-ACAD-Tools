"""Unit tests for StyleApplicationOrchestratorService."""
import pytest
from unittest.mock import Mock, MagicMock, call, patch, PropertyMock, ANY
import geopandas as gpd
from shapely.geometry import Point

from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, Text, MText, Hatch, Layer as EzdxfLayer
from ezdxf.lldxf.const import BYLAYER, LINEWEIGHT_BYLAYER

from src.services.style_application_orchestrator_service import StyleApplicationOrchestratorService
from src.interfaces.logging_service_interface import ILoggingService
from src.interfaces.config_loader_interface import IConfigLoader
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.domain.style_models import (
    NamedStyle, StyleConfig,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem, DXFLineweight, TextAttachmentPoint
)
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.exceptions import ConfigError, DXFProcessingError

# Attempt to import ezdxf entities for spec if available, otherwise use object
try:
    EZDXF_AVAILABLE_FOR_SPEC = True
except ImportError:
    EZDXF_AVAILABLE_FOR_SPEC = False

# Default ACI color used in service
DEFAULT_ACI_COLOR = 7

@pytest.fixture
def mock_logger_service() -> Mock:
    mock_service = Mock(spec=ILoggingService)
    mock_logger = MagicMock()
    # Optional: Configure side effects for logging methods if specific log messages need to be asserted
    # mock_logger.debug.side_effect = print
    # mock_logger.info.side_effect = print
    # mock_logger.warning.side_effect = print
    # mock_logger.error.side_effect = print
    mock_service.get_logger.return_value = mock_logger
    return mock_service

@pytest.fixture
def mock_config_loader() -> Mock:
    mock_loader = Mock(spec=IConfigLoader)
    # Setup default ACI color mappings
    mock_loader.get_aci_color_mappings.return_value = [
        AciColorMappingItem(name="red", aciCode=1, rgb="#FF0000"),
        AciColorMappingItem(name="green", aciCode=3, rgb="#00FF00"),
        AciColorMappingItem(name="blue", aciCode=5, rgb="#0000FF"),
        AciColorMappingItem(name="custom_yellow", aciCode=50, rgb="#FFFF00"),
    ]
    return mock_loader

@pytest.fixture
def mock_dxf_adapter() -> Mock:
    mock_adapter = Mock(spec=IDXFAdapter)
    mock_adapter.is_available.return_value = True
    mock_adapter.get_modelspace.return_value = MagicMock(name="mock_modelspace")
    mock_adapter.get_layer.return_value = MagicMock(spec=EzdxfLayer if EZDXF_AVAILABLE_FOR_SPEC else object)
    # Mock other methods as needed by the orchestrator
    mock_adapter.set_entity_properties = MagicMock()
    mock_adapter.set_layer_properties = MagicMock()
    mock_adapter.create_dxf_layer = MagicMock()
    mock_adapter.query_entities.return_value = [] # Default to no entities on layer
    mock_adapter.set_hatch_pattern_fill = MagicMock()
    mock_adapter.set_hatch_solid_fill = MagicMock()
    mock_adapter.add_hatch = MagicMock(return_value=MagicMock(spec=Hatch if EZDXF_AVAILABLE_FOR_SPEC else object))
    mock_adapter.add_hatch_boundary_path = MagicMock()
    return mock_adapter

@pytest.fixture
def mock_dxf_resource_manager() -> Mock:
    manager = Mock(spec=IDXFResourceManager)
    manager.ensure_text_style.side_effect = lambda doc, ts_props: ts_props.font if ts_props and ts_props.font else "Standard"
    manager.ensure_linetype.side_effect = lambda doc, ls_props: ls_props.linetype if ls_props and ls_props.linetype else "Continuous"
    return manager

@pytest.fixture
def style_orchestrator(
    mock_logger_service: Mock,
    mock_config_loader: Mock,
    mock_dxf_adapter: Mock,
    mock_dxf_resource_manager: Mock
) -> StyleApplicationOrchestratorService:
    return StyleApplicationOrchestratorService(
        logger_service=mock_logger_service,
        config_loader=mock_config_loader,
        dxf_adapter=mock_dxf_adapter,
        dxf_resource_manager=mock_dxf_resource_manager
    )

class TestStyleApplicationOrchestratorServiceInitialization:
    def test_initialization_and_aci_map_loading(self, style_orchestrator, mock_config_loader, mock_logger_service):
        assert style_orchestrator._logger is not None
        assert style_orchestrator._config_loader == mock_config_loader
        assert style_orchestrator._dxf_adapter is not None
        assert style_orchestrator._dxf_resource_manager is not None
        assert style_orchestrator._aci_map is None # Lazy loaded

        # Trigger ACI map load
        aci_map = style_orchestrator._get_aci_color_map()
        assert len(aci_map) == 4
        assert aci_map["red"] == 1
        mock_config_loader.get_aci_color_mappings.assert_called_once()
        style_orchestrator._logger.info.assert_any_call(f"Loaded ACI color map with 4 entries.")

    def test_aci_map_loading_failure(self, style_orchestrator, mock_config_loader, mock_logger_service):
        mock_config_loader.get_aci_color_mappings.side_effect = ConfigError("Failed to load config")
        aci_map = style_orchestrator._get_aci_color_map()
        assert aci_map == {}
        style_orchestrator._logger.error.assert_any_call("Failed to load ACI color map: Failed to load config. Color name resolution will fail.", exc_info=True)

    def test_dxf_adapter_not_available(self, mock_logger_service, mock_config_loader, mock_dxf_adapter, mock_dxf_resource_manager):
        mock_dxf_adapter.is_available.return_value = False
        service = StyleApplicationOrchestratorService(mock_logger_service, mock_config_loader, mock_dxf_adapter, mock_dxf_resource_manager)
        service._logger.error.assert_called_with("ezdxf library not available via adapter. DXF styling functionality will be severely limited.")

class TestStyleApplicationOrchestratorServiceResolveColor:
    def test_resolve_aci_color_string_known(self, style_orchestrator):
        assert style_orchestrator._resolve_aci_color("blue") == 5

    def test_resolve_aci_color_string_unknown(self, style_orchestrator):
        assert style_orchestrator._resolve_aci_color("unknown_purple") == DEFAULT_ACI_COLOR
        style_orchestrator._logger.warning.assert_called_with(f"ACI color name 'unknown_purple' not found in map. Using default ACI {DEFAULT_ACI_COLOR}.")

    def test_resolve_aci_color_int(self, style_orchestrator):
        assert style_orchestrator._resolve_aci_color(10) == 10

    def test_resolve_aci_color_none(self, style_orchestrator):
        assert style_orchestrator._resolve_aci_color(None) is None

    def test_resolve_aci_color_invalid_type(self, style_orchestrator):
        assert style_orchestrator._resolve_aci_color([1,2,3]) == DEFAULT_ACI_COLOR # type: ignore
        style_orchestrator._logger.warning.assert_called_with(f"Unexpected color value type: <class 'list'>. Value: {[1, 2, 3]}")

class TestStyleApplicationOrchestratorServiceGetStyleForLayer:
    def test_get_style_from_layer_definition_namedstyle(self, style_orchestrator):
        # This test name is now a bit misleading as GeomLayerDefinition.style expects a string.
        # The service logic `isinstance(layer_definition.style, NamedStyle)` is likely unreachable with Pydantic validation.
        # We are testing the string reference path here.
        inline_style_object = NamedStyle(name="inline_style_name", layer=LayerStyleProperties(color="red"))
        layer_def = GeomLayerDefinition(name="test_layer", type="poly", style="inline_style_name") # Pass name as string
        style_config = StyleConfig(styles={"inline_style_name": inline_style_object}) # Provide the style in config
        result = style_orchestrator.get_style_for_layer("test_layer", layer_def, style_config)
        assert result == inline_style_object

    def test_get_style_from_layer_definition_string_ref(self, style_orchestrator):
        referenced_style = NamedStyle(name="global_style", layer=LayerStyleProperties(color="green"))
        layer_def = GeomLayerDefinition(name="test_layer", type="poly", style="global_style") # type: ignore
        style_config = StyleConfig(styles={"global_style": referenced_style})
        result = style_orchestrator.get_style_for_layer("test_layer", layer_def, style_config)
        assert result == referenced_style

    def test_get_style_from_layer_definition_string_ref_not_found(self, style_orchestrator):
        layer_def = GeomLayerDefinition(name="test_layer", type="poly", style="missing_style") # type: ignore
        style_config = StyleConfig(styles={})
        # Should try layer_name next if ref not found, and then None if layer_name not found
        result = style_orchestrator.get_style_for_layer("test_layer", layer_def, style_config)
        assert result is None
        style_orchestrator._logger.warning.assert_any_call("Style 'missing_style' referenced by layer 'test_layer' not found.")

    def test_get_style_by_layer_name_if_no_def_style(self, style_orchestrator):
        layer_name_style = NamedStyle(name="test_layer", layer=LayerStyleProperties(color="blue"))
        layer_def = GeomLayerDefinition(name="test_layer", type="poly", style=None) # type: ignore
        style_config = StyleConfig(styles={"test_layer": layer_name_style})
        result = style_orchestrator.get_style_for_layer("test_layer", layer_def, style_config)
        assert result == layer_name_style

    def test_get_style_no_style_found(self, style_orchestrator):
        layer_def = GeomLayerDefinition(name="test_layer", type="poly", style=None) # type: ignore
        style_config = StyleConfig(styles={})
        result = style_orchestrator.get_style_for_layer("test_layer", layer_def, style_config)
        assert result is None
        style_orchestrator._logger.info.assert_any_call("No specific style for layer 'test_layer'.")

class TestStyleApplicationOrchestratorServiceApplyStyleToGDF:
    def test_apply_style_to_gdf_empty(self, style_orchestrator):
        gdf = gpd.GeoDataFrame()
        style = NamedStyle(name="test_style")
        result_gdf = style_orchestrator.apply_style_to_geodataframe(gdf, style, "test_layer")
        assert result_gdf.empty

    def test_apply_style_to_gdf_layer_props(self, style_orchestrator):
        gdf = gpd.GeoDataFrame({'geometry': [Point(0,0)]})
        style = NamedStyle(name="TestStyle", layer=LayerStyleProperties(color="red", linetype="DASHED", lineweight=25))
        result_gdf = style_orchestrator.apply_style_to_geodataframe(gdf, style, "test_layer")
        assert "_style_color_aci" in result_gdf.columns and result_gdf["_style_color_aci"].iloc[0] == 1
        assert "_style_linetype" in result_gdf.columns and result_gdf["_style_linetype"].iloc[0] == "DASHED"
        assert "_style_lineweight" in result_gdf.columns and result_gdf["_style_lineweight"].iloc[0] == 25

    def test_apply_style_to_gdf_text_props(self, style_orchestrator):
        gdf = gpd.GeoDataFrame({'geometry': [Point(0,0)]})
        style = NamedStyle(name="TestStyle", text=TextStyleProperties(font="Arial", color="green", height=3.5, rotation=45.0))
        result_gdf = style_orchestrator.apply_style_to_geodataframe(gdf, style, "test_layer")
        assert "_style_text_font" in result_gdf.columns and result_gdf["_style_text_font"].iloc[0] == "Arial"
        assert "_style_text_color_aci" in result_gdf.columns and result_gdf["_style_text_color_aci"].iloc[0] == 3
        assert "_style_text_height" in result_gdf.columns and result_gdf["_style_text_height"].iloc[0] == 3.5
        assert "_style_text_rotation" in result_gdf.columns and result_gdf["_style_text_rotation"].iloc[0] == 45.0

class TestStyleApplicationOrchestratorServiceDetermineEntityProps:
    def test_determine_entity_props_layer_only(self, style_orchestrator):
        style = NamedStyle(layer=LayerStyleProperties(color="red", linetype="DASHED", lineweight=25))
        props = style_orchestrator._determine_entity_properties_from_style(style, "LINE")
        assert props["color"] == 1 # red
        assert props["linetype"] == "DASHED"
        assert props["lineweight"] == 25
        assert props["transparency"] is None # Adapter default

    def test_determine_entity_props_defaults_if_style_layer_none(self, style_orchestrator):
        style = NamedStyle(layer=None) # No layer style defined
        props = style_orchestrator._determine_entity_properties_from_style(style, "LINE")
        assert props["color"] == BYLAYER
        assert props["linetype"] == "BYLAYER"
        assert props["lineweight"] == LINEWEIGHT_BYLAYER
        assert props["transparency"] is None # Adapter default

    def test_determine_entity_props_text_override_color(self, style_orchestrator):
        layer_style = LayerStyleProperties(color="red")
        # Try with alias and Enum member
        text_style = TextStyleProperties(color="blue", height=2.5, attachment_point=TextAttachmentPoint.MIDDLE_LEFT)
        style = NamedStyle(layer=layer_style, text=text_style)

        # DIAGNOSTIC ASSERTION (should pass now)
        assert style.text is not None
        assert style.text.attachment_point is not None, "TextStyleProperties.attachment_point is None after instantiation!"
        assert style.text.attachment_point == TextAttachmentPoint.MIDDLE_LEFT, f"Unexpected attachment_point value: {style.text.attachment_point}"

        # Test for TEXT entity type
        props_text = style_orchestrator._determine_entity_properties_from_style(style=style, entity_type="TEXT")
        assert props_text["color"] == 5  # Blue
        text_specific_text = props_text.get("text_specific", {})
        assert text_specific_text['height'] == 2.5
        assert text_specific_text['attachment_point'] == "MIDDLE_LEFT"

        # Test for MTEXT entity type (should be same for these props)
        props_mtext = style_orchestrator._determine_entity_properties_from_style(style=style, entity_type="MTEXT")
        assert props_mtext["color"] == 5  # Blue
        text_specific_mtext = props_mtext.get("text_specific", {})
        assert text_specific_mtext['height'] == 2.5
        assert text_specific_mtext['attachment_point'] == "MIDDLE_LEFT"

    def test_determine_entity_props_hatch(self, style_orchestrator):
        style = NamedStyle(
            layer=LayerStyleProperties(color=7), # Default color, will be overridden by hatch
            hatch=HatchStyleProperties(pattern_name="SOLID", scale=1.0, angle=0, color="custom_yellow")
        )
        props = style_orchestrator._determine_entity_properties_from_style(style, "HATCH")

        assert props["color"] == 50 # ACI for custom_yellow from mock_config_loader

        hatch_specific = props.get("hatch_specific", {})
        assert hatch_specific.get("pattern_name") == "SOLID"
        assert hatch_specific.get("scale") == 1.0
        assert hatch_specific.get("angle") == 0
        # Spacing might be None by default if not set, so check presence or value if applicable
        assert "spacing" not in hatch_specific # Assuming it's not set in this test case


class TestStyleApplicationOrchestratorServiceApplyToDXFEntity:
    @pytest.fixture
    def mock_entity(self) -> Mock:
        entity = MagicMock(spec=DXFGraphic)
        entity.dxftype.return_value = "LINE"
        entity.dxf = MagicMock()
        entity.dxf.handle = "E1B0"
        return entity

    def test_apply_to_dxf_entity_common_props(self, style_orchestrator, mock_dxf_adapter, mock_entity):
        style = NamedStyle(name="common", layer=LayerStyleProperties(color="red", linetype="SOLID"))
        mock_drawing = MagicMock(spec=Drawing)
        style_orchestrator.apply_style_to_dxf_entity(mock_entity, style, mock_drawing)
        mock_dxf_adapter.set_entity_properties.assert_called_once_with(
            entity=mock_entity, color=1, linetype="SOLID", lineweight=LINEWEIGHT_BYLAYER, transparency=None
        )

    def test_apply_to_dxf_text_entity(self, style_orchestrator, mock_dxf_adapter, mock_dxf_resource_manager):
        mock_text_entity = MagicMock(spec=Text)
        mock_text_entity.dxftype.return_value = "TEXT"
        mock_text_entity.dxf = MagicMock()
        mock_text_entity.dxf.handle = "E1B1"

        # Input style definition for the test
        input_text_properties = TextStyleProperties(
            font="Technic",
            height=5.0,
            rotation=90.0, # Test uses 90
            color="green", # Text color (ACI 3)
            align_to_view=False,
            attachment_point=TextAttachmentPoint.TOP_CENTER # Added for completeness
        )
        style_model = NamedStyle(
            name="text_style",
            layer=LayerStyleProperties(color="blue"), # Layer color (ACI 5) - will be overridden by text color
            text=input_text_properties
        )
        mock_drawing = MagicMock(spec=Drawing)

        # Mock what ensure_text_style returns (it's just the font name from current mock fixture)
        # mock_dxf_resource_manager.ensure_text_style.return_value = "Technic" # This is handled by fixture

        style_orchestrator.apply_style_to_dxf_entity(mock_text_entity, style_model, mock_drawing)

        # 1. Assert common properties passed to set_entity_properties
        # Color should be from text (green=3), others from layer defaults if not in text style
        mock_dxf_adapter.set_entity_properties.assert_called_once_with(
            entity=mock_text_entity,
            color=3, # Green from text style
            linetype="BYLAYER", # From default logic as not in LayerStyleProperties or TextStyleProperties
            lineweight=LINEWEIGHT_BYLAYER, # Default
            transparency=None # Default
        )

        # 2. Assert ensure_text_style was called correctly
        # It's called with the original TextStyleProperties model instance
        mock_dxf_resource_manager.ensure_text_style.assert_called_once_with(mock_drawing, input_text_properties)

        # 3. Assert direct .dxf attributes set by _apply_text_entity_specifics
        # The mock for ensure_text_style (from fixture) returns ts_props.font, so "Technic"
        assert mock_text_entity.dxf.style == "Technic"
        assert abs(mock_text_entity.dxf.height - 5.0) < 0.001
        assert abs(mock_text_entity.dxf.rotation - 90.0) < 0.001

        # Check attachment point (assuming MTEXT logic in _apply_text_entity_specifics also applies to TEXT if field exists)
        # The service method _apply_text_entity_specifics currently only sets attachment_point for MText.
        # So for TEXT entity, this attribute might not be set on dxf object even if in resolved_props.
        # For now, we don't assert mock_text_entity.dxf.attachment_point unless service logic is confirmed to set it for TEXT.
        # If it were MTEXT and attachment_point was "TOP_CENTER", the value would be 1.
        # Example if MTEXT: assert mock_text_entity.dxf.attachment_point == MTextEntityAlignment.TOP_CENTER.value

    # More tests for MTEXT, HATCH, _align_text_entity_to_view, etc.

class TestStyleApplicationOrchestratorServiceApplyToDXFLayer:
    @pytest.fixture
    def mock_drawing_with_layer(self, mock_dxf_adapter) -> MagicMock:
        mock_drawing = MagicMock(spec=Drawing)
        mock_layer_obj = MagicMock(spec=EzdxfLayer if EZDXF_AVAILABLE_FOR_SPEC else object)
        mock_dxf_adapter.get_layer.return_value = mock_layer_obj
        return mock_drawing

    def test_apply_to_dxf_layer_existing_layer(self, style_orchestrator, mock_dxf_adapter, mock_dxf_resource_manager, mock_drawing_with_layer):
        """Test applying style to an existing DXF layer."""
        layer_name = "EXISTING_LAYER"
        # Ensure get_layer returns the mock_layer for this name
        mock_dxf_adapter.get_layer.return_value = mock_drawing_with_layer.layers.get(layer_name)

        style = NamedStyle(name="layer_style", layer=LayerStyleProperties(color="custom_yellow", linetype="BORDER", lineweight=30, plot=False))

        style_orchestrator.apply_styles_to_dxf_layer(mock_drawing_with_layer, layer_name, style)

        mock_dxf_adapter.get_layer.assert_called_once_with(mock_drawing_with_layer, layer_name)
        mock_dxf_adapter.create_dxf_layer.assert_not_called()
        mock_dxf_resource_manager.ensure_linetype.assert_called_once_with(mock_drawing_with_layer, style.layer)
        mock_dxf_adapter.set_layer_properties.assert_called_once_with(
            doc=mock_drawing_with_layer,
            layer_name=layer_name,
            color=50,
            linetype="BORDER",
            lineweight=30,
            plot=False,
            # on, frozen, locked will be None if not in style, adapter handles defaults
        )
        # Assuming query_entities returns empty list by default from fixture
        mock_dxf_adapter.query_entities.assert_called_once()

    def test_apply_to_dxf_layer_new_layer(self, style_orchestrator, mock_dxf_adapter, mock_dxf_resource_manager, mock_drawing_with_layer):
        # Simulate get_layer returning None first, then the created layer
        created_layer_mock = MagicMock(spec=EzdxfLayer if EZDXF_AVAILABLE_FOR_SPEC else object)
        mock_dxf_adapter.get_layer.side_effect = [None, created_layer_mock]

        style = NamedStyle(name="new_layer_style", layer=LayerStyleProperties(color="red"))
        layer_name = "NEW_LAYER"

        style_orchestrator.apply_styles_to_dxf_layer(mock_drawing_with_layer, layer_name, style)

        assert mock_dxf_adapter.get_layer.call_count == 2
        mock_dxf_adapter.create_dxf_layer.assert_called_once_with(mock_drawing_with_layer, layer_name)
        mock_dxf_adapter.set_layer_properties.assert_called_once_with(
            doc=mock_drawing_with_layer,
            layer_name=layer_name,
            color=1,
            linetype="BYLAYER", # Default if not in style
            lineweight=LINEWEIGHT_BYLAYER # Default if not in style
        )

    def test_apply_to_dxf_layer_entities_on_layer(self, style_orchestrator, mock_dxf_adapter, mock_drawing_with_layer):
        style = NamedStyle(name="entity_layer_style", layer=LayerStyleProperties(color="green"))
        layer_name = "LAYER_WITH_ENTITIES"

        mock_entity_on_layer1 = MagicMock(spec=DXFGraphic); mock_entity_on_layer1.dxftype.return_value="LINE"
        mock_entity_on_layer2 = MagicMock(spec=DXFGraphic); mock_entity_on_layer2.dxftype.return_value="TEXT"
        mock_dxf_adapter.query_entities.return_value = [mock_entity_on_layer1, mock_entity_on_layer2]

        # Patch apply_style_to_dxf_entity to check it's called
        with patch.object(style_orchestrator, 'apply_style_to_dxf_entity') as mock_apply_entity_style:
            style_orchestrator.apply_styles_to_dxf_layer(mock_drawing_with_layer, layer_name, style)
            assert mock_apply_entity_style.call_count == 2
            mock_apply_entity_style.assert_any_call(mock_entity_on_layer1, style, mock_drawing_with_layer)
            mock_apply_entity_style.assert_any_call(mock_entity_on_layer2, style, mock_drawing_with_layer)

class TestStyleApplicationOrchestratorCacheManagement:
    def test_clear_caches_and_get_cache_info(self, style_orchestrator):
        # Load map first
        style_orchestrator._get_aci_color_map()
        info_before = style_orchestrator.get_cache_info()
        assert info_before["aci_map_entries"] > 0
        assert info_before["aci_map_loaded"] is True

        style_orchestrator.clear_caches()
        info_after = style_orchestrator.get_cache_info()
        assert info_after["aci_map_entries"] == 0
        assert info_after["aci_map_loaded"] is False

        # Check if it loads again
        style_orchestrator._get_aci_color_map()
        info_reloaded = style_orchestrator.get_cache_info()
        assert info_reloaded["aci_map_entries"] > 0
        assert info_reloaded["aci_map_loaded"] is True

# TODO: Add more tests for:
# - _apply_text_entity_specifics (MTEXT attachment point logic, align_to_view interaction)
# - apply_style_to_dxf_entity (HATCH styling path, including different pattern/solid fill scenarios)
# - _apply_hatch_properties (if it remains a public or semi-public creation helper, test its logic)
# - _align_text_entity_to_view (various scenarios, different extrusions)
# - Edge cases for ensure_linetype and ensure_text_style in mocks if their behavior is complex
# - Error handling paths (e.g., adapter raising DXFProcessingError)
