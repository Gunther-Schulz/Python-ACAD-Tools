"""Unit tests for DataSourceService.

Tests the refactored DataSourceService that uses IDXFAdapter for DXF operations
instead of direct ezdxf calls (Sub-Task 1.B of REFACTORING_PLAN.MD).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, ANY
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point
from ezdxf.document import Drawing as EzdxfDrawing

from src.services.data_source_service import DataSourceService
from src.services.logging_service import LoggingService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.domain.exceptions import DXFProcessingError, DataSourceError

# --- REAL SERVICE FIXTURES ---
@pytest.fixture
def real_logger_service() -> LoggingService:
    return LoggingService()

# --- FOCUSED MOCK FIXTURES ---
@pytest.fixture
def mock_dxf_adapter(monkeypatch) -> MagicMock:
    adapter = MagicMock(spec=IDXFAdapter)
    # Mock the load_dxf_file method to return a mock drawing by default
    adapter.load_dxf_file.return_value = MagicMock(spec=EzdxfDrawing, name="MockEzdxfDrawing")
    return adapter

@pytest.fixture
def sample_gdf() -> gpd.GeoDataFrame:
    """Provides a sample GeoDataFrame for testing."""
    return gpd.GeoDataFrame({
        'geometry': [Point(0, 0), Point(1, 1)],
        'property1': ['A', 'B'],
        'property2': [10, 20]
    })

# --- SERVICE UNDER TEST FIXTURE (Parameterized for adapter state) ---
@pytest.fixture
def service_real_logger(real_logger_service: LoggingService, mock_dxf_adapter: MagicMock) -> DataSourceService:
    """Service instance with a mock DXF adapter and REAL logger."""
    return DataSourceService(logger_service=real_logger_service, dxf_adapter=mock_dxf_adapter)


class TestDataSourceServiceInit:
    def test_init_succeeds(self, real_logger_service, mock_dxf_adapter, caplog):
        """Business Outcome: Initialization succeeds, no error logged regarding adapter availability."""
        with caplog.at_level("INFO"): # Capture info logs too
            service = DataSourceService(logger_service=real_logger_service, dxf_adapter=mock_dxf_adapter)

        assert service._dxf_adapter == mock_dxf_adapter
        assert hasattr(service, '_geodataframes')
        assert "DXF library not available via adapter. DXF loading will fail." not in caplog.text


class TestDataSourceServiceLoadDXF:
    @patch('src.services.data_source_service.os.path.exists', return_value=True)
    def test_load_dxf_file_success(self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock, caplog):
        """Business Outcome: Successfully loads DXF if file exists, and adapter succeeds."""
        test_file_path = "path/to/successful.dxf"
        mock_drawing_object = MagicMock(spec=EzdxfDrawing) # Simulate a drawing object
        mock_dxf_adapter.load_dxf_file.return_value = mock_drawing_object

        with caplog.at_level("INFO"):
            result = service_real_logger.load_dxf_file(test_file_path)

        assert result == mock_drawing_object
        mock_os_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)
        assert f"Successfully loaded DXF file via adapter: {test_file_path}" in caplog.text

    @patch('src.services.data_source_service.os.path.exists', return_value=False)
    def test_load_dxf_file_not_found_raises_file_not_found_error(self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock):
        """Negative Test: Raises FileNotFoundError if os.path.exists is False."""
        test_file_path = "path/to/nonexistent.dxf"
        with pytest.raises(FileNotFoundError, match=f"DXF file not found: {test_file_path}"):
            service_real_logger.load_dxf_file(test_file_path)
        mock_os_exists.assert_called_once_with(test_file_path)
        mock_dxf_adapter.load_dxf_file.assert_not_called()

    @patch('src.services.data_source_service.os.path.exists', return_value=True)
    def test_load_dxf_file_adapter_raises_dxf_processing_error_propagates(
        self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock, caplog
    ):
        """Negative Test: DXFProcessingError from adapter is propagated and logged."""
        test_file_path = "path/to/adapter_error.dxf"
        error_message = "Adapter-specific DXF read failure"
        mock_dxf_adapter.load_dxf_file.side_effect = DXFProcessingError(error_message)

        with caplog.at_level("ERROR"):
            with pytest.raises(DXFProcessingError, match=error_message):
                service_real_logger.load_dxf_file(test_file_path)

        assert f"Adapter failed to load DXF file {test_file_path}: {error_message}" in caplog.text
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)

    @patch('src.services.data_source_service.os.path.exists', return_value=True)
    def test_load_dxf_file_adapter_returns_none_raises_dxf_processing_error(
        self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock, caplog
    ):
        """Negative Test: If adapter returns None, raises DXFProcessingError and logs error."""
        test_file_path = "path/to/adapter_returns_none.dxf"
        mock_dxf_adapter.load_dxf_file.return_value = None

        with caplog.at_level("ERROR"):
            with pytest.raises(DXFProcessingError, match=f"Adapter failed to load DXF file {test_file_path} \\(returned None\\)."):
                service_real_logger.load_dxf_file(test_file_path)

        assert f"Adapter returned None for DXF file {test_file_path} without explicit exception." in caplog.text
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)

    @patch('src.services.data_source_service.os.path.exists', return_value=True)
    def test_load_dxf_file_adapter_unexpected_exception_wrapped_and_logged(
        self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock, caplog
    ):
        """Negative Test: Unexpected exceptions from adapter are wrapped in DXFProcessingError and logged."""
        test_file_path = "path/to/adapter_unexpected_error.dxf"
        original_error_message = "Something completely unexpected from adapter"
        mock_dxf_adapter.load_dxf_file.side_effect = ValueError(original_error_message) # Example non-DXF error

        with caplog.at_level("ERROR"):
            with pytest.raises(DXFProcessingError, match=f"Unexpected error loading DXF file {test_file_path} via adapter: {original_error_message}"):
                service_real_logger.load_dxf_file(test_file_path)

        assert f"Unexpected error loading DXF file {test_file_path} via adapter: {original_error_message}" in caplog.text
        mock_dxf_adapter.load_dxf_file.assert_called_once_with(test_file_path)

    @pytest.mark.parametrize("invalid_path_input", [None, ""])
    def test_load_dxf_file_none_or_empty_path_raises_error(self, service_real_logger: DataSourceService, invalid_path_input):
        """Negative Test: None or empty file_path for DXF loading raises appropriate error."""
        # Expect TypeError for None, ValueError or FileNotFoundError for empty string if os.path.exists handles it that way
        with pytest.raises((TypeError, ValueError, FileNotFoundError, DXFProcessingError)):
            service_real_logger.load_dxf_file(invalid_path_input)

    @patch('src.services.data_source_service.os.path.exists', side_effect=IsADirectoryError("[Errno 21] Is a directory: '/fake/dir'"))
    def test_load_dxf_file_path_is_directory_raises_error(self, mock_os_exists, service_real_logger: DataSourceService):
        """Negative Test: Path is a directory for DXF loading raises IsADirectoryError or similar."""
        test_file_path = "/fake/dir"
        # Service might catch IsADirectoryError from os.path.exists or adapter might raise it wrapped
        with pytest.raises((IsADirectoryError, DXFProcessingError, FileNotFoundError)):
            service_real_logger.load_dxf_file(test_file_path)
        mock_os_exists.assert_called_once_with(test_file_path)


class TestDataSourceServiceLoadGeoJSON:
    # Service for these tests doesn't strictly need a functional DXF adapter, but fixture provides one.
    @patch('src.services.data_source_service.gpd.read_file')
    def test_load_geojson_success(self, mock_gpd_read_file, service_real_logger: DataSourceService, caplog):
        """Business Outcome: Successfully loads GeoJSON if file exists and gpd.read_file succeeds."""
        test_file_path = "path/to/data.geojson"
        sample_gdf = gpd.GeoDataFrame({'geometry': [Point(1,2)], 'prop': ['value']})
        mock_gpd_read_file.return_value = sample_gdf

        with caplog.at_level("INFO"):
            result_gdf = service_real_logger.load_geojson_file(test_file_path)

        assert result_gdf.equals(sample_gdf)
        mock_gpd_read_file.assert_called_once_with(test_file_path, crs=None)
        assert f"Successfully loaded GeoJSON: {test_file_path} with CRS: {sample_gdf.crs}" in caplog.text

    @patch('src.services.data_source_service.os.path.exists', return_value=False)
    def test_load_geojson_file_not_found_raises_error(self, mock_os_exists, service_real_logger: DataSourceService, mock_dxf_adapter: MagicMock): # mock_dxf_adapter needed for service fixture
        """Negative Test: Raises FileNotFoundError if os.path.exists is False for GeoJSON."""
        test_file_path = "path/to/nonexistent.geojson"
        with pytest.raises(DataSourceError, match=f"Failed to load GeoJSON file {test_file_path}"):
            service_real_logger.load_geojson_file(test_file_path)

    @patch('src.services.data_source_service.gpd.read_file')
    def test_load_geojson_gpd_read_error_raises_data_source_error(
        self, mock_gpd_read_file, service_real_logger: DataSourceService, caplog
    ):
        """Negative Test: Exceptions from gpd.read_file are wrapped in DataSourceError and logged."""
        test_file_path = "path/to/invalid.geojson"
        original_error_message = "GeoPandas failed to parse"
        mock_gpd_read_file.side_effect = ValueError(original_error_message) # Example error from gpd

        with caplog.at_level("ERROR"):
            with pytest.raises(DataSourceError, match=f"Failed to load GeoJSON file {test_file_path}: {original_error_message}"):
                service_real_logger.load_geojson_file(test_file_path)

        assert f"Failed to load GeoJSON file {test_file_path}: {original_error_message}" in caplog.text
        mock_gpd_read_file.assert_called_once_with(test_file_path, crs=None)

    @pytest.mark.parametrize("invalid_path_input", [None, ""])
    def test_load_geojson_none_or_empty_path_raises_error(self, service_real_logger: DataSourceService, invalid_path_input):
        """Negative Test: None or empty file_path for GeoJSON loading raises appropriate error."""
        with pytest.raises((TypeError, ValueError, FileNotFoundError, DataSourceError)):
            service_real_logger.load_geojson_file(invalid_path_input)

    def test_load_geojson_path_is_directory_raises_error(self, service_real_logger: DataSourceService, caplog):
        """Negative Test: Path is a directory for GeoJSON loading raises IsADirectoryError or DataSourceError."""
        test_file_path = "/fake/dir"
        # gpd.read_file itself raises errors for directories (e.g., pyogrio.errors.DataSourceError: No such file or directory)
        # The service wraps this into a DataSourceError.
        with caplog.at_level("ERROR"):
            with pytest.raises(DataSourceError, match=f"Failed to load GeoJSON file {test_file_path}"):
                service_real_logger.load_geojson_file(test_file_path)
        assert f"Failed to load GeoJSON file {test_file_path}" in caplog.text


class TestDataSourceServiceGeoDataFrameManagement:
    def test_add_gdf_success_and_get_gdf_retrieves_it(self, service_real_logger: DataSourceService, caplog):
        """Business Outcome: Added GDF can be retrieved. Logs info."""
        gdf = gpd.GeoDataFrame({'geometry': [Point(0,0)], 'data': ['A']})
        layer_name = "my_data_layer"

        with caplog.at_level("INFO"):
            service_real_logger.add_gdf(gdf, layer_name)

        assert f"Successfully added/updated GeoDataFrame for layer: '{layer_name}'" in caplog.text

        retrieved_gdf = service_real_logger.get_gdf(layer_name)
        assert retrieved_gdf is gdf # Check for object identity

    def test_add_gdf_invalid_type_raises_data_source_error(self, service_real_logger: DataSourceService, caplog):
        """Negative Test: Adding non-GDF type raises DataSourceError and logs error."""
        not_a_gdf = "this is a string"
        layer_name = "invalid_layer"

        with caplog.at_level("ERROR"):
            with pytest.raises(DataSourceError, match=f"Invalid type for add_gdf. Expected GeoDataFrame, got <class 'str'> for layer '{layer_name}'."):
                service_real_logger.add_gdf(not_a_gdf, layer_name)

        assert f"Attempted to add a non-GeoDataFrame object for layer '{layer_name}'" in caplog.text

    def test_add_gdf_overwrite_logs_warning(self, service_real_logger: DataSourceService, caplog):
        """Business Outcome: Overwriting an existing GDF logs a warning."""
        gdf1 = gpd.GeoDataFrame({'geometry': [Point(1,1)]})
        gdf2 = gpd.GeoDataFrame({'geometry': [Point(2,2)]})
        layer_name = "overwritten_layer"

        service_real_logger.add_gdf(gdf1, layer_name) # Initial add
        caplog.clear() # Clear logs before the overwrite action

        with caplog.at_level("WARNING"):
            service_real_logger.add_gdf(gdf2, layer_name) # Overwrite

        assert f"Overwriting existing GeoDataFrame for layer: '{layer_name}'" in caplog.text
        assert service_real_logger.get_gdf(layer_name) is gdf2

    def test_get_gdf_nonexistent_layer_raises_data_source_error(self, service_real_logger: DataSourceService, caplog):
        """Negative Test: Getting a non-existent layer raises DataSourceError and logs error."""
        layer_name = "non_existent_layer"
        with caplog.at_level("ERROR"):
            with pytest.raises(DataSourceError, match=f"Layer '{layer_name}' not found in DataSourceService."):
                service_real_logger.get_gdf(layer_name)

        assert f"Layer '{layer_name}' not found in DataSourceService." in caplog.text

    @pytest.mark.parametrize("invalid_layer_name", [None, ""])
    def test_add_gdf_none_or_empty_layer_name_raises_error(self, service_real_logger: DataSourceService, sample_gdf: gpd.GeoDataFrame, invalid_layer_name, caplog):
        """Negative Test: None or empty layer_name for add_gdf raises DataSourceError."""
        # Service should validate layer_name before adding to dict
        with caplog.at_level("ERROR"):
            with pytest.raises(DataSourceError, match="Layer name cannot be None or empty."):
                service_real_logger.add_gdf(sample_gdf, invalid_layer_name) # type: ignore
        # Check for specific log if validation is added and logs
        assert "Layer name cannot be None or empty." in caplog.text

    @pytest.mark.parametrize("invalid_layer_name", [None, ""])
    def test_get_gdf_none_or_empty_layer_name_raises_error(self, service_real_logger: DataSourceService, invalid_layer_name, caplog):
        """Negative Test: None or empty layer_name for get_gdf raises DataSourceError or KeyError."""
        # Service should validate layer_name or dict access will raise KeyError
        with caplog.at_level("ERROR"):
            with pytest.raises((DataSourceError, KeyError)):
                service_real_logger.get_gdf(invalid_layer_name) # type: ignore
        # Existing error for non-existent layer is DataSourceError wrapping KeyError
        # If validation is added, it might raise a more specific DataSourceError before KeyError
        if invalid_layer_name is None:
            assert "Layer name cannot be None" in caplog.text or "Layer 'None' not found" in caplog.text
        else: # Empty string
            assert "Layer name cannot be empty" in caplog.text or "Layer '' not found" in caplog.text
