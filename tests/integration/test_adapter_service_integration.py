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
    def style_applicator_service(self, mock_config_loader, mock_logger_service, mock_adapter):
        """Create StyleApplicatorService with mocked dependencies."""
        return StyleApplicatorService(mock_config_loader, mock_logger_service, mock_adapter)

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

        # Verify style application
        style_applicator_service._dxf_adapter.set_layer_properties.assert_called_once()

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

        # Verify GeoDataFrame addition
        style_applicator_service._dxf_adapter.add_point.assert_called()

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

    def test_shared_adapter_state_consistency(self, mock_adapter, mock_logger_service, mock_config_loader):
        """Test that services sharing the same adapter maintain consistent state."""
        # Setup: Both services use the same adapter instance
        data_service = DataSourceService(mock_logger_service, mock_adapter)
        style_service = StyleApplicatorService(mock_config_loader, mock_logger_service, mock_adapter)

        # Execute: Operations on both services
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

    @patch('src.adapters.ezdxf_adapter.ezdxf')
    @patch('os.path.exists')
    def test_real_adapter_with_services(self, mock_exists, mock_ezdxf, mock_logger_service, mock_config_loader):
        """Test services with real EzdxfAdapter (mocked ezdxf library)."""
        # Setup: Mock ezdxf library
        mock_exists.return_value = True
        mock_drawing = Mock()
        mock_layers = Mock()
        mock_layer = Mock()

        # Mock layer creation behavior: first call returns False (doesn't exist), after creation returns True
        layer_exists = [False]  # Use list to allow modification in nested function
        def mock_contains(self, layer_name):
            return layer_exists[0]
        def mock_add(layer_name):
            layer_exists[0] = True  # After adding, layer exists
            return mock_layer
        def mock_get(layer_name):
            return mock_layer if layer_exists[0] else None

        mock_layers.__contains__ = mock_contains
        mock_layers.add = mock_add
        mock_layers.get = mock_get
        mock_drawing.layers = mock_layers
        mock_ezdxf.readfile.return_value = mock_drawing
        mock_ezdxf.new.return_value = mock_drawing

        # Create real adapter with mocked ezdxf
        adapter = EzdxfAdapter(mock_logger_service)

        # Create services with real adapter
        data_service = DataSourceService(mock_logger_service, adapter)
        style_service = StyleApplicatorService(mock_config_loader, mock_logger_service, adapter)

        # Execute: Load DXF file
        drawing = data_service.load_dxf_file("test.dxf")

        # Verify: Real adapter was used
        assert drawing is not None
        mock_ezdxf.readfile.assert_called_once_with("test.dxf")

        # Execute: Apply style
        style = NamedStyle(layer=LayerStyleProperties(color="blue"))
        style_service.apply_styles_to_dxf_layer(drawing, "test_layer", style)

        # Verify: Style application completed without error
        assert adapter.is_available()

    def test_unavailable_adapter_with_services(self, mock_logger_service, mock_config_loader):
        """Test services behavior when adapter is unavailable."""
        # Setup: Create adapter that will be unavailable
        adapter = EzdxfAdapter(mock_logger_service)
        # Mock the adapter to be unavailable
        adapter.is_available = Mock(return_value=False)

        # Create services with unavailable adapter
        data_service = DataSourceService(mock_logger_service, adapter)
        style_service = StyleApplicatorService(mock_config_loader, mock_logger_service, adapter)

        # Verify: Adapter is unavailable
        assert not adapter.is_available()

        # Execute & Verify: Services handle unavailable adapter
        with pytest.raises(DXFProcessingError):
            data_service.load_dxf_file("test.dxf")

        # Style service should handle unavailable adapter by raising DXFProcessingError
        mock_drawing = Mock()
        style = NamedStyle(layer=LayerStyleProperties(color="red"))

        # This should raise DXFProcessingError due to unavailable adapter
        with pytest.raises(DXFProcessingError):
            style_service.apply_styles_to_dxf_layer(mock_drawing, "test_layer", style)


class TestCompleteWorkflowIntegration:
    """Test complete end-to-end workflows."""

    @pytest.fixture
    def complete_setup(self):
        """Setup complete service ecosystem."""
        # Mock dependencies
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger

        mock_config_loader = Mock(spec=IConfigLoader)
        mock_config_loader.get_aci_color_mappings.return_value = []
        mock_style_config = Mock()
        mock_style_config.styles = {
            "roads": {"layer": {"color": "red", "lineweight": 25}},
            "buildings": {"layer": {"color": "blue", "lineweight": 20}}
        }
        mock_config_loader.load_global_styles.return_value = mock_style_config

        # Mock adapter
        mock_adapter = Mock(spec=EzdxfAdapter)
        mock_adapter.is_available.return_value = True

        mock_drawing = Mock()
        mock_modelspace = Mock()
        mock_drawing.modelspace.return_value = mock_modelspace
        mock_adapter.load_dxf_file.return_value = mock_drawing
        mock_adapter.create_document.return_value = mock_drawing

        # Create services
        data_service = DataSourceService(mock_logger_service, mock_adapter)
        style_service = StyleApplicatorService(mock_config_loader, mock_logger_service, mock_adapter)

        return {
            'data_service': data_service,
            'style_service': style_service,
            'mock_adapter': mock_adapter,
            'mock_drawing': mock_drawing,
            'mock_config_loader': mock_config_loader
        }

    @patch('os.path.exists')
    def test_complete_dxf_processing_workflow(self, mock_exists, complete_setup):
        """Test complete DXF processing workflow."""
        mock_exists.return_value = True
        setup = complete_setup
        data_service = setup['data_service']
        style_service = setup['style_service']

        # Step 1: Load DXF file
        drawing = data_service.load_dxf_file("input.dxf")
        assert drawing is not None

        # Step 2: Create GeoDataFrame
        gdf = gpd.GeoDataFrame({
            'geometry': [LineString([(0, 0), (1, 1)]), LineString([(2, 2), (3, 3)])],
            'road_type': ['highway', 'local']
        })

        # Step 3: Apply styles and add to DXF
        for idx, row in gdf.iterrows():
            layer_name = f"road_{row['road_type']}"
            style = NamedStyle(layer=LayerStyleProperties(color="red", lineweight=25))

            # Add geometry to DXF with style
            style_service.add_geodataframe_to_dxf(
                drawing,
                gpd.GeoDataFrame([row]),
                layer_name,
                style
            )

        # Step 4: Save DXF (would be done by adapter)
        setup['mock_adapter'].save_document.return_value = None

        # Verify complete workflow
        assert setup['mock_adapter'].load_dxf_file.called
        assert setup['mock_adapter'].add_line.called or setup['mock_adapter'].add_lwpolyline.called

    @patch('os.path.exists')
    def test_error_recovery_workflow(self, mock_exists, complete_setup):
        """Test error recovery in complete workflow."""
        mock_exists.return_value = False  # File doesn't exist
        setup = complete_setup
        data_service = setup['data_service']

        # Test graceful error handling
        with pytest.raises(FileNotFoundError):
            data_service.load_dxf_file("nonexistent.dxf")

        # Test recovery: create new DXF instead (via adapter)
        drawing = data_service._dxf_adapter.create_document()
        assert drawing is not None

    @patch('os.path.exists')
    def test_concurrent_service_operations(self, mock_exists, complete_setup):
        """Test concurrent operations on services."""
        mock_exists.return_value = True
        setup = complete_setup
        data_service = setup['data_service']
        style_service = setup['style_service']

        # Simulate concurrent operations
        drawing1 = data_service.load_dxf_file("file1.dxf")
        drawing2 = data_service.load_dxf_file("file2.dxf")

        # Apply styles to both drawings
        style = NamedStyle(layer=LayerStyleProperties(color="green"))
        style_service.apply_styles_to_dxf_layer(drawing1, "layer1", style)
        style_service.apply_styles_to_dxf_layer(drawing2, "layer2", style)

        # Verify both operations completed
        assert setup['mock_adapter'].load_dxf_file.call_count == 2
        assert setup['mock_adapter'].set_layer_properties.call_count == 2


class TestServiceDataFlowIntegration:
    """Test data flow between services."""

    @pytest.fixture
    def services_with_real_data_flow(self):
        """Setup services that can handle real data flow."""
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger

        mock_config_loader = Mock(spec=IConfigLoader)
        from src.domain.style_models import AciColorMappingItem
        mock_config_loader.get_aci_color_mappings.return_value = [
            AciColorMappingItem(name="red", aciCode=1),
            AciColorMappingItem(name="blue", aciCode=5),
            AciColorMappingItem(name="green", aciCode=3)
        ]

        mock_adapter = Mock(spec=EzdxfAdapter)
        mock_adapter.is_available.return_value = True

        data_service = DataSourceService(mock_logger_service, mock_adapter)
        style_service = StyleApplicatorService(mock_config_loader, mock_logger_service, mock_adapter)

        return data_service, style_service

    def test_geodataframe_style_application_integration(self, services_with_real_data_flow):
        """Test GeoDataFrame styling integration."""
        data_service, style_service = services_with_real_data_flow

        # Create test GeoDataFrame
        gdf = gpd.GeoDataFrame({
            'geometry': [Point(0, 0), Point(1, 1)],
            'category': ['A', 'B']
        })

        # Apply style to GeoDataFrame
        style = NamedStyle(layer=LayerStyleProperties(color="red"))
        styled_gdf = style_service.apply_style_to_geodataframe(gdf, style, "test_layer")

        # Verify styling was applied
        assert styled_gdf is not None
        assert len(styled_gdf) == len(gdf)
        assert '_style_color_aci' in styled_gdf.columns

    def test_color_resolution_integration(self, services_with_real_data_flow):
        """Test color resolution integration between services."""
        data_service, style_service = services_with_real_data_flow

        # Test color resolution
        aci_code = style_service._resolve_aci_color("red")
        assert aci_code == 1

        # Test with unknown color
        aci_code = style_service._resolve_aci_color("unknown_color")
        assert aci_code == 7  # Default color
