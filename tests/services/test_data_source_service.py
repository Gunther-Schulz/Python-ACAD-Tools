"""Unit tests for DataSourceService.

Tests the refactored DataSourceService that uses IDXFAdapter for DXF operations
instead of direct ezdxf calls (Sub-Task 1.B of REFACTORING_PLAN.MD).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point

from src.services.data_source_service import DataSourceService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.logging_service_interface import ILoggingService
from src.domain.exceptions import DXFProcessingError, DataSourceError


class TestDataSourceServiceInit:
    """Test DataSourceService initialization."""

    def test_init_with_available_dxf_adapter(self):
        """Test initialization when DXF adapter is available."""
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = True
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger

        service = DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

        assert service._dxf_adapter == mock_dxf_adapter
        assert service._logger == mock_logger
        assert hasattr(service, '_geodataframes')
        mock_dxf_adapter.is_available.assert_called_once()

    def test_init_with_unavailable_dxf_adapter(self):
        """Test initialization when DXF adapter is not available."""
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = False
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger

        service = DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

        # Service should still initialize but log error
        assert service._dxf_adapter == mock_dxf_adapter
        mock_logger.error.assert_called_once_with(
            "DXF library not available via adapter. DXF loading will fail."
        )


class TestDataSourceServiceLoadDXF:
    """Test DXF file loading functionality."""

    @pytest.fixture
    def mock_dxf_adapter(self):
        """Create mock DXF adapter."""
        mock_adapter = Mock(spec=IDXFAdapter)
        mock_adapter.is_available.return_value = True
        return mock_adapter

    @pytest.fixture
    def mock_logger_service(self):
        """Create mock logger service."""
        mock_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def data_source_service(self, mock_dxf_adapter, mock_logger_service):
        """Create DataSourceService with mocked dependencies."""
        return DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_dxf_file_success(self, mock_exists, data_source_service, mock_dxf_adapter):
        """Test successful DXF file loading."""
        # Setup
        test_file_path = "test.dxf"
        mock_drawing = Mock()
        mock_exists.return_value = True
        mock_dxf_adapter.load_dxf_file.return_value = mock_drawing

        # Execute
        result = data_source_service.load_dxf_file(test_file_path)

        # Verify
        assert result == mock_drawing
        mock_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)
        data_source_service._logger.info.assert_called_once_with(
            f"Successfully loaded DXF file via adapter: {test_file_path}"
        )

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_dxf_file_file_not_found(self, mock_exists, data_source_service, mock_dxf_adapter):
        """Test DXF file loading when file doesn't exist."""
        # Setup
        test_file_path = "missing.dxf"
        mock_exists.return_value = False

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match=f"DXF file not found: {test_file_path}"):
            data_source_service.load_dxf_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_not_called()

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_dxf_file_dxf_processing_error(self, mock_exists, data_source_service, mock_dxf_adapter):
        """Test DXF file loading with DXFProcessingError."""
        # Setup
        test_file_path = "invalid.dxf"
        error_message = "Invalid DXF structure"
        mock_exists.return_value = True
        mock_dxf_adapter.load_dxf_file.side_effect = DXFProcessingError(error_message)

        # Execute & Verify
        with pytest.raises(DXFProcessingError, match=error_message):
            data_source_service.load_dxf_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)
        data_source_service._logger.error.assert_called_once()

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_dxf_file_adapter_returns_none(self, mock_exists, data_source_service, mock_dxf_adapter):
        """Test DXF file loading when adapter returns None."""
        # Setup
        test_file_path = "empty.dxf"
        mock_exists.return_value = True
        mock_dxf_adapter.load_dxf_file.return_value = None

        # Execute & Verify
        with pytest.raises(DXFProcessingError, match="Adapter failed to load DXF file"):
            data_source_service.load_dxf_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_dxf_file_generic_exception(self, mock_exists, data_source_service, mock_dxf_adapter):
        """Test DXF file loading with generic exception."""
        # Setup
        test_file_path = "error.dxf"
        error_message = "Unexpected error"
        mock_exists.return_value = True
        mock_dxf_adapter.load_dxf_file.side_effect = Exception(error_message)

        # Execute & Verify
        with pytest.raises(DXFProcessingError, match="Unexpected error loading DXF file"):
            data_source_service.load_dxf_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)

    def test_load_dxf_file_adapter_unavailable(self, mock_logger_service):
        """Test DXF file loading when adapter is unavailable."""
        # Setup
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = False
        service = DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

        # Execute & Verify
        with pytest.raises(DXFProcessingError, match="DXF library not available via adapter"):
            service.load_dxf_file("test.dxf")

        mock_dxf_adapter.load_dxf_file.assert_not_called()


class TestDataSourceServiceGeoJSON:
    """Test GeoJSON file loading functionality."""

    @pytest.fixture
    def data_source_service(self):
        """Create DataSourceService for GeoJSON testing."""
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = True
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger
        return DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

    @patch('src.services.data_source_service.os.path.exists')
    @patch('src.services.data_source_service.gpd.read_file')
    def test_load_geojson_file_success(self, mock_read_file, mock_exists, data_source_service):
        """Test successful GeoJSON file loading."""
        # Setup
        test_file_path = "test.geojson"
        mock_gdf = gpd.GeoDataFrame({
            'geometry': [Point(0, 0), Point(1, 1)],
            'name': ['Point1', 'Point2']
        })
        mock_exists.return_value = True
        mock_read_file.return_value = mock_gdf

        # Execute
        result = data_source_service.load_geojson_file(test_file_path)

        # Verify
        assert result.equals(mock_gdf)
        mock_exists.assert_called_once_with(test_file_path)
        mock_read_file.assert_called_once_with(test_file_path)
        data_source_service._logger.info.assert_called_once()

    @patch('src.services.data_source_service.os.path.exists')
    def test_load_geojson_file_file_not_found(self, mock_exists, data_source_service):
        """Test GeoJSON file loading with FileNotFoundError."""
        # Setup
        test_file_path = "missing.geojson"
        mock_exists.return_value = False

        # Execute & Verify
        with pytest.raises(FileNotFoundError, match=f"GeoJSON file not found: {test_file_path}"):
            data_source_service.load_geojson_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)

    @patch('src.services.data_source_service.os.path.exists')
    @patch('src.services.data_source_service.gpd.read_file')
    def test_load_geojson_file_generic_exception(self, mock_read_file, mock_exists, data_source_service):
        """Test GeoJSON file loading with generic exception."""
        # Setup
        test_file_path = "invalid.geojson"
        error_message = "Invalid GeoJSON format"
        mock_exists.return_value = True
        mock_read_file.side_effect = Exception(error_message)

        # Execute & Verify
        with pytest.raises(DataSourceError, match=f"Failed to load GeoJSON file {test_file_path}"):
            data_source_service.load_geojson_file(test_file_path)

        mock_exists.assert_called_once_with(test_file_path)
        mock_read_file.assert_called_once_with(test_file_path)


class TestDataSourceServiceGeoDataFrame:
    """Test GeoDataFrame management functionality."""

    @pytest.fixture
    def data_source_service(self):
        """Create DataSourceService for GeoDataFrame testing."""
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = True
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger
        return DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

    def test_add_gdf_success(self, data_source_service):
        """Test successful GeoDataFrame addition."""
        # Setup
        gdf = gpd.GeoDataFrame({
            'geometry': [Point(0, 0), Point(1, 1)],
            'name': ['Point1', 'Point2']
        })
        layer_name = "test_layer"

        # Execute
        data_source_service.add_gdf(gdf, layer_name)

        # Verify
        assert layer_name in data_source_service._geodataframes
        assert data_source_service._geodataframes[layer_name] is gdf
        data_source_service._logger.info.assert_called()

    def test_add_gdf_invalid_type(self, data_source_service):
        """Test GeoDataFrame addition with invalid type."""
        # Setup
        invalid_gdf = "not a geodataframe"
        layer_name = "test_layer"

        # Execute & Verify
        with pytest.raises(DataSourceError, match="Invalid type for add_gdf"):
            data_source_service.add_gdf(invalid_gdf, layer_name)

    def test_add_gdf_overwrite_existing(self, data_source_service):
        """Test GeoDataFrame addition overwrites existing."""
        # Setup
        gdf1 = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
        gdf2 = gpd.GeoDataFrame({'geometry': [Point(1, 1)]})
        layer_name = "test_layer"

        # Execute
        data_source_service.add_gdf(gdf1, layer_name)
        data_source_service.add_gdf(gdf2, layer_name)

        # Verify
        assert data_source_service._geodataframes[layer_name] is gdf2
        data_source_service._logger.warning.assert_called_once()

    def test_get_gdf_success(self, data_source_service):
        """Test successful GeoDataFrame retrieval."""
        # Setup
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
        layer_name = "test_layer"
        data_source_service.add_gdf(gdf, layer_name)

        # Execute
        result = data_source_service.get_gdf(layer_name)

        # Verify
        assert result is gdf

    def test_get_gdf_not_found(self, data_source_service):
        """Test GeoDataFrame retrieval when layer not found."""
        # Setup
        layer_name = "missing_layer"

        # Execute & Verify
        with pytest.raises(DataSourceError, match=f"Layer '{layer_name}' not found"):
            data_source_service.get_gdf(layer_name)


class TestDataSourceServiceIntegration:
    """Integration tests for DataSourceService methods."""

    @pytest.fixture
    def data_source_service(self):
        """Create DataSourceService for integration testing."""
        mock_dxf_adapter = Mock(spec=IDXFAdapter)
        mock_dxf_adapter.is_available.return_value = True
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_logger_service.get_logger.return_value = mock_logger
        return DataSourceService(
            logger_service=mock_logger_service,
            dxf_adapter=mock_dxf_adapter
        )

    @patch('src.services.data_source_service.os.path.exists')
    def test_multiple_file_operations(self, mock_exists, data_source_service):
        """Test multiple file operations in sequence."""
        # Setup
        mock_exists.return_value = True
        data_source_service._dxf_adapter.load_dxf_file.return_value = Mock()

        # Test 1: DXF loading
        dxf_result = data_source_service.load_dxf_file("test.dxf")
        assert dxf_result is not None

        # Test 2: GeoDataFrame management
        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
        data_source_service.add_gdf(gdf, "test_layer")
        retrieved_gdf = data_source_service.get_gdf("test_layer")
        assert retrieved_gdf is gdf

        # Verify logger was called for both operations
        assert data_source_service._logger.info.call_count >= 2

    def test_error_handling_consistency(self, data_source_service):
        """Test that error handling is consistent across methods."""
        # Test DXF error handling
        data_source_service._dxf_adapter.load_dxf_file.side_effect = DXFProcessingError("Test error")

        with patch('src.services.data_source_service.os.path.exists', return_value=True):
            with pytest.raises(DXFProcessingError):
                data_source_service.load_dxf_file("test.dxf")

        # Test GeoDataFrame error handling
        with pytest.raises(DataSourceError):
            data_source_service.get_gdf("missing_layer")

        # Both should have logged errors
        assert data_source_service._logger.error.call_count >= 1
