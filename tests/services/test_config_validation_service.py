"""Integration tests for ConfigValidationService with other services."""
import pytest
import tempfile
import json
import yaml
from pathlib import Path
from typing import Dict, Any
import os

from src.core.container import ApplicationContainer
from src.domain.config_validation import ConfigValidationService, ConfigValidationError
from src.services.config_loader_service import ConfigLoaderService


class TestConfigValidationServiceIntegration:
    """Integration tests for ConfigValidationService."""

    @pytest.fixture
    def container(self):
        """Create application container for testing."""
        return ApplicationContainer()

    @pytest.fixture
    def temp_project_structure(self):
        """Create a temporary project structure for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create project structure
            project_dir = temp_path / "projects" / "test_project"
            project_dir.mkdir(parents=True)

            # Create test data
            test_data = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Test Building", "type": "commercial", "area": 1000},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-74.006, 40.7128], [-74.005, 40.7128],
                                           [-74.005, 40.7138], [-74.006, 40.7138],
                                           [-74.006, 40.7128]]]
                        }
                    }
                ]
            }

            (project_dir / "test_data.geojson").write_text(json.dumps(test_data))

            # MODIFIED: Create project.yaml with main settings, pathAliases, and stylePresets
            project_config_data = {
                "main": {
                    "crs": "EPSG:4326",
                    "dxfVersion": "R2018",
                    "exportFormat": "dxf",
                    "dxf": {
                        "outputPath": "output/default_test.dxf",
                        "templatePath": "some/template.dxf"
                    }
                },
                "pathAliases": {
                    "data": {
                        "test": "test_data.geojson"
                    },
                    "output": {
                        "dxf": "output/test.dxf"
                    }
                },
                "stylePresets": {
                    "building_style": {
                        "layer": {"color": 7, "linetype": "CONTINUOUS"}
                    }
                }
            }
            (project_dir / "project.yaml").write_text(yaml.dump(project_config_data))

            # MODIFIED: Create the dummy template.dxf file and its parent directory
            template_dxf_dir = project_dir / "some"
            template_dxf_dir.mkdir(parents=True, exist_ok=True)
            (template_dxf_dir / "template.dxf").write_text("0\nEOF\n") # Minimal valid DXF

            # Create valid geom_layers.yaml (only geomLayers list)
            valid_geom_layers_data = {
                "geomLayers": [
                    {
                        "name": "valid_layer",
                        "type": "polygon",
                        "style": "building_style",
                        "source": "@data/test",
                        "operations": []
                    }
                ]
            }
            (project_dir / "geom_layers.yaml").write_text(yaml.dump(valid_geom_layers_data))

            # Create invalid geom_layers.yaml for testing validation errors (main and pathAliases remain here for this specific test file)
            invalid_geom_layers = {
                "geomLayers": [
                    {
                        "name": "invalid_layer",
                        "geojsonFile": "@data.nonexistent",  # Non-existent file
                        "style": "building_styl",  # Typo in style name
                        "updateDxf": "yes",  # Should be boolean
                        "labelColum": "name",  # Typo in field name
                        "unknownSetting": "value",  # Unknown setting
                        "operations": [
                            {
                                "type": "bufer",  # Typo in operation type
                                "distance": -5.0,  # Invalid negative distance
                                "cap_style": "invalid_cap",  # Invalid cap style
                                "layers": ["nonexistent_layer"]  # Non-existent layer reference
                            }
                        ]
                    }
                ],
                "pathAliases": { # Keep pathAliases here for the invalid file test
                    "data": {
                        "test": "test_data.geojson",
                        "dangerous": "../../../etc/passwd"  # Security warning
                    }
                },
                "main": { # Keep main here for the invalid file test
                    "crs": "EPSG:99999",  # Invalid EPSG code
                    "dxfVersion": "R2025",  # Invalid DXF version
                    "maxMemoryMb": 256  # Performance warning
                }
            }
            (project_dir / "geom_layers_invalid.yaml").write_text(yaml.dump(invalid_geom_layers))

            yield {
                "temp_dir": temp_path,
                "project_dir": project_dir,
                "projects_root": temp_path / "projects"
            }

    @pytest.mark.integration
    @pytest.mark.services
    def test_config_validation_service_initialization(self, container):
        """Test that ConfigValidationService can be initialized from container."""
        validation_service = container.config_validation_service()
        assert isinstance(validation_service, ConfigValidationService)
        assert validation_service.validation_errors == []
        assert validation_service.validation_warnings == []

    @pytest.mark.integration
    @pytest.mark.services
    def test_config_loader_with_validation(self, container, temp_project_structure):
        """Test config loader service with validation enabled."""
        config_loader = container.config_loader_service()

        # Test loading valid configuration
        try:
            # Change to the temp directory to make relative paths work
            import os
            original_cwd = os.getcwd()
            os.chdir(temp_project_structure["temp_dir"])

            config = config_loader.load_specific_project_config(
                "test_project",
                "projects",
                geom_layers_yaml_name="geom_layers.yaml"
            )

            assert config is not None
            assert len(config.geom_layers) == 1
            assert config.geom_layers[0].name == "valid_layer"

        finally:
            os.chdir(original_cwd)

    @pytest.mark.integration
    @pytest.mark.services
    def test_config_loader_with_validation_errors(self, container, temp_project_structure):
        """Test config loader service with validation errors."""
        config_loader = container.config_loader_service()

        # Test loading invalid configuration
        import os
        original_cwd = os.getcwd()

        try:
            os.chdir(temp_project_structure["temp_dir"])

            with pytest.raises(Exception):  # Should raise ConfigError due to validation failure
                config_loader.load_specific_project_config(
                    "test_project",
                    "projects",
                    geom_layers_yaml_name="geom_layers_invalid.yaml"
                )

        finally:
            os.chdir(original_cwd)

    @pytest.mark.integration
    @pytest.mark.services
    def test_validation_with_path_resolver(self, container, temp_project_structure):
        """Test validation service integration with path resolver."""
        validation_service = container.config_validation_service()
        path_resolver = container.path_resolver_service()

        # Create validation service with path resolver
        validation_service_with_resolver = ConfigValidationService(
            base_path=str(temp_project_structure["project_dir"]),
            path_resolver=path_resolver
        )

        config = {
            "geomLayers": [
                {
                    "name": "test_layer",
                    "geojsonFile": "@data.test",  # Path alias
                    "style": "building_style",
                    "updateDxf": True
                }
            ],
            "pathAliases": {
                "data": {
                    "test": "test_data.geojson"
                }
            }
        }

        # This should resolve the path alias and validate successfully
        result = validation_service_with_resolver.validate_project_config(config)
        assert result == config

    @pytest.mark.integration
    @pytest.mark.services
    def test_comprehensive_validation_scenarios(self, temp_project_structure):
        """Test comprehensive validation scenarios from the demo files."""
        validation_service = ConfigValidationService(
            base_path=str(temp_project_structure["project_dir"])
        )

        # Test performance warning scenario
        performance_config = {
            "geomLayers": [
                {
                    "name": "performance_test",
                    "geojsonFile": "test_data.geojson",
                    "style": "building_style",
                    "updateDxf": True,
                    "operations": [
                        {
                            "type": "buffer",
                            "distance": 15000.0,  # Exceeds performance threshold
                            "layers": ["performance_test"]
                        }
                    ]
                }
            ]
        }

        with pytest.raises(ConfigValidationError):
            validation_service.validate_project_config(performance_config)

        errors = validation_service.validation_errors
        assert any("exceeds recommended maximum" in error for error in errors)

    @pytest.mark.integration
    @pytest.mark.services
    def test_validation_warnings_collection(self, temp_project_structure):
        """Test that validation warnings are properly collected."""
        validation_service = ConfigValidationService(
            base_path=str(temp_project_structure["project_dir"])
        )

        # Configuration that should generate warnings but not errors
        warning_config = {
            "geomLayers": [
                {
                    "name": "warning_test",
                    "geojsonFile": "test_data.geojson",
                    "style": "building_style",
                    "updateDxf": True,
                    "unknownSetting": "value",  # Should generate warning
                    "labelColum": "name"  # Typo should generate warning
                }
            ],
            "pathAliases": {
                "data": {
                    "test": "test_data.geojson",
                    "suspicious": "../suspicious_path"  # Security warning
                }
            },
            "main": {
                "maxMemoryMb": 256  # Performance warning
            }
        }

        # This should succeed but generate warnings
        result = validation_service.validate_project_config(warning_config)

        warnings = validation_service.validation_warnings
        assert len(warnings) > 0
        assert any("unknown" in warning.lower() for warning in warnings)
        assert any("memory" in warning.lower() for warning in warnings)

    @pytest.mark.integration
    @pytest.mark.services
    def test_validation_error_details(self, temp_project_structure):
        """Test that validation errors contain detailed information."""
        validation_service = ConfigValidationService(
            base_path=str(temp_project_structure["project_dir"])
        )

        error_config = {
            "geomLayers": [
                {
                    "name": "error_test",
                    "geojsonFile": "nonexistent.geojson",
                    "style": "building_style",
                    "updateDxf": True,
                    "operations": [
                        {
                            "type": "buffer",
                            "distance": -10.0,  # Invalid negative distance
                            "cap_style": "invalid_style"  # Invalid cap style
                        },
                        {
                            "type": "invalid_operation"  # Invalid operation type
                        }
                    ]
                }
            ]
        }

        try:
            validation_service.validate_project_config(error_config)
            pytest.fail("Expected ConfigValidationError")
        except ConfigValidationError as e:
            assert e.validation_errors is not None
            assert len(e.validation_errors) > 0

            errors = e.validation_errors
            assert any("cannot be negative" in error for error in errors)
            assert any("Invalid cap style" in error for error in errors)
            assert any("Unknown operation type" in error for error in errors)

    @pytest.mark.integration
    @pytest.mark.services
    def test_validation_with_file_existence_checking(self, temp_project_structure):
        """Test validation with file existence checking."""
        validation_service = ConfigValidationService(
            base_path=str(temp_project_structure["project_dir"])
        )

        # Test with existing file
        valid_config = {
            "geomLayers": [
                {
                    "name": "file_test",
                    "geojsonFile": "test_data.geojson",  # This file exists
                    "style": "building_style",
                    "updateDxf": True
                }
            ]
        }

        # Should succeed
        result = validation_service.validate_project_config(valid_config)
        assert result == valid_config

        # Test with non-existing file
        invalid_config = {
            "geomLayers": [
                {
                    "name": "file_test",
                    "geojsonFile": "nonexistent.geojson",  # This file doesn't exist
                    "style": "building_style",
                    "updateDxf": True
                }
            ]
        }

        # Should fail with file not found error
        with pytest.raises(ConfigValidationError):
            validation_service.validate_project_config(invalid_config)


class TestValidationServicePerformance:
    """Performance tests for validation service."""

    @pytest.mark.integration
    @pytest.mark.services
    @pytest.mark.slow
    def test_large_config_validation_performance(self):
        """Test validation performance with large configurations."""
        validation_service = ConfigValidationService()

        # Create a large configuration with many layers
        large_config = {
            "geomLayers": []
        }

        # Add 100 layers to test performance
        for i in range(100):
            layer = {
                "name": f"layer_{i}",
                "geojsonFile": f"data_{i}.geojson",
                "style": "building_style",
                "updateDxf": True,
                "operations": [
                    {
                        "type": "buffer",
                        "distance": 10.0,
                        "layers": [f"layer_{i}"]
                    }
                ]
            }
            large_config["geomLayers"].append(layer)

        # Validation should complete in reasonable time
        import time
        start_time = time.time()

        try:
            validation_service.validate_project_config(large_config)
        except ConfigValidationError:
            pass  # We expect some validation errors due to missing files

        end_time = time.time()
        validation_time = end_time - start_time

        # Should complete within 5 seconds for 100 layers
        assert validation_time < 5.0, f"Validation took too long: {validation_time:.2f} seconds"
