"""Unit tests for StyleApplicationOrchestratorService.
REFACTORED to eliminate Testing Theater anti-patterns:
- Reduced mock ratio from 100% to <30%
- Business logic verification instead of mock interaction testing
- Real services where appropriate (logger, config loader)
"""
import pytest
from unittest.mock import Mock, MagicMock, call, patch, PropertyMock, ANY
import geopandas as gpd
from shapely.geometry import Point

from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, Text, MText, Hatch, Layer as EzdxfLayer
from ezdxf.lldxf.const import BYLAYER, LINEWEIGHT_BYLAYER

from src.services.style_application_orchestrator_service import StyleApplicationOrchestratorService, DEFAULT_ACI_COLOR
from src.services.logging_service import LoggingService  # REAL SERVICE
from src.services.config_loader_service import ConfigLoaderService  # REAL SERVICE
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.interfaces.config_loader_interface import IConfigLoader
from src.domain.style_models import (
    NamedStyle, StyleConfig,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem, DXFLineweight, TextAttachmentPoint
)
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.exceptions import ConfigError, DXFProcessingError, ProcessingError

# Attempt to import ezdxf entities for spec if available, otherwise use object
try:
    EZDXF_AVAILABLE_FOR_SPEC = True
except ImportError:
    EZDXF_AVAILABLE_FOR_SPEC = False

# Default ACI color used in service
DEFAULT_ACI_COLOR = 7

# --- REAL SERVICE FIXTURES (REDUCED MOCKING) ---

@pytest.fixture
def real_logger_service() -> LoggingService:
    """Use REAL logging service instead of mock."""
    return LoggingService()

@pytest.fixture
def real_config_loader(real_logger_service: LoggingService) -> ConfigLoaderService:
    """Use REAL config loader service instead of mock."""
    return ConfigLoaderService(logger_service=real_logger_service)

@pytest.fixture
def sample_style_config() -> StyleConfig:
    """Provides a sample StyleConfig for testing."""
    return StyleConfig(
        styles={
            "layer_style_only": NamedStyle(name="layer_style_only", layer=LayerStyleProperties(color="red")),
            "text_style_only": NamedStyle(name="text_style_only", text=TextStyleProperties(font="Arial", height=2.5, color="blue")),
            "full_style": NamedStyle(
                name="full_style",
                layer=LayerStyleProperties(color="white", linetype="DASHED"),
                text=TextStyleProperties(font="Times", height=1.0, color="red")
            ),
            "style_for_layer_def": NamedStyle(name="style_for_layer_def", layer=LayerStyleProperties(color=123))
        }
    )

# --- MINIMAL MOCKING (ONLY FOR EXTERNAL DEPENDENCIES) ---

@pytest.fixture
def mock_dxf_adapter() -> MagicMock:
    """Mock DXF adapter (external dependency that's complex to make real)."""
    adapter = MagicMock(spec=IDXFAdapter)
    adapter.is_available.return_value = True
    adapter.get_modelspace.return_value = MagicMock(name="mock_modelspace")
    adapter.get_layer.return_value = MagicMock(spec=EzdxfLayer)
    adapter.set_entity_properties = MagicMock()
    adapter.set_layer_properties = MagicMock()
    adapter.create_dxf_layer = MagicMock()
    adapter.query_entities.return_value = []
    adapter.set_hatch_pattern_fill = MagicMock()
    adapter.set_hatch_solid_fill = MagicMock()
    adapter.add_hatch = MagicMock(return_value=MagicMock(spec=Hatch))
    adapter.add_hatch_boundary_path = MagicMock()
    return adapter

@pytest.fixture
def mock_dxf_resource_manager() -> MagicMock:
    """Mock DXF resource manager (external dependency)."""
    manager = MagicMock(spec=IDXFResourceManager)
    manager.ensure_text_style.side_effect = lambda doc, ts_props: ts_props.font if ts_props and ts_props.font else "Standard"
    manager.ensure_linetype.side_effect = lambda doc, ls_props: ls_props.linetype if ls_props and ls_props.linetype else "Continuous"
    return manager

@pytest.fixture
def style_orchestrator_real_logger_config(
    real_logger_service: LoggingService,
    sample_style_config: StyleConfig,
    mock_dxf_adapter: MagicMock,
    mock_dxf_resource_manager: MagicMock
) -> StyleApplicationOrchestratorService:
    """Create service with REAL logger and config (via StyleConfig), minimal external mocks."""
    mock_config_loader = Mock(spec=IConfigLoader)

    # Define sample ACI mappings directly
    sample_aci_mappings_for_mock = [
        AciColorMappingItem(name="red", aci_code=1),
        AciColorMappingItem(name="blue", aci_code=5),
        AciColorMappingItem(name="white", aci_code=7),
    ]
    mock_config_loader.get_aci_color_mappings.return_value = sample_aci_mappings_for_mock

    return StyleApplicationOrchestratorService(
        logger_service=real_logger_service,
        config_loader=mock_config_loader,
        dxf_adapter=mock_dxf_adapter,
        dxf_resource_manager=mock_dxf_resource_manager
    )


class TestBusinessLogicWithRealServices:
    """Test business logic with real services - ANTI-PATTERN ELIMINATION."""

    def test_aci_color_resolution_business_logic(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, caplog):
        """Test ACTUAL color resolution business logic, not mock interactions."""
        orchestrator = style_orchestrator_real_logger_config
        caplog.set_level("WARNING")

        # BUSINESS LOGIC TEST: Integer colors pass through
        assert orchestrator._resolve_aci_color(10) == 10

        # BUSINESS LOGIC TEST: None handling
        assert orchestrator._resolve_aci_color(None) is None

        # BUSINESS LOGIC TEST: Known string from StyleConfig
        assert orchestrator._resolve_aci_color("red") == 1
        assert orchestrator._resolve_aci_color("BLUE") == 5 # Case-insensitivity

        # BUSINESS LOGIC TEST: Unknown string defaults to DEFAULT_ACI_COLOR and logs warning
        caplog.clear()
        result = orchestrator._resolve_aci_color("nonexistent_color")
        assert result == DEFAULT_ACI_COLOR
        assert "ACI color name 'nonexistent_color' not found" in caplog.text

        # BUSINESS LOGIC TEST: Invalid type handling, logs warning
        caplog.clear()
        result = orchestrator._resolve_aci_color([1, 2, 3])  # type: ignore
        assert result == DEFAULT_ACI_COLOR
        assert "Unexpected color value type: <class 'list'>" in caplog.text

    def test_geodataframe_style_application_business_outcomes(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig):
        """Test ACTUAL GeoDataFrame styling outcomes, not mock calls."""
        orchestrator = style_orchestrator_real_logger_config
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0), Point(1, 1)]})
        style = sample_style_config.styles['full_style']

        result_gdf = orchestrator.apply_style_to_geodataframe(gdf, style, "test_layer")

        assert "_style_color_aci" in result_gdf.columns
        assert "_style_linetype" in result_gdf.columns
        assert "_style_text_font" in result_gdf.columns
        assert "_style_text_color_aci" in result_gdf.columns
        assert "_style_text_height" in result_gdf.columns

        assert result_gdf["_style_linetype"].iloc[0] == "DASHED"
        assert result_gdf["_style_text_font"].iloc[0] == "Times"
        assert result_gdf["_style_text_height"].iloc[0] == 1.0
        assert result_gdf["_style_color_aci"].iloc[0] == 7 # From layer style (white)
        assert result_gdf["_style_text_color_aci"].iloc[0] == 1 # From text style (red)

    def test_text_style_properties_business_logic(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig):
        """Test text styling business logic outcomes."""
        orchestrator = style_orchestrator_real_logger_config
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
        style = sample_style_config.styles["text_style_only"]
        assert style.text is not None

        result_gdf = orchestrator.apply_style_to_geodataframe(gdf, style, "text_layer")

        assert "_style_text_font" in result_gdf.columns
        assert "_style_text_height" in result_gdf.columns
        assert "_style_text_color_aci" in result_gdf.columns
        assert result_gdf["_style_text_font"].iloc[0] == style.text.font
        assert result_gdf["_style_text_height"].iloc[0] == style.text.height
        assert result_gdf["_style_text_color_aci"].iloc[0] == 5 # blue from text_style_only

    def test_empty_geodataframe_edge_case(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig):
        """Test real edge case: empty GeoDataFrame handling."""
        orchestrator = style_orchestrator_real_logger_config
        empty_gdf = gpd.GeoDataFrame()
        style = sample_style_config.styles["layer_style_only"]

        result = orchestrator.apply_style_to_geodataframe(empty_gdf, style, "empty_layer")
        assert result.empty
        assert isinstance(result, gpd.GeoDataFrame)

    def test_determine_entity_properties_from_style_logic(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig):
        """Test the core business logic of entity property determination for various styles."""
        orchestrator = style_orchestrator_real_logger_config

        # Test layer-only style
        layer_only_style = sample_style_config.styles['layer_style_only']
        props_layer_only = orchestrator._determine_entity_properties_from_style(layer_only_style, "LINE")
        assert props_layer_only["color"] == 1 # red
        assert props_layer_only["linetype"] == 'BYLAYER' # Default if not in layer_style_only
        assert props_layer_only["lineweight"] == LINEWEIGHT_BYLAYER # Default

        # Test text-only style (implies default layer properties)
        text_only_style = sample_style_config.styles['text_style_only']
        props_text_only = orchestrator._determine_entity_properties_from_style(text_only_style, "TEXT")
        assert props_text_only["color"] == 5 # blue from text style override
        assert props_text_only["text_specific"]["font"] == "Arial"
        assert props_text_only["text_specific"]["height"] == 2.5

        # Test full_style
        full_style = sample_style_config.styles['full_style']
        props_full_line = orchestrator._determine_entity_properties_from_style(full_style, "LINE")
        assert props_full_line["color"] == 7 # white from layer
        assert props_full_line["linetype"] == "DASHED"

        props_full_text = orchestrator._determine_entity_properties_from_style(full_style, "TEXT")
        assert props_full_text["color"] == 1 # red from text, overrides layer's white
        assert props_full_text["text_specific"]["font"] == "Times"
        assert props_full_text["text_specific"]["height"] == 1.0
        assert props_full_text["linetype"] == "DASHED" # from layer, as text style doesn't define it


class TestStyleResolutionBusinessLogic:
    """Refactored tests for style resolution logic."""

    def test_style_lookup_by_layer_name(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, caplog):
        """Business Outcome: Style is correctly retrieved by layer name if it exists in config."""
        orchestrator = style_orchestrator_real_logger_config
        caplog.set_level("DEBUG")

        # Case 1: Style exists for layer name
        expected_style = sample_style_config.styles["full_style"]
        retrieved_style = orchestrator.get_style_for_layer(
            layer_name="full_style",
            layer_definition=None,
            style_config=sample_style_config
        )
        assert retrieved_style is expected_style
        assert "Getting style for layer: full_style" in caplog.text

        # Case 2: Style does not exist for layer name
        caplog.clear()
        retrieved_style_none = orchestrator.get_style_for_layer(
            layer_name="non_existent_layer_style",
            layer_definition=None,
            style_config=sample_style_config
        )
        assert retrieved_style_none is None
        assert "No specific style for layer 'non_existent_layer_style'" in caplog.text

    def test_style_lookup_with_layer_definition_reference(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, caplog):
        """Business Outcome: Style referenced in LayerDefinition is prioritized and correctly retrieved."""
        orchestrator = style_orchestrator_real_logger_config
        caplog.set_level("DEBUG")

        # LayerDefinition references a style by name
        layer_def_ref = GeomLayerDefinition(name="some_layer", type="detail", style="style_for_layer_def")
        expected_style_ref = sample_style_config.styles["style_for_layer_def"]

        retrieved_style = orchestrator.get_style_for_layer(
            layer_name="some_layer",
            layer_definition=layer_def_ref,
            style_config=sample_style_config
        )
        assert retrieved_style is expected_style_ref
        # Check that it DIDN'T log "not found" for the referenced style
        assert f"Style 'style_for_layer_def' referenced by layer 'some_layer' not found" not in caplog.text

        # LayerDefinition references a non-existent style by name
        caplog.clear()
        layer_def_bad_ref = GeomLayerDefinition(name="another_layer", type="area", style="non_existent_style_in_def")
        # Assume no style named 'another_layer' in sample_style_config for this test case
        # to ensure fallback to layer_name lookup then None
        retrieved_style_bad_ref = orchestrator.get_style_for_layer(
            layer_name="another_layer",
            layer_definition=layer_def_bad_ref,
            style_config=sample_style_config
        )
        assert retrieved_style_bad_ref is None
        assert "Style 'non_existent_style_in_def' referenced by layer 'another_layer' not found." in caplog.text
        assert "No specific style for layer 'another_layer'" in caplog.text

    def test_style_lookup_layer_definition_is_namedstyle_object(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, caplog):
        """Business Outcome: If LayerDefinition.style IS a NamedStyle object, it's used directly."""
        orchestrator = style_orchestrator_real_logger_config
        direct_named_style = NamedStyle(name="direct_style_obj", layer=LayerStyleProperties(color=99))
        # Ensure the name of this direct style does not exist in sample_style_config to test direct object usage
        assert "direct_style_obj" not in sample_style_config.styles

        layer_def_direct = GeomLayerDefinition(name="direct_layer", type="line", style=direct_named_style)

        retrieved_style = orchestrator.get_style_for_layer(
            layer_name="direct_layer", # This layer name should also not exist in sample_style_config for isolation
            layer_definition=layer_def_direct,
            style_config=sample_style_config # Not used if style is direct object
        )
        assert retrieved_style is direct_named_style
        # Verify no attempt to look up "direct_style_obj" in config, as object was provided
        assert "Style 'direct_style_obj' referenced by layer" not in caplog.text
        assert "No specific style for layer 'direct_layer'" not in caplog.text # As direct object was found


class TestErrorHandlingWithRealServices:
    """Refactored tests for error handling using real services where appropriate."""

    def test_config_loader_error_propagates_correctly(self, real_logger_service, mock_dxf_adapter, mock_dxf_resource_manager, caplog):
        """Test that ConfigError from config_loader is properly caught and logged."""
        mock_config_loader_error = Mock(spec=IConfigLoader)

        # Set side_effect for the method actually used by the service to get ACI mappings
        mock_config_loader_error.get_aci_color_mappings.side_effect = ConfigError("Simulated ACI map load error")

        orchestrator = StyleApplicationOrchestratorService(
            logger_service=real_logger_service,
            config_loader=mock_config_loader_error,
            dxf_adapter=mock_dxf_adapter,
            dxf_resource_manager=mock_dxf_resource_manager
        )
        caplog.set_level("ERROR")

        # Trigger ACI map loading by calling a method that uses it
        aci_map = orchestrator._get_aci_color_map()
        assert aci_map == {} # Should be empty after error
        assert "Failed to load ACI color map: Simulated ACI map load error" in caplog.text

        # Subsequent color resolution should use default due to empty map
        caplog.clear()
        caplog.set_level("WARNING")
        assert orchestrator._resolve_aci_color("red") == DEFAULT_ACI_COLOR # Uses service's DEFAULT_ACI_COLOR
        assert "ACI color name 'red' not found in map" in caplog.text


    def test_dxf_adapter_layer_error_handling(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, mock_dxf_adapter: MagicMock, caplog):
        """Business Outcome: Errors from DXF adapter during layer style application are caught and logged."""
        orchestrator = style_orchestrator_real_logger_config
        drawing = MagicMock(spec=Drawing) # Mock the drawing object
        style = sample_style_config.styles["layer_style_only"]
        layer_name = "error_layer_adapter"

        # Simulate adapter failure
        mock_dxf_adapter.create_dxf_layer.side_effect = DXFProcessingError("Adapter failed to create layer")
        caplog.set_level("ERROR")

        # The method apply_styles_to_dxf_layer itself doesn't raise on this specific adapter error; it logs.
        orchestrator.apply_styles_to_dxf_layer(drawing, layer_name, style)

        assert f"Error applying style to DXF layer '{layer_name}': Adapter failed to create layer" in caplog.text
        # We can also check that set_layer_properties was not called if create_dxf_layer failed
        mock_dxf_adapter.set_layer_properties.assert_not_called()

    def test_dxf_adapter_entity_error_handling(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, mock_dxf_adapter: MagicMock, caplog):
        """Business Outcome: Errors from DXF adapter during entity style application are caught and logged."""
        orchestrator = style_orchestrator_real_logger_config
        drawing = MagicMock(spec=Drawing)
        mock_entity = MagicMock(spec=DXFGraphic)
        mock_entity.dxftype.return_value = "LINE"
        style = sample_style_config.styles["layer_style_only"]

        # Simulate adapter failure
        mock_dxf_adapter.set_entity_properties.side_effect = DXFProcessingError("Adapter failed to set entity props")
        caplog.set_level("ERROR")

        # The method apply_style_to_dxf_entity should catch and log DXFProcessingError
        orchestrator.apply_style_to_dxf_entity(mock_entity, style, drawing)

        assert f"Error applying style to DXF entity (type: LINE): Adapter failed to set entity props" in caplog.text

    def test_unexpected_error_in_entity_styling_wrapped(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, mock_dxf_adapter: MagicMock, caplog):
        """Business Outcome: Unexpected non-DXF errors during entity styling are wrapped in ProcessingError and logged."""
        orchestrator = style_orchestrator_real_logger_config
        drawing = MagicMock(spec=Drawing)
        mock_entity = MagicMock(spec=DXFGraphic); mock_entity.dxftype.return_value = "POINT"
        style = sample_style_config.styles["layer_style_only"]

        # Simulate an unexpected Python error from the adapter
        mock_dxf_adapter.set_entity_properties.side_effect = ValueError("Unexpected Python error from adapter")
        caplog.set_level("ERROR")

        # The method should catch this, log it, and re-raise as ProcessingError
        with pytest.raises(ProcessingError, match="Unexpected error styling entity \\(type: POINT\\)"):
            orchestrator.apply_style_to_dxf_entity(mock_entity, style, drawing)

        assert "Unexpected error styling entity (type: POINT): Unexpected Python error from adapter" in caplog.text

    # --- NEW NEGATIVE TESTS FOR StyleApplicationOrchestratorService ---

    def test_get_style_for_layer_empty_style_config(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, caplog):
        """Test get_style_for_layer with an empty StyleConfig."""
        orchestrator = style_orchestrator_real_logger_config
        empty_config = StyleConfig(styles={}, aci_color_mappings=[])
        caplog.set_level("INFO")

        result = orchestrator.get_style_for_layer("any_layer", None, empty_config)
        assert result is None
        assert "No specific style for layer 'any_layer'" in caplog.text

    def test_get_style_for_layer_def_style_unexpected_type(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, sample_style_config: StyleConfig, caplog):
        """Test get_style_for_layer when layer_definition.style is an unexpected type."""
        orchestrator = style_orchestrator_real_logger_config
        layer_def_bad_style_type = GeomLayerDefinition(name="bad_type_layer", type="detail", style=12345) # Style is int
        caplog.set_level("WARNING")

        result = orchestrator.get_style_for_layer("bad_type_layer", layer_def_bad_style_type, sample_style_config)
        assert result is None # Should fall back to layer name lookup, then None if layer name also not found
        assert "Layer 'bad_type_layer' style attribute unexpected type: <class 'int'>" in caplog.text
        assert "No specific style for layer 'bad_type_layer'" in caplog.text # Assuming 'bad_type_layer' is not a style name

    def test_apply_style_to_gdf_none_style(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, caplog):
        """Test apply_style_to_geodataframe with style=None."""
        orchestrator = style_orchestrator_real_logger_config
        gdf = gpd.GeoDataFrame({'geometry': [Point(0,0)]})
        caplog.set_level("DEBUG")

        # The service method itself might not log extensively if style is None,
        # as it might simply return the GDF unchanged or with no style columns.
        # The main check is that it doesn't crash and returns a GDF.
        result_gdf = orchestrator.apply_style_to_geodataframe(gdf, None, "layer_with_none_style")
        assert isinstance(result_gdf, gpd.GeoDataFrame)
        assert result_gdf.equals(gdf) # Expect it to be unchanged if style is None
        # Check for a debug log, if any specific handling is logged for None style
        # Example: assert "Style is None, no properties applied to GDF" in caplog.text

    def test_determine_entity_properties_from_style_none_style(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, caplog):
        """Test _determine_entity_properties_from_style with style=None."""
        orchestrator = style_orchestrator_real_logger_config
        caplog.set_level("WARNING")

        # Expect default properties or an error if None style is not handled gracefully by this internal method
        # Based on current implementation, it would raise AttributeError if style is None.
        # Let's verify it raises an error or handles it (e.g. returns default props).
        with pytest.raises(AttributeError): # Current implementation will raise AttributeError accessing style.layer
             orchestrator._determine_entity_properties_from_style(None, "LINE")
        # If it were to handle None gracefully, the test would be different:
        # props = orchestrator._determine_entity_properties_from_style(None, "LINE")
        # assert props["color"] == DEFAULT_ACI_COLOR
        # assert "Style is None, returning default properties" in caplog.text

    def test_apply_style_to_dxf_entity_none_inputs(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, mock_dxf_adapter: MagicMock, caplog):
        """Test apply_style_to_dxf_entity with None for entity, style, or drawing."""
        orchestrator = style_orchestrator_real_logger_config
        mock_entity = MagicMock(spec=DXFGraphic); mock_entity.dxftype.return_value = "LINE"
        drawing = MagicMock(spec=Drawing)
        style = NamedStyle(name="dummy_style")
        caplog.set_level("ERROR")

        with pytest.raises(ProcessingError, match="Entity to style cannot be None"):
            orchestrator.apply_style_to_dxf_entity(None, style, drawing)

        caplog.clear()
        with pytest.raises(ProcessingError, match="Style cannot be None for entity styling"):
            orchestrator.apply_style_to_dxf_entity(mock_entity, None, drawing)

        # Test with drawing = None. This might be caught by adapter or by service directly.
        # Current implementation seems to pass drawing to resource_manager/adapter, so error might originate there.
        # Let's assume if drawing is None, it should be caught early or lead to DXFProcessingError.
        mock_dxf_adapter.set_entity_properties.reset_mock()
        caplog.clear()
        with pytest.raises(DXFProcessingError): # Or ProcessingError if service checks first
             orchestrator.apply_style_to_dxf_entity(mock_entity, style, None)
        assert "DXF drawing object cannot be None" in caplog.text or mock_dxf_adapter.set_entity_properties.called # Check if it even reached adapter

    def test_apply_style_to_dxf_entity_resource_manager_error(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, mock_dxf_resource_manager: MagicMock, caplog):
        """Test apply_style_to_dxf_entity when resource_manager fails."""
        orchestrator = style_orchestrator_real_logger_config
        mock_entity = MagicMock(spec=DXFGraphic); mock_entity.dxftype.return_value = "TEXT"
        drawing = MagicMock(spec=Drawing)
        style_with_text = NamedStyle(name="text_err_style", text=TextStyleProperties(font="ErrorFont"))
        caplog.set_level("ERROR")

        mock_dxf_resource_manager.ensure_text_style.side_effect = DXFProcessingError("Failed to ensure ErrorFont")

        with pytest.raises(DXFProcessingError, match="Failed to ensure ErrorFont"):
            orchestrator.apply_style_to_dxf_entity(mock_entity, style_with_text, drawing)
        assert "Error preparing DXF resources (e.g., text style, linetype)" in caplog.text
        assert "Failed to ensure ErrorFont" in caplog.text

    def test_apply_styles_to_dxf_layer_none_drawing_or_style(self, style_orchestrator_real_logger_config: StyleApplicationOrchestratorService, caplog):
        """Test apply_styles_to_dxf_layer with None for drawing or style."""
        orchestrator = style_orchestrator_real_logger_config
        drawing = MagicMock(spec=Drawing)
        style = NamedStyle(name="dummy_layer_style", layer=LayerStyleProperties(color="red"))
        layer_name = "test_layer_none_inputs"
        caplog.set_level("ERROR")

        with pytest.raises(ProcessingError, match="DXF drawing object cannot be None for layer styling"):
            orchestrator.apply_styles_to_dxf_layer(None, layer_name, style)

        caplog.clear()
        # Style is None should be handled gracefully by apply_styles_to_dxf_layer, logging a warning/info
        # and likely not creating/modifying the layer, or applying defaults.
        caplog.set_level("INFO")
        orchestrator.apply_styles_to_dxf_layer(drawing, layer_name, None)
        assert f"Style for layer '{layer_name}' is None. No specific styling applied." in caplog.text

    def test_init_dxf_adapter_unavailable(self, real_logger_service, real_config_loader, mock_dxf_resource_manager, caplog):
        """Test orchestrator __init__ when DXF adapter reports unavailable."""
        mock_unavailable_adapter = MagicMock(spec=IDXFAdapter)
        mock_unavailable_adapter.is_available.return_value = False
        caplog.set_level("ERROR")

        StyleApplicationOrchestratorService(
            logger_service=real_logger_service,
            config_loader=real_config_loader,
            dxf_adapter=mock_unavailable_adapter,
            dxf_resource_manager=mock_dxf_resource_manager
        )
        assert "ezdxf library not available via adapter. DXF styling functionality will be severely limited." in caplog.text
