"""Tests for configuration validation functionality."""
import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

from src.domain.config_validation import (
    ConfigValidationService,
    ConfigValidationError,
    ConfigValidators,
    ValidationRegistry,
    CrossFieldValidator
)


class TestConfigValidators:
    """Test cases for individual validator functions."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_buffer_distance_valid(self):
        """Test valid buffer distance validation."""
        result = ConfigValidators.validate_buffer_distance(100.0)
        assert result == 100.0

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_buffer_distance_negative(self):
        """Test negative buffer distance validation."""
        with pytest.raises(ValueError, match="cannot be negative"):
            ConfigValidators.validate_buffer_distance(-10.0)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_buffer_distance_too_large(self):
        """Test buffer distance that's too large."""
        with pytest.raises(ValueError, match="exceeds recommended maximum"):
            ConfigValidators.validate_buffer_distance(20000.0)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_crs_epsg(self):
        """Test EPSG CRS validation."""
        result = ConfigValidators.validate_crs("EPSG:4326")
        assert result == "EPSG:4326"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_crs_invalid_epsg(self):
        """Test invalid EPSG code."""
        with pytest.raises(ValueError, match="outside valid range"):
            ConfigValidators.validate_crs("EPSG:99999")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_crs_proj4(self):
        """Test PROJ4 CRS validation."""
        result = ConfigValidators.validate_crs("+proj=utm +zone=33 +datum=WGS84")
        assert result == "+proj=utm +zone=33 +datum=WGS84"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_crs_invalid(self):
        """Test invalid CRS format."""
        with pytest.raises(ValueError, match="Invalid CRS"):
            ConfigValidators.validate_crs("invalid_crs")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_aci_color_integer(self):
        """Test ACI color validation with integer."""
        result = ConfigValidators.validate_aci_color(7)
        assert result == 7

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_aci_color_string(self):
        """Test ACI color validation with string."""
        result = ConfigValidators.validate_aci_color("red")
        assert result == "red"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_aci_color_out_of_range(self):
        """Test ACI color validation with out of range value."""
        with pytest.raises(ValueError, match="must be between"):
            ConfigValidators.validate_aci_color(300)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_dxf_version_valid(self):
        """Test valid DXF version."""
        result = ConfigValidators.validate_dxf_version("R2010")
        assert result == "R2010"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_dxf_version_invalid(self):
        """Test invalid DXF version."""
        with pytest.raises(ValueError, match="Invalid DXF version"):
            ConfigValidators.validate_dxf_version("R9999")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_export_format_valid(self):
        """Test valid export format."""
        result = ConfigValidators.validate_export_format("dxf")
        assert result == "dxf"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_export_format_invalid(self):
        """Test invalid export format."""
        with pytest.raises(ValueError, match="Invalid export format"):
            ConfigValidators.validate_export_format("invalid")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_positive_number_valid(self):
        """Test positive number validation."""
        result = ConfigValidators.validate_positive_number(5.5)
        assert result == 5.5

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_positive_number_invalid(self):
        """Test positive number validation with negative value."""
        with pytest.raises(ValueError, match="must be positive"):
            ConfigValidators.validate_positive_number(-1.0)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_percentage_valid(self):
        """Test percentage validation."""
        result = ConfigValidators.validate_percentage(0.75)
        assert result == 0.75

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_percentage_invalid(self):
        """Test percentage validation with out of range value."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            ConfigValidators.validate_percentage(1.5)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_suggest_closest_match_found(self):
        """Test closest match suggestion when match is found."""
        valid_keys = {"name", "type", "style", "operations"}
        result = ConfigValidators.suggest_closest_match("nam", valid_keys)
        assert result == "name"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_suggest_closest_match_not_found(self):
        """Test closest match suggestion when no close match exists."""
        valid_keys = {"name", "type", "style", "operations"}
        result = ConfigValidators.suggest_closest_match("xyz", valid_keys)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_file_path_basic(self):
        """Test basic file path validation."""
        result = ConfigValidators.validate_file_path("test.geojson", "geojson")
        assert result == "test.geojson"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_file_path_wrong_extension(self):
        """Test file path validation with wrong extension."""
        with pytest.raises(ValueError, match="must have one of these extensions"):
            ConfigValidators.validate_file_path("test.txt", "geojson")


class TestCrossFieldValidator:
    """Test cases for cross-field validation functions."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_output_paths_consistency_dxf(self):
        """Test output paths consistency for DXF format."""
        config = {
            "exportFormat": "dxf",
            "dxf": {"outputPath": "output.dxf"}
        }
        result = CrossFieldValidator.validate_output_paths_consistency(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_output_paths_consistency_dxf_missing(self):
        """Test output paths consistency for DXF format with missing path."""
        config = {"exportFormat": "dxf"}
        with pytest.raises(ValueError, match="requires dxf.outputPath"):
            CrossFieldValidator.validate_output_paths_consistency(config)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_operation_dependencies_circular(self):
        """Test operation dependencies validation with circular reference."""
        operations = [{"type": "buffer", "layers": ["test_layer"]}]
        with pytest.raises(ValueError, match="circular dependency"):
            CrossFieldValidator.validate_operation_dependencies(operations, "test_layer")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_operation_dependencies_valid(self):
        """Test operation dependencies validation with valid operations."""
        operations = [{"type": "buffer", "distance": 100}]
        result = CrossFieldValidator.validate_operation_dependencies(operations, "test_layer")
        assert result == operations


class TestConfigValidationService:
    """Test cases for the ConfigValidationService class."""

    @pytest.fixture
    def validation_service(self):
        """Create a ConfigValidationService instance for testing."""
        return ConfigValidationService()

    @pytest.fixture
    def temp_directory(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validation_service_initialization(self, validation_service):
        """Test ConfigValidationService initialization."""
        assert validation_service is not None
        assert validation_service.validation_errors == []
        assert validation_service.validation_warnings == []

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_project_config_empty(self, validation_service):
        """Test validation of empty project configuration."""
        config = {}
        result = validation_service.validate_project_config(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_project_config_with_main(self, validation_service):
        """Test validation of project configuration with main settings."""
        config = {
            "main": {
                "crs": "EPSG:4326",
                "exportFormat": "dxf",
                "dxf": {"outputPath": "output.dxf"}
            }
        }
        result = validation_service.validate_project_config(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_project_config_invalid_crs(self, validation_service):
        """Test validation of project configuration with invalid CRS."""
        config = {
            "main": {"crs": "invalid_crs"}
        }
        with pytest.raises(ConfigValidationError):
            validation_service.validate_project_config(config)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_geometry_layers_basic(self, validation_service, temp_directory):
        """Test validation of basic geometry layers."""
        # Create a temporary test file
        test_file = Path(temp_directory) / "test.geojson"
        test_file.write_text('{"type": "FeatureCollection", "features": []}')

        # Set base path to temp directory so file can be found
        validation_service.base_path = temp_directory

        config = {
            "geomLayers": [
                {
                    "name": "test_layer",
                    "geojsonFile": "test.geojson"
                }
            ]
        }
        result = validation_service.validate_project_config(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_geometry_layers_duplicate_names(self, validation_service):
        """Test validation of geometry layers with duplicate names."""
        config = {
            "geomLayers": [
                {"name": "test_layer", "geojsonFile": "test1.geojson"},
                {"name": "test_layer", "geojsonFile": "test2.geojson"}
            ]
        }
        with pytest.raises(ConfigValidationError):
            validation_service.validate_project_config(config)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_geometry_layers_no_data_source(self, validation_service):
        """Test validation of geometry layers without data source."""
        config = {
            "geomLayers": [
                {"name": "test_layer"}
            ]
        }
        with pytest.raises(ConfigValidationError):
            validation_service.validate_project_config(config)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_geometry_layers_with_operations(self, validation_service):
        """Test validation of geometry layers with operations."""
        config = {
            "geomLayers": [
                {
                    "name": "test_layer",
                    "operations": [
                        {"type": "buffer", "distance": 100}
                    ]
                }
            ]
        }
        result = validation_service.validate_project_config(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_path_aliases_basic(self, validation_service):
        """Test validation of basic path aliases."""
        config = {
            "pathAliases": {
                "data": "/path/to/data",
                "output": "/path/to/output"
            }
        }
        result = validation_service.validate_project_config(config)
        assert result == config

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_validate_path_aliases_with_warnings(self, validation_service):
        """Test validation of path aliases that generate warnings."""
        config = {
            "pathAliases": {
                "data": "../data",  # Should generate warning about '..'
                "output": "/path/to/output"
            }
        }
        result = validation_service.validate_project_config(config)
        assert result == config
        assert len(validation_service.validation_warnings) > 0
        assert any(".." in warning for warning in validation_service.validation_warnings)


class TestValidationRegistry:
    """Test cases for ValidationRegistry constants and patterns."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_valid_extensions_geojson(self):
        """Test that GeoJSON extensions are properly defined."""
        assert '.geojson' in ValidationRegistry.VALID_EXTENSIONS['geojson']
        assert '.json' in ValidationRegistry.VALID_EXTENSIONS['geojson']

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_valid_dxf_versions(self):
        """Test that DXF versions are properly defined."""
        assert 'R2010' in ValidationRegistry.VALID_DXF_VERSIONS
        assert 'R2018' in ValidationRegistry.VALID_DXF_VERSIONS

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_valid_operation_types(self):
        """Test that operation types are properly defined."""
        assert 'buffer' in ValidationRegistry.VALID_OPERATION_TYPES
        assert 'intersection' in ValidationRegistry.VALID_OPERATION_TYPES
        assert 'union' in ValidationRegistry.VALID_OPERATION_TYPES

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_patterns_epsg(self):
        """Test EPSG CRS pattern matching."""
        pattern = ValidationRegistry.CRS_PATTERNS['epsg']
        assert pattern.match("EPSG:4326")
        assert pattern.match("epsg:4326")  # Case insensitive
        assert not pattern.match("EPSG:abc")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_performance_thresholds(self):
        """Test that performance thresholds are reasonable."""
        thresholds = ValidationRegistry.PERFORMANCE_THRESHOLDS
        assert thresholds['max_buffer_distance'] > 0
        assert thresholds['max_file_size_mb'] > 0
        assert thresholds['max_features_warning'] > 0
