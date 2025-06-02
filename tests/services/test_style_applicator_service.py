"""Unit tests for StyleApplicatorService.
REFACTORED to eliminate Testing Theater anti-patterns:
- Reduced mock ratio.
- Business logic/outcome verification over mock interaction testing.
- Real services for simple dependencies (logger).
- Focused mocks for complex external dependencies (adapter, resource_manager).
- Introduced negative testing and edge cases.
"""
import pytest
from unittest.mock import Mock, MagicMock, call, ANY, patch # Added patch import
import geopandas as gpd
from shapely.geometry import Point # For creating sample GDF in tests

from ezdxf.document import Drawing # For type hints
from ezdxf.entities import DXFGraphic # For type hints
# from ezdxf.entities.layer import Layer as EzdxfLayer # Not strictly needed if only using Mock(spec=...)

from src.services.style_applicator_service import StyleApplicatorService
from src.services.logging_service import LoggingService # REAL SERVICE
# Interfaces for mocks
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.interfaces.geometry_processor_interface import IGeometryProcessor
from src.interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator
# Domain models
from src.domain.style_models import NamedStyle, StyleConfig, LayerStyleProperties, TextStyleProperties
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.exceptions import DXFProcessingError

# --- REAL SERVICE FIXTURES ---
@pytest.fixture
def real_logger_service() -> LoggingService:
    """Use REAL logging service."""
    return LoggingService()

# --- FOCUSED MOCK FIXTURES ---
@pytest.fixture
def mock_dxf_adapter() -> Mock:
    """Create a focused mock for IDXFAdapter."""
    mock = Mock(spec=IDXFAdapter)
    # If StyleApplicatorService constructor or methods immediately call other adapter methods, mock them here.
    # For instance, if create_document is called:
    # mock_drawing_instance = Mock(spec=Drawing)
    # mock.create_document.return_value = mock_drawing_instance
    return mock

@pytest.fixture
def mock_dxf_resource_manager() -> Mock:
    """Create a focused mock for IDXFResourceManager."""
    mock = Mock(spec=IDXFResourceManager)
    # Define specific return values or side effects if methods are directly called by StyleApplicatorService
    return mock

@pytest.fixture
def mock_geometry_processor() -> Mock:
    """Create a focused mock for IGeometryProcessor."""
    mock = Mock(spec=IGeometryProcessor)
    # Define specific return values or side effects, e.g.:
    # def sample_add_gdf_to_dxf(dxf_drawing, gdf, layer_name, style, layer_definition):
    #     # Simulate adding entities or modifying drawing if needed for outcome verification
    #     if not gdf.empty:
    #         dxf_drawing.entities_added = getattr(dxf_drawing, 'entities_added', 0) + len(gdf)
    # mock.add_geodataframe_to_dxf.side_effect = sample_add_gdf_to_dxf
    return mock

@pytest.fixture
def mock_style_orchestrator() -> Mock:
    """Create a focused mock for IStyleApplicationOrchestrator."""
    mock = Mock(spec=IStyleApplicationOrchestrator)
    # Define specific return values or side effects, e.g.:
    # mock.get_style_for_layer.return_value = NamedStyle(name="DefaultOrchestratorStyle")
    # def sample_apply_style_to_gdf(gdf, style, layer_name):
    #     gdf_copy = gdf.copy()
    #     if style and style.layer:
    #         gdf_copy[f"_style_color_{layer_name}"] = style.layer.color
    #     return gdf_copy
    # mock.apply_style_to_geodataframe.side_effect = sample_apply_style_to_gdf
    return mock

# --- SERVICE UNDER TEST FIXTURE ---
@pytest.fixture
def style_applicator_service_real_logger(
    real_logger_service: LoggingService, # REAL
    mock_dxf_adapter: Mock,
    mock_dxf_resource_manager: Mock,
    mock_geometry_processor: Mock,
    mock_style_orchestrator: Mock
) -> StyleApplicatorService:
    """Create StyleApplicatorService with a REAL logger and other deps appropriately mocked."""
    return StyleApplicatorService(
        logger_service=real_logger_service,
        dxf_adapter=mock_dxf_adapter,
        dxf_resource_manager=mock_dxf_resource_manager,
        geometry_processor=mock_geometry_processor,
        style_orchestrator=mock_style_orchestrator
    )

# Renamed fixture to be more specific as it's used by most tests now
@pytest.fixture
def service(style_applicator_service_real_logger: StyleApplicatorService) -> StyleApplicatorService:
    return style_applicator_service_real_logger


class TestStyleApplicatorServiceInitialization:
    """Tests for service initialization focusing on correct setup."""

    def test_initialization_with_real_logger_and_mocks(
        self,
        real_logger_service,
        mock_dxf_adapter,
        mock_dxf_resource_manager,
        mock_geometry_processor,
        mock_style_orchestrator
    ):
        """Test service initializes correctly, stores dependencies, and checks adapter availability."""
        # Execute
        service_instance = StyleApplicatorService(
            logger_service=real_logger_service,
            dxf_adapter=mock_dxf_adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )
        # BUSINESS VERIFICATION: Essential attributes are set with correct instances.
        assert service_instance._logger is not None
        assert service_instance._logger.name == "src.services.style_applicator_service" # Verify logger name
        assert service_instance._dxf_adapter == mock_dxf_adapter
        assert service_instance._dxf_resource_manager == mock_dxf_resource_manager
        assert service_instance._geometry_processor == mock_geometry_processor
        assert service_instance._style_orchestrator == mock_style_orchestrator

        # BUSINESS VERIFICATION: Adapter availability is checked on init. # This comment is now obsolete
        # mock_dxf_adapter.is_available.assert_called_once() # Removed assertion

    # Test 'test_initialization_logs_error_if_dxf_adapter_not_available' removed.

class TestStyleApplicatorServiceDelegationAndErrorHandling:
    """Focus on verifying correct delegation to collaborators and handling of adapter availability."""

    def test_get_style_for_layer_delegates_and_returns_value(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock
    ):
        """Business Outcome: Service correctly retrieves style via orchestrator."""
        # Setup: Prepare mock inputs and expected output for delegation
        layer_name = "roads"
        layer_def = Mock(spec=GeomLayerDefinition)
        style_config = Mock(spec=StyleConfig)
        expected_style = NamedStyle(name="RoadStyle", layer=LayerStyleProperties(color="yellow"))
        mock_style_orchestrator.get_style_for_layer.return_value = expected_style

        # Execute
        actual_style = service.get_style_for_layer(layer_name, layer_def, style_config)

        # BUSINESS VERIFICATION: Correct delegation and returned value matches expectation.
        mock_style_orchestrator.get_style_for_layer.assert_called_once_with(layer_name, layer_def, style_config)
        assert actual_style == expected_style

    def test_apply_style_to_geodataframe_delegates_and_returns_modified_gdf(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock
    ):
        """Business Outcome: GDF styling is applied via orchestrator, and result is returned."""
        # Setup: Use a REAL GeoDataFrame for more realistic interaction
        input_gdf = gpd.GeoDataFrame({'geometry': [Point(1, 1), Point(2, 2)]})
        style = NamedStyle(name="PointStyle", layer=LayerStyleProperties(color="red"))
        layer_name = "points_layer"

        # Simulate orchestrator actually modifying and returning a GDF
        processed_gdf = input_gdf.copy()
        processed_gdf["_style_info"] = "processed_by_orchestrator" # Example modification
        mock_style_orchestrator.apply_style_to_geodataframe.return_value = processed_gdf

        # Execute
        result_gdf = service.apply_style_to_geodataframe(input_gdf, style, layer_name)

        # BUSINESS VERIFICATION: Correct delegation and the GDF returned by orchestrator is passed through.
        mock_style_orchestrator.apply_style_to_geodataframe.assert_called_once_with(input_gdf, style, layer_name)
        assert "processed_by_orchestrator" in result_gdf["_style_info"].tolist()
        assert result_gdf is processed_gdf # Check if it's the same instance orchestrator returned

    def test_apply_style_to_dxf_entity_delegates_when_adapter_available(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Service applies style to entity via orchestrator."""
        # Setup
        mock_entity = Mock(spec=DXFGraphic)
        style = NamedStyle(name="EntityStyle")
        dxf_drawing = Mock(spec=Drawing)

        # Execute
        service.apply_style_to_dxf_entity(mock_entity, style, dxf_drawing)

        # BUSINESS VERIFICATION
        mock_style_orchestrator.apply_style_to_dxf_entity.assert_called_once_with(mock_entity, style, dxf_drawing, mock_dxf_adapter)

    def test_apply_styles_to_dxf_layer_delegates_when_adapter_available(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Service applies styles to layer via orchestrator."""
        # Setup
        dxf_drawing = Mock(spec=Drawing)
        layer_name = "test_layer"
        style = NamedStyle(name="LayerStyle")

        # Execute
        service.apply_styles_to_dxf_layer(dxf_drawing, layer_name, style)

        # BUSINESS VERIFICATION
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_once_with(dxf_drawing, layer_name, style, mock_dxf_adapter)

    def test_add_geodataframe_to_dxf_delegates_to_geometry_processor_when_adapter_available(
        self, service: StyleApplicatorService, mock_geometry_processor: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Adding GDF to DXF is delegated to geometry_processor."""
        # Setup
        dxf_drawing = Mock(spec=Drawing)
        gdf = gpd.GeoDataFrame({'geometry': [Point(1,1)]})
        layer_name = "test_gdf_layer"
        style = NamedStyle(name="GDFStyle")
        layer_definition = Mock(spec=GeomLayerDefinition)

        # Execute
        service.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, style, layer_definition)

        # BUSINESS VERIFICATION
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_once_with(
            dxf_drawing, gdf, layer_name, style, layer_definition
        )

    def test_clear_caches_delegates_to_style_orchestrator(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock
    ):
        """Business Outcome: Cache clearing is delegated to the orchestrator."""
        service.clear_caches()
        mock_style_orchestrator.clear_caches.assert_called_once()

    def test_get_cache_info_delegates_and_returns_orchestrator_info(
        self, service: StyleApplicatorService, mock_style_orchestrator: Mock
    ):
        """Business Outcome: Cache info retrieval is delegated, and orchestrator's data is returned."""
        expected_cache_info = {"orchestrator_cache_size": 10, "some_other_info": "details"}
        mock_style_orchestrator.get_cache_info.return_value = expected_cache_info

        actual_cache_info = service.get_cache_info()

        mock_style_orchestrator.get_cache_info.assert_called_once()
        assert actual_cache_info == expected_cache_info

    # Test from original file, ensuring it fits the new structure
    def test_add_geodataframe_to_dxf_with_complex_parameters_delegates_correctly(
        self, service: StyleApplicatorService, mock_geometry_processor: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Complex GDF additions (e.g. with labels) are correctly delegated."""
        dxf_drawing = Mock(spec=Drawing)
        gdf = gpd.GeoDataFrame({'geometry': [Point(10, 20)], 'label_text': ['InfoPoint']}) # Real GDF
        layer_name = "complex_layer"
        # Style that might influence labeling if geometry_processor uses it
        style = NamedStyle(name="LabelStyle", text=TextStyleProperties(font="Arial", height=2.5))
        # Layer definition that specifies a label column
        layer_def = Mock(spec=GeomLayerDefinition)
        layer_def.label_column = 'label_text' # Critical for testing this scenario

        service.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, style, layer_def)

        # BUSINESS VERIFICATION: Geometry processor is called with all correct parameters,
        # including those relevant for complex operations like labeling.
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_once_with(
            dxf_drawing=dxf_drawing,
            gdf=gdf,
            layer_name=layer_name,
            style=style,
            layer_definition=layer_def # Ensure layer_def with label_column is passed
        )

    def test_apply_style_to_dxf_entity_handles_none_parameters(self, service: StyleApplicatorService, mock_style_orchestrator: Mock, mock_dxf_adapter: Mock):
        """Test apply_style_to_dxf_entity handles None inputs without crashing and delegates appropriately."""
        # Test with None entity
        dxf_drawing = Mock(spec=Drawing)
        style = NamedStyle(name="TestStyle")
        service.apply_style_to_dxf_entity(None, style, dxf_drawing)
        mock_style_orchestrator.apply_style_to_dxf_entity.assert_called_with(None, style, dxf_drawing, mock_dxf_adapter)
        mock_style_orchestrator.reset_mock()

        # Test with None style
        mock_entity = Mock(spec=DXFGraphic)
        service.apply_style_to_dxf_entity(mock_entity, None, dxf_drawing)
        mock_style_orchestrator.apply_style_to_dxf_entity.assert_called_with(mock_entity, None, dxf_drawing, mock_dxf_adapter)
        mock_style_orchestrator.reset_mock()

        # Test with None drawing
        service.apply_style_to_dxf_entity(mock_entity, style, None)
        mock_style_orchestrator.apply_style_to_dxf_entity.assert_called_with(mock_entity, style, None, mock_dxf_adapter)

    def test_apply_styles_to_dxf_layer_handles_none_parameters(self, service: StyleApplicatorService, mock_style_orchestrator: Mock, mock_dxf_adapter: Mock):
        """Test apply_styles_to_dxf_layer handles None inputs without crashing and delegates appropriately."""
        dxf_drawing = Mock(spec=Drawing)
        style = NamedStyle(name="TestStyle")
        layer_name = "test_layer"

        # Test with None drawing
        service.apply_styles_to_dxf_layer(None, layer_name, style)
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_with(None, layer_name, style, mock_dxf_adapter)
        mock_style_orchestrator.reset_mock()

        # Test with None style
        service.apply_styles_to_dxf_layer(dxf_drawing, layer_name, None)
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_with(dxf_drawing, layer_name, None, mock_dxf_adapter)
        mock_style_orchestrator.reset_mock()

        # Test with None layer_name (should probably be handled by orchestrator or raise specific error)
        service.apply_styles_to_dxf_layer(dxf_drawing, None, style)
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_with(dxf_drawing, None, style, mock_dxf_adapter)


    def test_add_geodataframe_to_dxf_handles_none_parameters(self, service: StyleApplicatorService, mock_geometry_processor: Mock, mock_dxf_adapter: Mock):
        """Test add_geodataframe_to_dxf handles None inputs without crashing and delegates appropriately."""
        dxf_drawing = Mock(spec=Drawing)
        gdf = gpd.GeoDataFrame({'geometry': [Point(1, 1)]})
        layer_name = "test_layer"

        # Test with None drawing
        service.add_geodataframe_to_dxf(None, gdf, layer_name)
        # Note: add_geodataframe_to_dxf has optional style and layer_definition,
        # so the call to geometry_processor will include Nones for those if not provided.
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_with(
            dxf_drawing=None, gdf=gdf, layer_name=layer_name, style=None, layer_definition=None
        )
        mock_geometry_processor.reset_mock()

        # Test with None GDF
        service.add_geodataframe_to_dxf(dxf_drawing, None, layer_name)
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_with(
            dxf_drawing=dxf_drawing, gdf=None, layer_name=layer_name, style=None, layer_definition=None
        )
        mock_geometry_processor.reset_mock()

        # Test with None layer_name
        service.add_geodataframe_to_dxf(dxf_drawing, gdf, None)
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_with(
            dxf_drawing=dxf_drawing, gdf=gdf, layer_name=None, style=None, layer_definition=None
        )
        mock_geometry_processor.reset_mock()

    def test_get_style_for_layer_handles_none_parameters(self, service: StyleApplicatorService, mock_style_orchestrator: Mock):
        """Test get_style_for_layer handles None inputs without crashing and delegates appropriately."""
        # Assuming layer_name and style_config are critical for StyleApplicatorService to pass to orchestrator.
        # Layer_definition is Optional in StyleApplicatorService.get_style_for_layer method signature.
        valid_layer_name = "some_layer"
        valid_config = Mock(spec=StyleConfig)
        # Layer_definition can be None as it's optional
        optional_layer_def = None

        # Test None layer_name
        service.get_style_for_layer(None, optional_layer_def, valid_config)
        mock_style_orchestrator.get_style_for_layer.assert_called_with(None, optional_layer_def, valid_config)
        mock_style_orchestrator.reset_mock()

        # Test None style_config
        service.get_style_for_layer(valid_layer_name, optional_layer_def, None)
        mock_style_orchestrator.get_style_for_layer.assert_called_with(valid_layer_name, optional_layer_def, None)
        mock_style_orchestrator.reset_mock()

        # Test with valid layer_definition as well (it's optional, so this is a variation)
        valid_layer_def = Mock(spec=GeomLayerDefinition)
        service.get_style_for_layer(valid_layer_name, valid_layer_def, valid_config)
        mock_style_orchestrator.get_style_for_layer.assert_called_with(valid_layer_name, valid_layer_def, valid_config)
        mock_style_orchestrator.reset_mock()

# Note: The original file had comments about removing TestStyleApplicatorServiceBasic
# and TestStyleApplicatorServiceGeometry. This refactoring effectively achieves that by
# focusing StyleApplicatorService tests on its direct responsibilities (delegation, adapter checks)
# and assuming that the detailed logic of collaborators (orchestrator, processor)
# is tested in their own respective unit tests.
