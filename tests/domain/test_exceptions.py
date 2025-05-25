"""Comprehensive tests for domain exception classes."""
import pytest
from typing import List, Optional

from src.domain.exceptions import (
    ApplicationBaseException,
    ConfigError,
    ConfigValidationError,
    ProcessingError,
    DXFProcessingError,
    DXFGeometryConversionError,
    GeometryError,
    GdfValidationError,
    DataSourceError,
    PathResolutionError
)


class TestApplicationBaseException:
    """Test cases for ApplicationBaseException base class."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_base_exception_creation(self):
        """Test creating base application exception."""
        exc = ApplicationBaseException("Test message")
        assert str(exc) == "Test message"
        assert isinstance(exc, Exception)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_base_exception_inheritance(self):
        """Test that all custom exceptions inherit from ApplicationBaseException."""
        exceptions_to_test = [
            ConfigError,
            ProcessingError,
            PathResolutionError
        ]

        for exc_class in exceptions_to_test:
            exc = exc_class("Test message")
            assert isinstance(exc, ApplicationBaseException)
            assert isinstance(exc, Exception)


class TestConfigError:
    """Test cases for ConfigError and related exceptions."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_error_creation(self):
        """Test creating ConfigError."""
        exc = ConfigError("Configuration error occurred")
        assert str(exc) == "Configuration error occurred"
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_validation_error_basic(self):
        """Test basic ConfigValidationError creation."""
        exc = ConfigValidationError("Validation failed")
        assert str(exc) == "Validation failed"
        assert exc.field_name is None
        assert exc.config_file is None
        assert exc.validation_errors == []

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_validation_error_with_details(self):
        """Test ConfigValidationError with detailed information."""
        validation_errors = ["Field 'name' is required", "Field 'path' must be relative"]
        exc = ConfigValidationError(
            message="Multiple validation errors",
            field_name="project_config",
            config_file="project.yaml",
            validation_errors=validation_errors
        )

        assert exc.field_name == "project_config"
        assert exc.config_file == "project.yaml"
        assert exc.validation_errors == validation_errors

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_validation_error_string_representation(self):
        """Test ConfigValidationError string representation with all details."""
        validation_errors = ["Error 1", "Error 2"]
        exc = ConfigValidationError(
            message="Main error message",
            field_name="test_field",
            config_file="test.yaml",
            validation_errors=validation_errors
        )

        error_str = str(exc)
        assert "Main error message" in error_str
        assert "Config file: test.yaml" in error_str
        assert "Field: test_field" in error_str
        assert "Validation errors: Error 1; Error 2" in error_str

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_validation_error_partial_details(self):
        """Test ConfigValidationError with only some details provided."""
        # Only field name
        exc1 = ConfigValidationError("Error", field_name="test_field")
        error_str1 = str(exc1)
        assert "Field: test_field" in error_str1
        assert "Config file:" not in error_str1

        # Only config file
        exc2 = ConfigValidationError("Error", config_file="test.yaml")
        error_str2 = str(exc2)
        assert "Config file: test.yaml" in error_str2
        assert "Field:" not in error_str2

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_gdf_validation_error(self):
        """Test GdfValidationError."""
        exc = GdfValidationError("GeoDataFrame validation failed")
        assert str(exc) == "GeoDataFrame validation failed"
        assert isinstance(exc, ConfigError)
        assert isinstance(exc, ApplicationBaseException)


class TestProcessingErrors:
    """Test cases for processing-related exceptions."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_processing_error_creation(self):
        """Test creating ProcessingError."""
        exc = ProcessingError("Processing failed")
        assert str(exc) == "Processing failed"
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.dxf
    @pytest.mark.fast
    def test_dxf_processing_error(self):
        """Test DXFProcessingError."""
        exc = DXFProcessingError("DXF processing failed")
        assert str(exc) == "DXF processing failed"
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.dxf
    @pytest.mark.fast
    def test_dxf_geometry_conversion_error(self):
        """Test DXFGeometryConversionError."""
        exc = DXFGeometryConversionError("Geometry conversion failed")
        assert str(exc) == "Geometry conversion failed"
        assert isinstance(exc, DXFProcessingError)
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.geometry
    @pytest.mark.fast
    def test_geometry_error(self):
        """Test GeometryError."""
        exc = GeometryError("Geometry operation failed")
        assert str(exc) == "Geometry operation failed"
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_data_source_error(self):
        """Test DataSourceError."""
        exc = DataSourceError("Data source access failed")
        assert str(exc) == "Data source access failed"
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, ApplicationBaseException)


class TestPathResolutionError:
    """Test cases for PathResolutionError."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_basic(self):
        """Test basic PathResolutionError creation."""
        exc = PathResolutionError("Path resolution failed")
        assert str(exc) == "Path resolution failed"
        assert exc.alias_reference is None
        assert exc.project_name is None
        assert isinstance(exc, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_with_details(self):
        """Test PathResolutionError with detailed information."""
        exc = PathResolutionError(
            message="Alias not found",
            alias_reference="@data.input",
            project_name="test_project"
        )

        assert exc.alias_reference == "@data.input"
        assert exc.project_name == "test_project"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_string_representation(self):
        """Test PathResolutionError string representation with all details."""
        exc = PathResolutionError(
            message="Alias resolution failed",
            alias_reference="@config.main",
            project_name="my_project"
        )

        error_str = str(exc)
        assert "Alias resolution failed" in error_str
        assert "Project: my_project" in error_str
        assert "Alias reference: @config.main" in error_str

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_partial_details(self):
        """Test PathResolutionError with only some details provided."""
        # Only alias reference
        exc1 = PathResolutionError("Error", alias_reference="@data.test")
        error_str1 = str(exc1)
        assert "Alias reference: @data.test" in error_str1
        assert "Project:" not in error_str1

        # Only project name
        exc2 = PathResolutionError("Error", project_name="test_project")
        error_str2 = str(exc2)
        assert "Project: test_project" in error_str2
        assert "Alias reference:" not in error_str2

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_no_details(self):
        """Test PathResolutionError with no additional details."""
        exc = PathResolutionError("Simple error message")
        error_str = str(exc)
        assert error_str == "Simple error message"
        assert "Project:" not in error_str
        assert "Alias reference:" not in error_str


class TestExceptionHierarchy:
    """Test cases for exception inheritance hierarchy."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_exception_hierarchy_structure(self):
        """Test that exception hierarchy is correctly structured."""
        # Test inheritance chains
        assert issubclass(ConfigError, ApplicationBaseException)
        assert issubclass(ConfigValidationError, ConfigError)
        assert issubclass(GdfValidationError, ConfigError)

        assert issubclass(ProcessingError, ApplicationBaseException)
        assert issubclass(DXFProcessingError, ProcessingError)
        assert issubclass(DXFGeometryConversionError, DXFProcessingError)
        assert issubclass(GeometryError, ProcessingError)
        assert issubclass(DataSourceError, ProcessingError)

        assert issubclass(PathResolutionError, ApplicationBaseException)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_exception_catching_by_base_class(self):
        """Test that exceptions can be caught by their base classes."""
        # Test catching by ApplicationBaseException
        exceptions_to_test = [
            ConfigError("test"),
            ConfigValidationError("test"),
            ProcessingError("test"),
            DXFProcessingError("test"),
            PathResolutionError("test")
        ]

        for exc in exceptions_to_test:
            try:
                raise exc
            except ApplicationBaseException:
                pass  # Should catch all
            except Exception:
                pytest.fail(f"Exception {type(exc)} not caught by ApplicationBaseException")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_exception_catching_by_intermediate_class(self):
        """Test that exceptions can be caught by intermediate base classes."""
        # Test catching DXF exceptions by ProcessingError
        dxf_exceptions = [
            DXFProcessingError("test"),
            DXFGeometryConversionError("test")
        ]

        for exc in dxf_exceptions:
            try:
                raise exc
            except ProcessingError:
                pass  # Should catch DXF-related processing errors
            except Exception:
                pytest.fail(f"Exception {type(exc)} not caught by ProcessingError")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_exception_specific_catching(self):
        """Test that specific exceptions can be caught individually."""
        specific_exceptions = [
            (ConfigValidationError("test"), ConfigValidationError),
            (DXFGeometryConversionError("test"), DXFGeometryConversionError),
            (PathResolutionError("test"), PathResolutionError)
        ]

        for exc, exc_type in specific_exceptions:
            try:
                raise exc
            except exc_type:
                pass  # Should catch the specific type
            except Exception:
                pytest.fail(f"Exception {type(exc)} not caught by {exc_type}")


class TestExceptionUsagePatterns:
    """Test cases for common exception usage patterns."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_config_validation_error_usage_pattern(self):
        """Test typical usage pattern for ConfigValidationError."""
        def validate_config(config_data: dict) -> None:
            """Example validation function that raises ConfigValidationError."""
            errors = []

            if 'name' not in config_data:
                errors.append("Field 'name' is required")

            if 'path' in config_data and config_data['path'].startswith('/'):
                errors.append("Field 'path' must be relative")

            if errors:
                raise ConfigValidationError(
                    message="Configuration validation failed",
                    field_name="project_config",
                    config_file="test.yaml",
                    validation_errors=errors
                )

        # Test successful validation
        valid_config = {"name": "test", "path": "relative/path"}
        validate_config(valid_config)  # Should not raise

        # Test validation failure
        invalid_config = {"path": "/absolute/path"}
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(invalid_config)

        exc = exc_info.value
        assert exc.field_name == "project_config"
        assert exc.config_file == "test.yaml"
        assert len(exc.validation_errors) == 2
        assert "Field 'name' is required" in exc.validation_errors
        assert "Field 'path' must be relative" in exc.validation_errors

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_path_resolution_error_usage_pattern(self):
        """Test typical usage pattern for PathResolutionError."""
        def resolve_alias(alias_ref: str, project: str) -> str:
            """Example function that raises PathResolutionError."""
            if not alias_ref.startswith('@'):
                raise PathResolutionError(
                    message="Invalid alias reference format",
                    alias_reference=alias_ref,
                    project_name=project
                )

            # Simulate alias not found
            if alias_ref == "@nonexistent":
                raise PathResolutionError(
                    message="Alias not found",
                    alias_reference=alias_ref,
                    project_name=project
                )

            return "/resolved/path"

        # Test successful resolution
        result = resolve_alias("@valid.alias", "test_project")
        assert result == "/resolved/path"

        # Test invalid format
        with pytest.raises(PathResolutionError) as exc_info:
            resolve_alias("invalid_format", "test_project")

        exc = exc_info.value
        assert "Invalid alias reference format" in str(exc)
        assert exc.alias_reference == "invalid_format"
        assert exc.project_name == "test_project"

        # Test alias not found
        with pytest.raises(PathResolutionError) as exc_info:
            resolve_alias("@nonexistent", "test_project")

        exc = exc_info.value
        assert "Alias not found" in str(exc)
        assert exc.alias_reference == "@nonexistent"
