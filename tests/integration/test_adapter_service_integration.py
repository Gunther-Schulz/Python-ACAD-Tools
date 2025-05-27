"""Integration tests for adapter and service interactions.

Tests the integration between DataSourceService, StyleApplicatorService, and EzdxfAdapter
following the refactoring in Sub-Tasks 1.A and 1.B of REFACTORING_PLAN.MD.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import geopandas as gpd
from shapely.geometry import Point, LineString
import pandas as pd

from src.adapters.ezdxf_adapter import EzdxfAdapter
from src.services.data_source_service import DataSourceService
from src.services.style_applicator_service import StyleApplicatorService
from src.interfaces.logging_service_interface import ILoggingService
from src.interfaces.config_loader_interface import IConfigLoader
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.interfaces.geometry_processor_interface import IGeometryProcessor
from src.interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator
from src.domain.style_models import NamedStyle, LayerStyleProperties
from src.domain.exceptions import DXFProcessingError, DataSourceError


class TestDataSourceStyleApplicatorIntegration:
    """Test integration between DataSourceService and StyleApplicatorService."""

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
        mock_style_config = Mock()
        mock_style_config.styles = {
                            "test_layer": {
                    "layer": {"color": "red", "lineweight": 25}
                }
        }
        mock_loader.load_global_styles.return_value = mock_style_config
        return mock_loader

    @pytest.fixture
    def mock_dxf_resource_manager(self) -> Mock:
        return Mock(spec=IDXFResourceManager)

    @pytest.fixture
    def mock_geometry_processor(self) -> Mock:
        return Mock(spec=IGeometryProcessor)

    @pytest.fixture
    def mock_style_orchestrator(self) -> Mock:
        return Mock(spec=IStyleApplicationOrchestrator)

    @pytest.fixture
    def mock_adapter(self):
        """Create mock DXF adapter."""
        adapter = Mock(spec=EzdxfAdapter)
        adapter.is_available.return_value = True

        # Mock drawing object
        mock_drawing = Mock()
        mock_modelspace = Mock()
        mock_drawing.modelspace.return_value = mock_modelspace
        adapter.load_dxf_file.return_value = mock_drawing
        adapter.create_document.return_value = mock_drawing

        return adapter

    @pytest.fixture
    def data_source_service(self, mock_logger_service, mock_adapter):
        """Create DataSourceService with mocked dependencies."""
        return DataSourceService(mock_logger_service, mock_adapter)

    @pytest.fixture
    def style_applicator_service(self, mock_logger_service, mock_adapter, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Create StyleApplicatorService with mocked dependencies."""
        return StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )

    @patch('os.path.exists')
    def test_load_dxf_and_apply_layer_style_workflow(self, mock_exists, data_source_service, style_applicator_service):
        """Test complete workflow: load DXF file and apply layer styles."""
        # Setup
        mock_exists.return_value = True
        dxf_file_path = "test.dxf"

        # Execute: Load DXF file
        drawing = data_source_service.load_dxf_file(dxf_file_path)

        # Verify DXF loading
        assert drawing is not None
        data_source_service._dxf_adapter.load_dxf_file.assert_called_once_with(dxf_file_path)

        # Execute: Apply styles to DXF layer
        layer_name = "test_layer"
        style = NamedStyle(layer=LayerStyleProperties(color="blue", lineweight=25))

        style_applicator_service.apply_styles_to_dxf_layer(drawing, layer_name, style)

        # Verify style application was orchestrated
        style_applicator_service._style_orchestrator.apply_styles_to_dxf_layer.assert_called_once_with(
            dxf_drawing=drawing, layer_name=layer_name, style=style
        )

    def test_create_dxf_and_add_geodataframe_workflow(self, data_source_service, style_applicator_service):
        """Test workflow: create new DXF and add GeoDataFrame."""
        # Setup: Create GeoDataFrame
        gdf_data = {
            'geometry': [Point(0, 0), Point(1, 1)],
            'name': ['Point1', 'Point2']
        }
        gdf = gpd.GeoDataFrame(gdf_data)

        # Execute: Create new DXF drawing (via adapter since DataSourceService doesn't have this method)
        drawing = data_source_service._dxf_adapter.create_document()

        # Verify DXF creation
        assert drawing is not None

        # Execute: Add GeoDataFrame to DXF
        layer_name = "points_layer"
        style = NamedStyle(layer=LayerStyleProperties(color="green"))

        style_applicator_service.add_geodataframe_to_dxf(drawing, gdf, layer_name, style)

        # Verify GeoDataFrame addition was orchestrated
        style_applicator_service._geometry_processor.add_geodataframe_to_dxf.assert_called_once_with(
            dxf_drawing=drawing, gdf=gdf, layer_name=layer_name, style=style, layer_definition=None
        )

    @patch('os.path.exists')
    def test_error_propagation_between_services(self, mock_exists, data_source_service, style_applicator_service):
        """Test error propagation between services."""
        # Setup: File doesn't exist
        mock_exists.return_value = False

        # Execute & Verify: DataSourceService error propagation
        with pytest.raises(FileNotFoundError):
            data_source_service.load_dxf_file("nonexistent.dxf")

        # Setup: Adapter unavailable
        data_source_service._dxf_adapter.is_available.return_value = False

        # Execute & Verify: Adapter unavailability error
        with pytest.raises(DXFProcessingError):
            data_source_service.load_dxf_file("test.dxf")

        # Test error from style applicator if orchestrator fails
        style_applicator_service._style_orchestrator.apply_styles_to_dxf_layer.side_effect = DXFProcessingError("Orchestrator failed")
        with pytest.raises(DXFProcessingError, match="Orchestrator failed"):
            style_applicator_service.apply_styles_to_dxf_layer(Mock(), "layer", Mock())

    def test_shared_adapter_state_consistency(self, mock_adapter, mock_logger_service, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Test that services sharing the same adapter maintain consistent state."""
        data_service = DataSourceService(mock_logger_service, mock_adapter)
        style_service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )

        with patch('os.path.exists', return_value=True):
            drawing = data_service.load_dxf_file("test.dxf")

        style = NamedStyle(layer=LayerStyleProperties(color="red"))
        style_service.apply_styles_to_dxf_layer(drawing, "test_layer", style)

        # Verify: Both services used the same adapter
        assert data_service._dxf_adapter is style_service._dxf_adapter
        assert mock_adapter.load_dxf_file.called
        assert mock_adapter.set_layer_properties.called


class TestEzdxfAdapterServiceIntegration:
    """Test integration with real EzdxfAdapter (mocked ezdxf library)."""

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
        mock_style_config = Mock()
        mock_style_config.styles = {}
        mock_loader.load_global_styles.return_value = mock_style_config
        return mock_loader

    @pytest.fixture
    def mock_dxf_resource_manager(self) -> Mock:
        return Mock(spec=IDXFResourceManager)

    @pytest.fixture
    def mock_geometry_processor(self) -> Mock:
        return Mock(spec=IGeometryProcessor)

    @pytest.fixture
    def mock_style_orchestrator(self) -> Mock:
        return Mock(spec=IStyleApplicationOrchestrator)

    @patch('src.adapters.ezdxf_adapter.ezdxf')
    @patch('os.path.exists')
    def test_real_adapter_with_services(self, mock_exists, mock_ezdxf, mock_logger_service, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Test services with real EzdxfAdapter (mocked ezdxf library)."""
        mock_exists.return_value = True
        mock_drawing_ezdxf = Mock()
        mock_layers_ezdxf = Mock()
        mock_layer_ezdxf = Mock()

        layer_exists_ezdxf = [False]
        def mock_contains_ezdxf(self, layer_name):
            return layer_exists_ezdxf[0]
        def mock_add_ezdxf(layer_name):
            layer_exists_ezdxf[0] = True
            return mock_layer_ezdxf
        def mock_get_ezdxf(layer_name):
            return mock_layer_ezdxf if layer_exists_ezdxf[0] else None

        mock_layers_ezdxf.__contains__ = mock_contains_ezdxf
        mock_layers_ezdxf.add = mock_add_ezdxf
        mock_layers_ezdxf.get = mock_get_ezdxf
        mock_drawing_ezdxf.layers = mock_layers_ezdxf
        mock_modelspace_ezdxf = Mock()
        mock_drawing_ezdxf.modelspace = mock_modelspace_ezdxf
        mock_ezdxf.readfile.return_value = mock_drawing_ezdxf
        mock_ezdxf.new.return_value = mock_drawing_ezdxf

        adapter = EzdxfAdapter(mock_logger_service)
        data_service = DataSourceService(mock_logger_service, adapter)
        style_service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )

        drawing_obj = data_service.load_dxf_file("test.dxf")
        style = NamedStyle(layer=LayerStyleProperties(color="red"))
        style_service.apply_styles_to_dxf_layer(drawing_obj, "test_layer", style)

        mock_ezdxf.readfile.assert_called_once_with("test.dxf")
        mock_style_orchestrator.apply_styles_to_dxf_layer.assert_called_once()

    def test_unavailable_adapter_with_services(self, mock_logger_service, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Test services when adapter reports ezdxf as unavailable."""
        adapter = EzdxfAdapter(mock_logger_service)
        adapter.is_available = MagicMock(return_value=False)

        style_service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )

        with pytest.raises(DXFProcessingError):
            style_service.apply_styles_to_dxf_layer(Mock(), "layer", Mock())


class TestCompleteWorkflowIntegration:
    """Test complete workflow from data source to styled DXF entities."""

    @pytest.fixture
    def complete_setup(self, mock_logger_service, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Provides a complete setup with mocked services and a real adapter."""
        mock_ezdxf_lib = patch('src.adapters.ezdxf_adapter.ezdxf').start()
        mock_drawing_ezdxf = MagicMock()
        mock_modelspace_ezdxf = MagicMock()
        mock_drawing_ezdxf.modelspace = mock_modelspace_ezdxf
        mock_layers_ezdxf = MagicMock()
        mock_drawing_ezdxf.layers = mock_layers_ezdxf
        mock_ezdxf_lib.readfile.return_value = mock_drawing_ezdxf
        mock_ezdxf_lib.new.return_value = mock_drawing_ezdxf

        adapter = EzdxfAdapter(mock_logger_service)
        data_service = DataSourceService(mock_logger_service, adapter)
        style_applicator_service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )
        gdf = gpd.GeoDataFrame({
            'geometry': [Point(1, 1), LineString([(0,0), (2,2)])],
            'name': ['Feature1', 'Feature2']
        })

        yield data_service, style_applicator_service, adapter, gdf, mock_drawing_ezdxf, mock_ezdxf_lib
        patch.stopall()

    @patch('os.path.exists')
    def test_complete_dxf_processing_workflow(self, mock_exists, complete_setup):
        """Test a full workflow: load data, create DXF, add GDF, apply styles."""
        data_service, style_service, adapter, gdf, mock_drawing, mock_ezdxf = complete_setup
        mock_exists.return_value = True

        dxf_doc = data_service.create_new_dxf_drawing()

        layer_name = "geo_layer"
        simple_style = NamedStyle(layer=LayerStyleProperties(color="blue"))
        style_service.add_geodataframe_to_dxf(dxf_doc, gdf, layer_name, simple_style)
        style_service._geometry_processor.add_geodataframe_to_dxf.assert_called_once()

        style_service.apply_styles_to_dxf_layer(dxf_doc, layer_name, simple_style)
        style_service._style_orchestrator.apply_styles_to_dxf_layer.assert_called_once()

        output_path = "output.dxf"
        data_service.save_dxf_drawing(dxf_doc, output_path)
        adapter.save_document.assert_called_once_with(dxf_doc, output_path)

    @patch('os.path.exists')
    def test_error_recovery_workflow(self, mock_exists, complete_setup):
        data_service, style_service, _, _, _, _ = complete_setup
        mock_exists.return_value = False
        with pytest.raises(FileNotFoundError):
            data_service.load_dxf_file("nonexistent.dxf")

    @patch('os.path.exists')
    def test_concurrent_service_operations(self, mock_exists, complete_setup):
        """Simulate multiple operations to check for interference (mocked)."""
        data_service, style_service, _, gdf, mock_drawing, _ = complete_setup
        mock_exists.return_value = True

        dxf1 = data_service.create_new_dxf_drawing()
        dxf2 = data_service.load_dxf_file("another.dxf")

        style1 = NamedStyle(layer=LayerStyleProperties(color=1))
        style2 = NamedStyle(layer=LayerStyleProperties(color=2))

        style_service.add_geodataframe_to_dxf(dxf1, gdf, "layer1", style1)
        style_service.apply_styles_to_dxf_layer(dxf2, "layer2", style2)

        assert style_service._geometry_processor.add_geodataframe_to_dxf.call_count == 1
        assert style_service._style_orchestrator.apply_styles_to_dxf_layer.call_count == 1


class TestServiceDataFlowIntegration:
    """Tests focusing on data flow and transformations between services."""

    @pytest.fixture
    def services_with_real_data_flow(self, mock_logger_service, mock_dxf_resource_manager, mock_geometry_processor, mock_style_orchestrator):
        """Setup services with a real adapter for more realistic data flow testing."""
        mock_ezdxf_lib = patch('src.adapters.ezdxf_adapter.ezdxf').start()
        mock_drawing_ezdxf = MagicMock()
        mock_modelspace_ezdxf = MagicMock()
        mock_drawing_ezdxf.modelspace = mock_modelspace_ezdxf
        mock_layers_ezdxf = MagicMock()
        mock_drawing_ezdxf.layers = mock_layers_ezdxf
        mock_ezdxf_lib.new.return_value = mock_drawing_ezdxf

        adapter = EzdxfAdapter(mock_logger_service)
        data_service = DataSourceService(mock_logger_service, adapter)
        style_service = StyleApplicatorService(
            logger_service=mock_logger_service,
            dxf_adapter=adapter,
            dxf_resource_manager=mock_dxf_resource_manager,
            geometry_processor=mock_geometry_processor,
            style_orchestrator=mock_style_orchestrator
        )
        yield data_service, style_service, adapter, mock_drawing_ezdxf
        patch.stopall()

    def test_geodataframe_style_application_integration(self, services_with_real_data_flow):
        """Test applying styles during GeoDataFrame to DXF conversion."""
        _, style_service, adapter, mock_drawing = services_with_real_data_flow

        gdf = gpd.GeoDataFrame({'geometry': [Point(0,0)], 'name':['P1']})
        layer_name = "styled_gdf_layer"
        style = NamedStyle(layer=LayerStyleProperties(color="red", linetype="DASHED"))

        style_service.add_geodataframe_to_dxf(mock_drawing, gdf, layer_name, style)

        style_service._geometry_processor.add_geodataframe_to_dxf.assert_called_once()

    def test_color_resolution_integration(self, services_with_real_data_flow):
        """Test that color name resolution flows correctly to adapter calls."""
        _, style_service, adapter, mock_drawing = services_with_real_data_flow
        mock_orchestrator_config_loader = style_service._style_orchestrator._config_loader
        mock_orchestrator_config_loader.get_aci_color_mappings.return_value = [Mock(name="neon_pink", aci_code=13)]
        # Accessing private attribute of orchestrator for test setup, might need adjustment if orchestrator changes
        if hasattr(style_service._style_orchestrator, '_aci_map'):
            style_service._style_orchestrator._aci_map = None

        layer_name = "color_res_layer"
        style = NamedStyle(layer=LayerStyleProperties(color="neon_pink"))

        mock_orchestrator_adapter = style_service._style_orchestrator._dxf_adapter
        mock_orchestrator_adapter.get_layer.return_value = Mock()
        mock_orchestrator_adapter.query_entities.return_value = []

        style_service.apply_styles_to_dxf_layer(mock_drawing, layer_name, style)

        style_service._style_orchestrator.apply_styles_to_dxf_layer.assert_called_once()
        mock_orchestrator_adapter.set_layer_properties.assert_called_with(
            doc=mock_drawing,
            layer_name=layer_name,
            color=13,
            linetype="BYLAYER",
            lineweight=-2
        )
