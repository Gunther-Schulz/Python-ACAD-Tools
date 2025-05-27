import pytest
from unittest.mock import Mock, call # Import call
from ezdxf.document import Drawing

from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.logging_service_interface import ILoggingService
from src.services.dxf_resource_manager_service import DXFResourceManagerService
from src.domain.style_models import LayerStyleProperties, TextStyleProperties
from src.domain.exceptions import DXFProcessingError

@pytest.fixture
def mock_dxf_adapter() -> Mock:
    adapter = Mock(spec=IDXFAdapter)
    adapter.is_available.return_value = True
    return adapter

@pytest.fixture
def mock_logger_service() -> Mock:
    logger_service_mock = Mock(spec=ILoggingService) # Renamed to avoid conflict
    # Configure the mock logger that get_logger will return
    mock_actual_logger = Mock()
    logger_service_mock.get_logger.return_value = mock_actual_logger
    return logger_service_mock

@pytest.fixture
def mock_drawing() -> Mock:
    return Mock(spec=Drawing)

@pytest.fixture
def resource_manager(mock_dxf_adapter: Mock, mock_logger_service: Mock) -> DXFResourceManagerService:
    return DXFResourceManagerService(dxf_adapter=mock_dxf_adapter, logger_service=mock_logger_service)

# --- Tests for ensure_linetype ---
def test_ensure_linetype_none_props(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    resource_manager.ensure_linetype(mock_drawing, None)
    mock_dxf_adapter.create_linetype.assert_not_called()

def test_ensure_linetype_none_linetype_name(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = LayerStyleProperties(linetype=None)
    resource_manager.ensure_linetype(mock_drawing, props)
    mock_dxf_adapter.create_linetype.assert_not_called()

@pytest.mark.parametrize("std_ltype", ["BYLAYER", "BYBLOCK", "CONTINUOUS", "bylayer"])
def test_ensure_linetype_standard_types(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, std_ltype: str):
    props = LayerStyleProperties(linetype=std_ltype)
    resource_manager.ensure_linetype(mock_drawing, props)
    mock_dxf_adapter.create_linetype.assert_not_called()

def test_ensure_linetype_common_dashed(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = LayerStyleProperties(linetype="DASHED")
    resource_manager.ensure_linetype(mock_drawing, props)
    mock_dxf_adapter.create_linetype.assert_called_once_with(
        doc=mock_drawing,
        ltype_name="DASHED",
        pattern=[1.2, -0.7],
        description="Dashed ----"
    )

def test_ensure_linetype_custom_with_pattern(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    custom_pattern = [0.5, -0.25, 0.0, -0.25]
    props = LayerStyleProperties(linetype="MY_CUSTOM_LINE", linetype_pattern=custom_pattern)
    resource_manager.ensure_linetype(mock_drawing, props)
    mock_dxf_adapter.create_linetype.assert_called_once_with(
        doc=mock_drawing,
        ltype_name="MY_CUSTOM_LINE",
        pattern=custom_pattern,
        description="Custom linetype MY_CUSTOM_LINE from style pattern"
    )

def test_ensure_linetype_custom_unknown_defaulted(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = LayerStyleProperties(linetype="UNKNOWN_CUSTOM")
    resource_manager.ensure_linetype(mock_drawing, props)
    mock_dxf_adapter.create_linetype.assert_called_once_with(
        doc=mock_drawing,
        ltype_name="UNKNOWN_CUSTOM",
        pattern=[1.0, -0.5], # Default pattern
        description="Custom linetype UNKNOWN_CUSTOM (defaulted pattern)"
    )

def test_ensure_linetype_adapter_error(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, mock_logger_service: Mock):
    mock_dxf_adapter.create_linetype.side_effect = DXFProcessingError("Adapter boom")
    props = LayerStyleProperties(linetype="ERROR_LINE")
    resource_manager.ensure_linetype(mock_drawing, props)
    # Ensure logger was called with error
    mock_logger_service.get_logger().error.assert_called_once()
    assert "Adapter failed to create/ensure linetype 'ERROR_LINE'" in mock_logger_service.get_logger().error.call_args[0][0]


# --- Tests for ensure_text_style ---
def test_ensure_text_style_none_props(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    assert resource_manager.ensure_text_style(mock_drawing, None) is None
    mock_dxf_adapter.create_text_style.assert_not_called()

def test_ensure_text_style_none_font(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = TextStyleProperties(font=None)
    assert resource_manager.ensure_text_style(mock_drawing, props) is None
    mock_dxf_adapter.create_text_style.assert_not_called()

def test_ensure_text_style_valid_font(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = TextStyleProperties(font="Arial")
    expected_style_name = "Style_Arial"

    style_name = resource_manager.ensure_text_style(mock_drawing, props)
    assert style_name == expected_style_name
    mock_dxf_adapter.create_text_style.assert_called_once_with(
        doc=mock_drawing,
        style_name=expected_style_name,
        font_name="Arial"
    )

def test_ensure_text_style_font_with_special_chars(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = TextStyleProperties(font="Times New Roman")
    expected_style_name = "Style_Times_New_Roman"
    style_name = resource_manager.ensure_text_style(mock_drawing, props)
    assert style_name == expected_style_name
    mock_dxf_adapter.create_text_style.assert_called_once_with(
        doc=mock_drawing,
        style_name=expected_style_name,
        font_name="Times New Roman"
    )

def test_ensure_text_style_invalid_font_name_empty(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = TextStyleProperties(font=" ") # Empty after strip
    assert resource_manager.ensure_text_style(mock_drawing, props) is None
    mock_dxf_adapter.create_text_style.assert_not_called()

def test_ensure_text_style_invalid_font_name_none_str(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
    props = TextStyleProperties(font="None") # "None" string
    assert resource_manager.ensure_text_style(mock_drawing, props) is None
    mock_dxf_adapter.create_text_style.assert_not_called()

def test_ensure_text_style_adapter_error(resource_manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, mock_logger_service: Mock):
    mock_dxf_adapter.create_text_style.side_effect = DXFProcessingError("Adapter style boom")
    props = TextStyleProperties(font="ErrorFont")
    expected_style_name = "Style_ErrorFont"
    assert resource_manager.ensure_text_style(mock_drawing, props) is None
    mock_logger_service.get_logger().error.assert_called_once()
    assert f"Adapter failed to create text style '{expected_style_name}'" in mock_logger_service.get_logger().error.call_args[0][0]

def test_dxf_adapter_not_available_ensure_linetype(mock_logger_service: Mock):
    mock_dxf_adapter_unavailable = Mock(spec=IDXFAdapter)
    mock_dxf_adapter_unavailable.is_available.return_value = False
    service = DXFResourceManagerService(mock_dxf_adapter_unavailable, mock_logger_service)

    props = LayerStyleProperties(linetype="ANYLINE")
    service.ensure_linetype(Mock(spec=Drawing), props)

    mock_dxf_adapter_unavailable.create_linetype.assert_not_called()
    mock_logger_service.get_logger().warning.assert_any_call("DXF adapter not available. Skipping linetype creation.")

def test_dxf_adapter_not_available_ensure_text_style(mock_logger_service: Mock):
    mock_dxf_adapter_unavailable = Mock(spec=IDXFAdapter)
    mock_dxf_adapter_unavailable.is_available.return_value = False
    service = DXFResourceManagerService(mock_dxf_adapter_unavailable, mock_logger_service)

    props = TextStyleProperties(font="AnyFont")
    result = service.ensure_text_style(Mock(spec=Drawing), props)

    assert result is None
    mock_dxf_adapter_unavailable.create_text_style.assert_not_called()
    mock_logger_service.get_logger().warning.assert_any_call("DXF adapter not available. Skipping text style creation.")
