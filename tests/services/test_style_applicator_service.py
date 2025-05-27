"""Unit tests for StyleApplicatorService.

Tests the refactored StyleApplicatorService that primarily orchestrates calls
to specialized services like IStyleApplicationOrchestrator, IGeometryProcessor, etc.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock, ANY
import geopandas as gpd
import pandas as pd # No longer directly used in these simplified tests
# from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon # No longer needed here

from ezdxf.document import Drawing # For type hints
from ezdxf.entities import DXFGraphic # For type hints
# from ezdxf.lldxf.const import BYLAYER, BYBLOCK, LINEWEIGHT_BYLAYER, LINEWEIGHT_BYBLOCK, LINEWEIGHT_DEFAULT # No longer needed here

from src.services.style_applicator_service import StyleApplicatorService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.logging_service_interface import ILoggingService
# from src.interfaces.config_loader_interface import IConfigLoader # REMOVED from StyleApplicatorService constructor
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.interfaces.geometry_processor_interface import IGeometryProcessor
from src.interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator # ADDED
from src.domain.style_models import (
    NamedStyle, StyleConfig, TextStyleProperties # Added TextStyleProperties
    # LayerStyleProperties, TextStyleProperties, HatchStyleProperties, TextAttachmentPoint, DXFLineweight, AciColorMappingItem # Not directly used by SAS tests now
)
from src.domain.geometry_models import GeomLayerDefinition # ADDED IMPORT HERE
from src.domain.exceptions import DXFProcessingError # ConfigError might not be raised by SAS directly anymore

# Attempt to import ezdxf entities for spec if available, otherwise use object
try:
    # from ezdxf.entities import DXFGraphic # Already imported
    from ezdxf.entities.layer import Layer as EzdxfLayer
    EZDXF_AVAILABLE_FOR_SPEC = True
except ImportError:
    # DXFGraphic = object # type: ignore # Already handled
    EzdxfLayer = object # type: ignore
    EZDXF_AVAILABLE_FOR_SPEC = False


@pytest.fixture
def mock_logger_service() -> Mock:
    """Create mock logger service."""
    mock_service = Mock(spec=ILoggingService)
    mock_logger = MagicMock()
    # mock_logger.debug.side_effect = lambda msg, *args, **kwargs: print(f"MOCK_LOGGER_DEBUG: {msg}") # Keep for debugging if needed
    mock_service.get_logger.return_value = mock_logger
    return mock_service

# @pytest.fixture # REMOVED - IConfigLoader no longer direct dependency of StyleApplicatorService
# def mock_config_loader() -> Mock:
#     """Create mock config loader."""
#     # ... (implementation can be removed or kept if other test modules use it via conftest)
#     pass

@pytest.fixture
def mock_dxf_adapter() -> Mock:
    """Create mock DXF adapter."""
    mock_adapter = Mock(spec=IDXFAdapter)
    mock_adapter.is_available = MagicMock(return_value=True)
    # mock_adapter.get_modelspace = MagicMock(return_value=MagicMock(name="mock_modelspace")) # Not directly used by SAS
    return mock_adapter

@pytest.fixture
def mock_dxf_resource_manager() -> Mock:
    """Create mock DXF Resource Manager."""
    manager = Mock(spec=IDXFResourceManager)
    return manager

@pytest.fixture
def mock_geometry_processor() -> Mock:
    """Create mock Geometry Processor."""
    processor = Mock(spec=IGeometryProcessor)
    return processor

@pytest.fixture # ADDED NEW FIXTURE
def mock_style_orchestrator() -> Mock:
    """Create mock Style Application Orchestrator."""
    orchestrator = Mock(spec=IStyleApplicationOrchestrator)
    return orchestrator


@pytest.fixture
def style_applicator_service(
    mock_logger_service: Mock,
    mock_dxf_adapter: Mock,
    mock_dxf_resource_manager: Mock,
    mock_geometry_processor: Mock,
    mock_style_orchestrator: Mock
) -> StyleApplicatorService:
    """Create StyleApplicatorService instance with mocked dependencies."""
    return StyleApplicatorService(
        logger_service=mock_logger_service,
        dxf_adapter=mock_dxf_adapter,
        dxf_resource_manager=mock_dxf_resource_manager,
        geometry_processor=mock_geometry_processor,
        style_orchestrator=mock_style_orchestrator
    )


class TestStyleApplicatorServiceDelegation:
    """Tests that StyleApplicatorService correctly delegates to its orchestrator and processors."""

    def test_initialization(self, mock_logger_service, mock_dxf_adapter, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Test service initialization and storing of dependencies."""
        service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )
        assert service._logger is not None
        assert service._dxf_adapter == mock_dxf_adapter
        assert service._dxf_resource_manager == mock_dxf_resource_manager
        assert service._geometry_processor == mock_geometry_processor
        assert service._style_orchestrator == mock_style_orchestrator
        mock_dxf_adapter.is_available.assert_called_once()

    def test_initialization_dxf_adapter_not_available(self, mock_logger_service, mock_dxf_adapter, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        mock_dxf_adapter.is_available.return_value = False
        service = StyleApplicatorService(mock_logger_service, mock_dxf_adapter, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator)
        service._logger.error.assert_called_with("ezdxf library not available via adapter. DXF functionality will be severely limited.")

    def test_get_style_for_layer_delegates(self, style_applicator_service, mock_style_orchestrator):
        layer_name = "test_layer"
        layer_def = Mock(spec=GeomLayerDefinition)
        style_config = Mock(spec=StyleConfig)
        expected_style = Mock(spec=NamedStyle)
        mock_style_orchestrator.get_style_for_layer.return_value = expected_style

        result = style_applicator_service.get_style_for_layer(layer_name, layer_def, style_config)

        mock_style_orchestrator.get_style_for_layer.assert_called_once_with(layer_name, layer_def, style_config)
        assert result == expected_style

    def test_apply_style_to_geodataframe_delegates(self, style_applicator_service, mock_style_orchestrator):
        gdf = Mock(spec=gpd.GeoDataFrame)
        style = Mock(spec=NamedStyle)
        layer_name = "test_gdf_layer"
        expected_gdf = Mock(spec=gpd.GeoDataFrame)
        mock_style_orchestrator.apply_style_to_geodataframe.return_value = expected_gdf

        result = style_applicator_service.apply_style_to_geodataframe(gdf, style, layer_name)

        mock_style_orchestrator.apply_style_to_geodataframe.assert_called_once_with(gdf, style, layer_name)
        assert result == expected_gdf

    def test_apply_style_to_dxf_entity_delegates(self, style_applicator_service, mock_style_orchestrator, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = True
        entity = Mock(spec=DXFGraphic)
        style = Mock(spec=NamedStyle)
        dxf_drawing = Mock(spec=Drawing)

        style_applicator_service.apply_style_to_dxf_entity(entity, style, dxf_drawing)
        mock_style_orchestrator.apply_style_to_dxf_entity.assert_called_once_with(entity, style, dxf_drawing)

    def test_apply_style_to_dxf_entity_adapter_unavailable_raises(self, style_applicator_service, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = False
        entity = Mock(spec=DXFGraphic)
        style = Mock(spec=NamedStyle)
        dxf_drawing = Mock(spec=Drawing)
        with pytest.raises(DXFProcessingError, match="DXF adapter not available."):
            style_applicator_service.apply_style_to_dxf_entity(entity, style, dxf_drawing)

    def test_apply_styles_to_dxf_layer_delegates(self, style_applicator_service, mock_style_orchestrator, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = True
        dxf_drawing = Mock(spec=Drawing)
        layer_name = "test_dxf_layer"
        style = Mock(spec=NamedStyle)

        style_applicator_service.apply_styles_to_dxf_layer(dxf_drawing, layer_name, style)
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_once_with(dxf_drawing, layer_name, style)

    def test_apply_styles_to_dxf_layer_adapter_unavailable_raises(self, style_applicator_service, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = False
        dxf_drawing = Mock(spec=Drawing)
        layer_name = "test_dxf_layer"
        style = Mock(spec=NamedStyle)
        with pytest.raises(DXFProcessingError, match="DXF adapter not available."):
            style_applicator_service.apply_styles_to_dxf_layer(dxf_drawing, layer_name, style)

    def test_add_geodataframe_to_dxf_delegates(self, style_applicator_service, mock_geometry_processor, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = True
        dxf_drawing = Mock(spec=Drawing)
        gdf = Mock(spec=gpd.GeoDataFrame)
        layer_name = "geo_layer"
        style = Mock(spec=NamedStyle)
        layer_def = Mock(spec=GeomLayerDefinition)

        style_applicator_service.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, style, layer_def)
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_once_with(
            dxf_drawing=dxf_drawing, gdf=gdf, layer_name=layer_name, style=style, layer_definition=layer_def
        )

    def test_add_geodataframe_to_dxf_adapter_unavailable_raises(self, style_applicator_service, mock_dxf_adapter):
        mock_dxf_adapter.is_available.return_value = False
        dxf_drawing = Mock(spec=Drawing)
        gdf = Mock(spec=gpd.GeoDataFrame)
        layer_name = "geo_layer_fail"
        style = Mock(spec=NamedStyle)
        layer_def = Mock(spec=GeomLayerDefinition)
        with pytest.raises(DXFProcessingError, match="Cannot add geometries to DXF: ezdxf library not available via adapter."):
            style_applicator_service.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, style, layer_def)

    def test_clear_caches_delegates(self, style_applicator_service, mock_style_orchestrator):
        style_applicator_service.clear_caches()
        mock_style_orchestrator.clear_caches.assert_called_once()

    def test_get_cache_info_delegates(self, style_applicator_service, mock_style_orchestrator):
        expected_info = {}
        mock_style_orchestrator.get_cache_info.return_value = expected_info

        result = style_applicator_service.get_cache_info()

        mock_style_orchestrator.get_cache_info.assert_called_once()
        assert result == expected_info

    def test_add_geodataframe_to_dxf_with_complex_parameters_delegates(self, style_applicator_service, mock_geometry_processor, mock_dxf_adapter):
        """Test that add_geodataframe_to_dxf properly delegates to geometry processor with complex parameters including labels."""
        mock_dxf_adapter.is_available.return_value = True
        dxf_drawing = Mock(spec=Drawing)
        gdf = Mock(spec=gpd.GeoDataFrame)
        layer_name = "complex_geo_layer"
        style = NamedStyle(text=TextStyleProperties(font="Arial", height=2.5))
        layer_def = Mock(spec=GeomLayerDefinition)
        layer_def.label_column = 'complex_label_col'

        style_applicator_service.add_geodataframe_to_dxf(dxf_drawing, gdf, layer_name, style, layer_def)

        # Verify correct delegation to geometry processor with all parameters
        mock_geometry_processor.add_geodataframe_to_dxf.assert_called_once_with(
            dxf_drawing=dxf_drawing,
            gdf=gdf,
            layer_name=layer_name,
            style=style,
            layer_definition=layer_def
        )


# Removed TestStyleApplicatorServiceBasic and TestStyleApplicatorServiceGeometry classes
# as their detailed logic is now tested in the respective orchestrator/processor tests.
# The remaining tests in StyleApplicatorService should focus on its orchestration role.
