import pytest
from unittest.mock import Mock, call, MagicMock # Added MagicMock
from ezdxf.document import Drawing

from src.interfaces.dxf_adapter_interface import IDXFAdapter
# from src.interfaces.logging_service_interface import ILoggingService # Will use real LoggingService
from src.services.logging_service import LoggingService # REAL SERVICE
from src.services.dxf_resource_manager_service import DXFResourceManagerService
from src.domain.style_models import LayerStyleProperties, TextStyleProperties
from src.domain.exceptions import DXFProcessingError

# --- REAL SERVICE FIXTURES ---
@pytest.fixture
def real_logger_service() -> LoggingService:
    """Use REAL logging service."""
    return LoggingService()

# --- FOCUSED MOCK FIXTURES ---
@pytest.fixture
def mock_dxf_adapter() -> Mock:
    adapter = Mock(spec=IDXFAdapter)
    adapter.is_available.return_value = True # Default to available
    # Configure specific mock behaviors for create_linetype and create_text_style per test if needed
    # e.g., adapter.create_linetype.return_value = None (or a mock linetype object if service used it)
    # e.g., adapter.create_text_style.return_value = None (or a mock text style object)
    return adapter

@pytest.fixture
def mock_drawing() -> Mock:
    """Provides a generic mock for an ezdxf.document.Drawing object."""
    return Mock(spec=Drawing)

# --- SERVICE UNDER TEST FIXTURE ---
@pytest.fixture
def resource_manager_real_logger(mock_dxf_adapter: Mock, real_logger_service: LoggingService) -> DXFResourceManagerService:
    """Instantiate DXFResourceManagerService with a REAL logger and a MOCKED adapter."""
    return DXFResourceManagerService(dxf_adapter=mock_dxf_adapter, logger_service=real_logger_service)

# Simplified fixture name for use in tests
@pytest.fixture
def manager(resource_manager_real_logger: DXFResourceManagerService) -> DXFResourceManagerService:
    return resource_manager_real_logger


class TestEnsureLinetype:
    """Tests for the ensure_linetype method."""

    def test_adapter_unavailable_logs_warning_and_skips(self, real_logger_service: LoggingService, caplog):
        """Business Outcome: If adapter is unavailable, logs warning and does not attempt creation."""
        mock_dxf_adapter_unavailable = Mock(spec=IDXFAdapter)
        mock_dxf_adapter_unavailable.is_available.return_value = False
        # Use caplog from pytest to capture log messages from the REAL logger
        service = DXFResourceManagerService(mock_dxf_adapter_unavailable, real_logger_service)

        props = LayerStyleProperties(linetype="ANYLINE_WILL_DO")
        drawing_mock = Mock(spec=Drawing)

        with caplog.at_level("WARNING", logger="src.services.dxf_resource_manager_service"):
            service.ensure_linetype(drawing_mock, props)

        assert "DXF adapter not available. Skipping linetype creation." in caplog.text
        mock_dxf_adapter_unavailable.create_linetype.assert_not_called()

    def test_none_props_or_linetype_name_skips_creation(self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
        """Business Outcome: No adapter call if LayerStyleProperties or linetype name is None."""
        manager.ensure_linetype(mock_drawing, None)
        mock_dxf_adapter.create_linetype.assert_not_called()

        props_no_linetype = LayerStyleProperties(linetype=None)
        manager.ensure_linetype(mock_drawing, props_no_linetype)
        mock_dxf_adapter.create_linetype.assert_not_called() # Should still be 0 calls total

    @pytest.mark.parametrize("std_ltype", ["BYLAYER", "BYBLOCK", "CONTINUOUS", "bylayer", "continuous"])
    def test_standard_linetypes_are_skipped(self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, std_ltype: str):
        """Business Outcome: Standard DXF linetypes are recognized and skipped (assumed to exist)."""
        props = LayerStyleProperties(linetype=std_ltype)
        manager.ensure_linetype(mock_drawing, props)
        mock_dxf_adapter.create_linetype.assert_not_called()

    def test_common_dashed_linetype_calls_adapter_with_correct_pattern(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: 'DASHED' linetype uses predefined common pattern for adapter call."""
        props = LayerStyleProperties(linetype="DASHED")
        manager.ensure_linetype(mock_drawing, props)
        # VERIFY: Correct parameters passed to the adapter mock
        mock_dxf_adapter.create_linetype.assert_called_once_with(
            doc=mock_drawing,
            ltype_name="DASHED",
            pattern=[1.2, -0.7],
            description="Dashed ----"
        )

    def test_custom_linetype_with_pattern_uses_provided_pattern(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Custom linetype with a defined pattern uses that pattern for adapter call."""
        custom_pattern = [0.5, -0.25, 0.0, -0.25] # Example custom pattern
        props = LayerStyleProperties(linetype="MY_CUSTOM_LINE", linetype_pattern=custom_pattern)
        manager.ensure_linetype(mock_drawing, props)
        # VERIFY: Correct parameters, including the custom pattern, passed to adapter
        mock_dxf_adapter.create_linetype.assert_called_once_with(
            doc=mock_drawing,
            ltype_name="MY_CUSTOM_LINE",
            pattern=custom_pattern,
            description="Custom linetype MY_CUSTOM_LINE from style pattern"
        )

    def test_unknown_custom_linetype_uses_default_pattern(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, real_logger_service: LoggingService, caplog
    ):
        """Business Outcome: Unknown custom linetype (no pattern) uses a default pattern and logs warning."""
        props = LayerStyleProperties(linetype="UNKNOWN_CUSTOM_LTYPE")
        with caplog.at_level("WARNING", logger="src.services.dxf_resource_manager_service"):
            manager.ensure_linetype(mock_drawing, props)

        # VERIFY: Logged warning about using default pattern
        assert "Linetype 'UNKNOWN_CUSTOM_LTYPE' is not a predefined common type and has no pattern in style. Creating with a default dashed pattern." in caplog.text
        # VERIFY: Adapter called with default pattern
        mock_dxf_adapter.create_linetype.assert_called_once_with(
            doc=mock_drawing,
            ltype_name="UNKNOWN_CUSTOM_LTYPE",
            pattern=[1.0, -0.5], # Service's default pattern
            description="Custom linetype UNKNOWN_CUSTOM_LTYPE (defaulted pattern)"
        )

    def test_adapter_error_during_linetype_creation_logs_error(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, real_logger_service: LoggingService, caplog
    ):
        """Business Outcome: If adapter fails to create linetype, an error is logged."""
        # Setup: Configure adapter mock to raise an error
        error_message = "Adapter failed during linetype creation"
        mock_dxf_adapter.create_linetype.side_effect = DXFProcessingError(error_message)

        props = LayerStyleProperties(linetype="FAILING_LINETYPE")

        with caplog.at_level("ERROR", logger="src.services.dxf_resource_manager_service"):
            manager.ensure_linetype(mock_drawing, props)

        # VERIFY: Error log contains relevant information
        assert f"Adapter failed to create/ensure linetype 'FAILING_LINETYPE': {error_message}" in caplog.text
        # VERIFY: Ensure create_linetype was actually called
        mock_dxf_adapter.create_linetype.assert_called_once()

    @pytest.mark.parametrize("empty_ltype_val", ["", "  ", "\t"])
    def test_empty_or_whitespace_linetype_name_skips_creation_logs_warning(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, caplog, empty_ltype_val: str
    ):
        """Business Outcome: Empty or whitespace linetype names are skipped and a warning is logged."""
        props = LayerStyleProperties(linetype=empty_ltype_val)
        with caplog.at_level("WARNING", logger="src.services.dxf_resource_manager_service"):
            manager.ensure_linetype(mock_drawing, props)

        assert f"Linetype name '{empty_ltype_val}' is invalid or effectively empty. Skipping." in caplog.text
        mock_dxf_adapter.create_linetype.assert_not_called()

    def test_invalid_linetype_pattern_type_falls_back_logs_warning(
        self,
        mock_dxf_adapter: MagicMock,
        real_logger_service: LoggingService,
        caplog: pytest.LogCaptureFixture
    ):
        """Business Outcome: Invalid (e.g. empty) linetype_pattern list falls back to default/common logic and logs warning."""
        # Pass an empty list for linetypePattern, which is valid for the model, but should be handled by service logic
        layer_props_empty_pattern_list = LayerStyleProperties(linetype="CUSTOM_EMPTY_PATTERN", linetypePattern=[])
        service = DXFResourceManagerService(mock_dxf_adapter, real_logger_service)

        with caplog.at_level("WARNING"):
            service.ensure_linetype(mock_dxf_adapter.doc, layer_props_empty_pattern_list)

        mock_dxf_adapter.create_linetype.assert_called_once_with(
            doc=mock_dxf_adapter.doc,
            ltype_name="CUSTOM_EMPTY_PATTERN",
            pattern=[1.0, -0.5],  # Default pattern from fallback logic
            description="Custom linetype CUSTOM_EMPTY_PATTERN (defaulted pattern)"
        )
        # Check for the specific warning when the pattern list is empty
        assert f"Linetype pattern for 'CUSTOM_EMPTY_PATTERN' is invalid (not a list or empty). Proceeding with default/common linetype logic." in caplog.text

    def test_adapter_unexpected_exception_during_linetype_creation_logs_error(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, caplog
    ):
        """Business Outcome: If adapter raises an unexpected Exception, it is caught and logged."""
        error_message = "Adapter blew up unexpectedly"
        mock_dxf_adapter.create_linetype.side_effect = Exception(error_message)
        props = LayerStyleProperties(linetype="FAILING_UNEXPECTEDLY")

        with caplog.at_level("ERROR", logger="src.services.dxf_resource_manager_service"):
            manager.ensure_linetype(mock_drawing, props)

        assert f"Unexpected error creating linetype 'FAILING_UNEXPECTEDLY' via adapter: {error_message}" in caplog.text
        mock_dxf_adapter.create_linetype.assert_called_once()


class TestEnsureTextStyle:
    """Tests for the ensure_text_style method."""

    def test_adapter_unavailable_logs_warning_returns_none(self, real_logger_service: LoggingService, caplog):
        """Business Outcome: If adapter is unavailable, logs warning, returns None, skips creation."""
        mock_dxf_adapter_unavailable = Mock(spec=IDXFAdapter)
        mock_dxf_adapter_unavailable.is_available.return_value = False
        service = DXFResourceManagerService(mock_dxf_adapter_unavailable, real_logger_service)

        props = TextStyleProperties(font="AnyFontWillDo")
        drawing_mock = Mock(spec=Drawing)

        result = None
        with caplog.at_level("WARNING", logger="src.services.dxf_resource_manager_service"):
            result = service.ensure_text_style(drawing_mock, props)

        assert "DXF adapter not available. Skipping text style creation." in caplog.text
        assert result is None
        mock_dxf_adapter_unavailable.create_text_style.assert_not_called()

    def test_none_props_or_font_returns_none_skips_creation(self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock):
        """Business Outcome: No adapter call and returns None if TextStyleProperties or font is None."""
        assert manager.ensure_text_style(mock_drawing, None) is None
        mock_dxf_adapter.create_text_style.assert_not_called()

        props_no_font = TextStyleProperties(font=None)
        assert manager.ensure_text_style(mock_drawing, props_no_font) is None
        mock_dxf_adapter.create_text_style.assert_not_called() # Still 0 calls total

    def test_valid_font_returns_stylename_calls_adapter(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Valid font name leads to adapter call with generated style name, and style name is returned."""
        props = TextStyleProperties(font="Arial")
        expected_style_name = "Style_Arial" # Based on service's internal naming logic

        returned_style_name = manager.ensure_text_style(mock_drawing, props)

        assert returned_style_name == expected_style_name
        # VERIFY: Adapter called with correct generated name and original font name
        mock_dxf_adapter.create_text_style.assert_called_once_with(
            doc=mock_drawing,
            style_name=expected_style_name,
            font_name="Arial"
        )

    def test_font_with_special_chars_generates_valid_stylename(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock
    ):
        """Business Outcome: Font names with spaces/special chars are sanitized for the style name."""
        props = TextStyleProperties(font="Times New Roman Italic")
        # Service logic: "Style_" + replaces non-alphanum with "_"
        expected_style_name = "Style_Times_New_Roman_Italic"

        returned_style_name = manager.ensure_text_style(mock_drawing, props)
        assert returned_style_name == expected_style_name
        mock_dxf_adapter.create_text_style.assert_called_once_with(
            doc=mock_drawing,
            style_name=expected_style_name,
            font_name="Times New Roman Italic"
        )

    @pytest.mark.parametrize("invalid_font_val", [" ", "  ", "\t", "None"]) # "None" string is invalid
    def test_invalid_font_names_return_none_log_warning(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, real_logger_service: LoggingService, caplog, invalid_font_val:str
    ):
        """Business Outcome: Invalid font names (empty, whitespace, "None" string) return None and log warning."""
        props = TextStyleProperties(font=invalid_font_val)
        with caplog.at_level("WARNING", logger="src.services.dxf_resource_manager_service"):
            result = manager.ensure_text_style(mock_drawing, props)

        assert result is None
        assert f"Cannot derive a valid style name from font: '{invalid_font_val}'. Using default style." in caplog.text
        mock_dxf_adapter.create_text_style.assert_not_called()

    def test_adapter_error_during_text_style_creation_logs_error_returns_none(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, real_logger_service: LoggingService, caplog
    ):
        """Business Outcome: If adapter fails to create text style, an error is logged, and None is returned."""
        font_name = "ErrorFont"
        props = TextStyleProperties(font=font_name)
        expected_style_name = f"Style_{font_name}" # Based on service logic
        error_message = "Adapter failed during text style creation"
        mock_dxf_adapter.create_text_style.side_effect = DXFProcessingError(error_message)

        result = None
        with caplog.at_level("ERROR", logger="src.services.dxf_resource_manager_service"):
            result = manager.ensure_text_style(mock_drawing, props)

        assert result is None
        # VERIFY: Error log contains relevant information
        assert f"Adapter failed to create text style '{expected_style_name}' for font '{font_name}': {error_message}" in caplog.text
        # VERIFY: Ensure create_text_style was actually called
        mock_dxf_adapter.create_text_style.assert_called_once()

    def test_adapter_unexpected_exception_during_text_style_creation_logs_error_returns_none(
        self, manager: DXFResourceManagerService, mock_drawing: Mock, mock_dxf_adapter: Mock, caplog
    ):
        """Business Outcome: If adapter raises an unexpected Exception, it's caught, logged, returns None."""
        error_message = "Adapter text style creation blew up"
        mock_dxf_adapter.create_text_style.side_effect = Exception(error_message)
        props = TextStyleProperties(font="ExplodingFont")
        expected_style_name = "Style_ExplodingFont"

        returned_style_name = None
        with caplog.at_level("ERROR", logger="src.services.dxf_resource_manager_service"):
            returned_style_name = manager.ensure_text_style(mock_drawing, props)

        assert f"Unexpected error creating text style '{expected_style_name}' for 'ExplodingFont': {error_message}" in caplog.text
        assert returned_style_name is None
        mock_dxf_adapter.create_text_style.assert_called_once()
