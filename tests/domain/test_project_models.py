"""Comprehensive tests for project-related domain models."""
import pytest
from typing import Dict, Any
from pydantic import ValidationError

from src.domain.project_models import (
    ExportFormat, DXFVersion, ProjectMainSettings, LegendDefinition,
    GlobalProjectSettings, SpecificProjectConfig, DXFMode
)


class TestExportFormat:
    """Test cases for ExportFormat enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_export_format_values(self):
        """Test ExportFormat enum values."""
        assert ExportFormat.DXF == "dxf"
        assert ExportFormat.SHAPEFILE == "shp"
        assert ExportFormat.GEOPACKAGE == "gpkg"
        assert ExportFormat.ALL == "all"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_export_format_from_string(self):
        """Test creating ExportFormat from string values."""
        assert ExportFormat("dxf") == ExportFormat.DXF
        assert ExportFormat("shp") == ExportFormat.SHAPEFILE
        assert ExportFormat("gpkg") == ExportFormat.GEOPACKAGE
        assert ExportFormat("all") == ExportFormat.ALL

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_export_format_invalid_value(self):
        """Test ExportFormat with invalid values."""
        with pytest.raises(ValueError):
            ExportFormat("invalid")
        with pytest.raises(ValueError):
            ExportFormat("pdf")


class TestDXFVersion:
    """Test cases for DXFVersion enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_version_values(self):
        """Test DXFVersion enum values."""
        assert DXFVersion.R12 == "R12"
        assert DXFVersion.R2000 == "R2000"
        assert DXFVersion.R2004 == "R2004"
        assert DXFVersion.R2007 == "R2007"
        assert DXFVersion.R2010 == "R2010"
        assert DXFVersion.R2013 == "R2013"
        assert DXFVersion.R2018 == "R2018"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_version_from_string(self):
        """Test creating DXFVersion from string values."""
        assert DXFVersion("R12") == DXFVersion.R12
        assert DXFVersion("R2000") == DXFVersion.R2000
        assert DXFVersion("R2010") == DXFVersion.R2010
        assert DXFVersion("R2018") == DXFVersion.R2018

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_version_invalid_value(self):
        """Test DXFVersion with invalid values."""
        with pytest.raises(ValueError):
            DXFVersion("R2025")
        with pytest.raises(ValueError):
            DXFVersion("invalid")


class TestDXFMode:
    """Test cases for DXFMode enum."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_mode_values(self):
        """Test DXFMode enum values."""
        assert DXFMode.CREATE == "create"
        assert DXFMode.UPDATE == "update"
        assert DXFMode.TEMPLATE == "template"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_mode_from_string(self):
        """Test creating DXFMode from string values."""
        assert DXFMode("create") == DXFMode.CREATE
        assert DXFMode("update") == DXFMode.UPDATE
        assert DXFMode("template") == DXFMode.TEMPLATE

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_mode_invalid_value(self):
        """Test DXFMode with invalid value."""
        with pytest.raises(ValueError):
            DXFMode("invalid_mode")


class TestDXFConfig:
    """Test cases for DXFConfig model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_minimal_dxf_config(self):
        """Test creating DXFConfig with minimal required fields."""
        from src.domain.project_models import DXFConfig

        config = DXFConfig(
            outputPath="output/test.dxf",
            mode="create"
        )

        assert config.output_path == "output/test.dxf"
        assert config.mode == DXFMode.CREATE
        assert config.input_path is None
        assert config.template_path is None
        assert config.version == DXFVersion.R2010

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_complete_dxf_config(self):
        """Test creating DXFConfig with all fields."""
        from src.domain.project_models import DXFConfig

        config = DXFConfig(
            outputPath="output/test.dxf",
            mode="update",
            inputPath="input/existing.dxf",
            templatePath="templates/base.dxf",
            version="R2018"
        )

        assert config.output_path == "output/test.dxf"
        assert config.mode == DXFMode.UPDATE
        assert config.input_path == "input/existing.dxf"
        assert config.template_path == "templates/base.dxf"
        assert config.version == DXFVersion.R2018

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_config_field_aliases(self):
        """Test DXFConfig field aliases work correctly."""
        from src.domain.project_models import DXFConfig

        # Using snake_case aliases
        config = DXFConfig(
            output_path="output/test.dxf",
            mode="template",
            input_path="input/existing.dxf",
            template_path="templates/base.dxf"
        )

        assert config.output_path == "output/test.dxf"
        assert config.mode == DXFMode.TEMPLATE
        assert config.input_path == "input/existing.dxf"
        assert config.template_path == "templates/base.dxf"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_config_required_fields(self):
        """Test DXFConfig required field validation."""
        from src.domain.project_models import DXFConfig

        # Missing outputPath
        with pytest.raises(ValidationError) as exc_info:
            DXFConfig(mode="create")
        assert "output_path" in str(exc_info.value) or "outputPath" in str(exc_info.value)

        # Missing mode
        with pytest.raises(ValidationError) as exc_info:
            DXFConfig(outputPath="test.dxf")
        assert "mode" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_dxf_config_enum_validation(self):
        """Test DXFConfig enum field validation."""
        from src.domain.project_models import DXFConfig

        # Valid enum values
        config = DXFConfig(
            outputPath="test.dxf",
            mode="update",
            version="R2007"
        )
        assert config.mode == DXFMode.UPDATE
        assert config.version == DXFVersion.R2007

        # Invalid mode
        with pytest.raises(ValidationError):
            DXFConfig(
                outputPath="test.dxf",
                mode="invalid_mode"
            )

        # Invalid version
        with pytest.raises(ValidationError):
            DXFConfig(
                outputPath="test.dxf",
                mode="create",
                version="R2025"
            )


class TestProjectMainSettings:
    """Test cases for ProjectMainSettings model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_minimal_valid_settings(self):
        """Test creating ProjectMainSettings with minimal required fields."""
        settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={
                "outputPath": "output/test.dxf",
                "mode": "create"
            }
        )

        assert settings.crs == "EPSG:4326"
        assert settings.dxf.output_path == "output/test.dxf"
        assert settings.dxf.mode == DXFMode.CREATE
        assert settings.template is None
        assert settings.export_format == ExportFormat.DXF
        assert settings.dxf_version == DXFVersion.R2010
        assert settings.style_presets_file == "styles.yaml"
        assert settings.shapefile_output_dir is None
        assert settings.output_geopackage_path is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_field_aliases(self):
        """Test field aliases work correctly."""
        # Using camelCase aliases
        settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={
                "outputPath": "/output/test.dxf",
                "mode": "update",
                "inputPath": "input/existing.dxf"
            },
            exportFormat="shp",
            dxfVersion="R2007",
            stylePresetsFile="custom_styles.yaml",
            shapefileOutputDir="/output/shp",
            outputGeopackagePath="/output/test.gpkg"
        )

        assert settings.dxf.output_path == "/output/test.dxf"
        assert settings.dxf.mode == DXFMode.UPDATE
        assert settings.dxf.input_path == "input/existing.dxf"
        assert settings.export_format == ExportFormat.SHAPEFILE
        assert settings.dxf_version == DXFVersion.R2007
        assert settings.style_presets_file == "custom_styles.yaml"
        assert settings.shapefile_output_dir == "/output/shp"
        assert settings.output_geopackage_path == "/output/test.gpkg"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_snake_case_fields(self):
        """Test snake_case field names work correctly."""
        settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={
                "output_path": "/output/test.dxf",
                "mode": "template",
                "template_path": "templates/base.dxf"
            },
            export_format="gpkg",
            dxf_version="R2013",
            style_presets_file="styles.yaml",
            shapefile_output_dir="/output",
            output_geopackage_path="/output/test.gpkg"
        )

        assert settings.dxf.output_path == "/output/test.dxf"
        assert settings.dxf.mode == DXFMode.TEMPLATE
        assert settings.dxf.template_path == "templates/base.dxf"
        assert settings.export_format == ExportFormat.GEOPACKAGE
        assert settings.dxf_version == DXFVersion.R2013

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_crs_validation(self):
        """Test CRS field accepts various formats."""
        # String CRS
        settings1 = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={"outputPath": "test.dxf", "mode": "create"}
        )
        assert settings1.crs == "EPSG:4326"

        # Integer CRS (EPSG code)
        settings2 = ProjectMainSettings(
            crs=4326,
            dxf={"outputPath": "test.dxf", "mode": "create"}
        )
        assert settings2.crs == 4326

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_required_fields_validation(self):
        """Test that required fields are validated."""
        # Missing crs
        with pytest.raises(ValidationError) as exc_info:
            ProjectMainSettings(dxf={"outputPath": "test.dxf", "mode": "create"})
        assert "crs" in str(exc_info.value)

        # Missing dxf configuration
        with pytest.raises(ValidationError) as exc_info:
            ProjectMainSettings(crs="EPSG:4326")
        assert "dxf" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_enum_field_validation(self):
        """Test enum field validation."""
        # Valid enum values
        settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={"outputPath": "test.dxf", "mode": "update"},
            exportFormat="all",
            dxfVersion="R2018"
        )
        assert settings.export_format == ExportFormat.ALL
        assert settings.dxf_version == DXFVersion.R2018

        # Invalid export format
        with pytest.raises(ValidationError):
            ProjectMainSettings(
                crs="EPSG:4326",
                dxf={"outputPath": "test.dxf", "mode": "create"},
                exportFormat="invalid"
            )

        # Invalid DXF version
        with pytest.raises(ValidationError):
            ProjectMainSettings(
                crs="EPSG:4326",
                dxf={"outputPath": "test.dxf", "mode": "create"},
                dxfVersion="R2025"
            )

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={"outputPath": "test.dxf", "mode": "create"},
            unknown_field="should_be_ignored",
            another_extra="also_ignored"
        )

        assert settings.crs == "EPSG:4326"
        assert settings.dxf.output_path == "test.dxf"
        assert not hasattr(settings, 'unknown_field')
        assert not hasattr(settings, 'another_extra')


class TestLegendDefinition:
    """Test cases for LegendDefinition model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_minimal_legend(self):
        """Test creating legend with minimal required fields."""
        legend = LegendDefinition(name="Test Legend")

        assert legend.name == "Test Legend"
        assert legend.title is None
        assert legend.position is None
        assert legend.style is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_complete_legend(self):
        """Test creating legend with all fields."""
        legend = LegendDefinition(
            name="Complete Legend",
            title="Legend Title",
            position={"x": 100.0, "y": 200.0},
            style="legend_style"
        )

        assert legend.name == "Complete Legend"
        assert legend.title == "Legend Title"
        assert legend.position == {"x": 100.0, "y": 200.0}
        assert legend.style == "legend_style"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_legend_required_field_validation(self):
        """Test that name field is required."""
        with pytest.raises(ValidationError) as exc_info:
            LegendDefinition()
        assert "name" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_legend_position_types(self):
        """Test different position value types."""
        # Dictionary position
        legend1 = LegendDefinition(
            name="Test",
            position={"x": 10, "y": 20, "width": 100, "height": 50}
        )
        assert legend1.position["x"] == 10
        assert legend1.position["y"] == 20

        # Empty dictionary
        legend2 = LegendDefinition(name="Test", position={})
        assert legend2.position == {}

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_legend_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        legend = LegendDefinition(
            name="Test Legend",
            extra_field="ignored",
            another_extra=123
        )

        assert legend.name == "Test Legend"
        assert not hasattr(legend, 'extra_field')
        assert not hasattr(legend, 'another_extra')


class TestGlobalProjectSettings:
    """Test cases for GlobalProjectSettings model."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_default_global_settings(self):
        """Test GlobalProjectSettings with default values."""
        settings = GlobalProjectSettings()

        assert settings.default_crs == "EPSG:4326"
        assert settings.default_dxf_version == DXFVersion.R2010
        assert settings.default_export_format == ExportFormat.DXF
        assert settings.global_styles_enabled is True
        assert settings.validation_enabled is True

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_custom_global_settings(self):
        """Test GlobalProjectSettings with custom values."""
        settings = GlobalProjectSettings(
            default_crs="EPSG:3857",
            default_dxf_version=DXFVersion.R2018,
            default_export_format=ExportFormat.GEOPACKAGE,
            global_styles_enabled=False,
            validation_enabled=False
        )

        assert settings.default_crs == "EPSG:3857"
        assert settings.default_dxf_version == DXFVersion.R2018
        assert settings.default_export_format == ExportFormat.GEOPACKAGE
        assert settings.global_styles_enabled is False
        assert settings.validation_enabled is False

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_global_settings_crs_types(self):
        """Test different CRS types in global settings."""
        # String CRS
        settings1 = GlobalProjectSettings(default_crs="EPSG:4326")
        assert settings1.default_crs == "EPSG:4326"

        # Integer CRS
        settings2 = GlobalProjectSettings(default_crs=4326)
        assert settings2.default_crs == 4326

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_global_settings_enum_validation(self):
        """Test enum validation in global settings."""
        # Valid enum values
        settings = GlobalProjectSettings(
            default_dxf_version="R2007",
            default_export_format="shp"
        )
        assert settings.default_dxf_version == DXFVersion.R2007
        assert settings.default_export_format == ExportFormat.SHAPEFILE

        # Invalid enum values
        with pytest.raises(ValidationError):
            GlobalProjectSettings(default_dxf_version="R2025")

        with pytest.raises(ValidationError):
            GlobalProjectSettings(default_export_format="invalid")


class TestSpecificProjectConfig:
    """Test cases for SpecificProjectConfig model."""

    @pytest.fixture
    def sample_main_settings(self) -> ProjectMainSettings:
        """Fixture providing sample main settings."""
        return ProjectMainSettings(
            crs="EPSG:4326",
            dxf={
                "outputPath": "output/test.dxf",
                "mode": "create"
            }
        )

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_minimal_project_config(self, sample_main_settings):
        """Test creating project config with minimal required fields."""
        config = SpecificProjectConfig(main=sample_main_settings)

        assert config.main == sample_main_settings
        assert config.geom_layers == []
        assert config.legends == []
        assert config.project_specific_styles is None
        assert config.path_aliases is None
        assert config.viewports == []
        assert config.block_inserts == []
        assert config.text_inserts == []
        assert config.path_arrays == []
        assert config.wmts_layers == []
        assert config.wms_layers == []
        assert config.dxf_operations is None

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_project_config_with_legends(self, sample_main_settings):
        """Test project config with legends."""
        legends = [
            LegendDefinition(name="Legend 1"),
            LegendDefinition(name="Legend 2", title="Second Legend")
        ]

        config = SpecificProjectConfig(
            main=sample_main_settings,
            legends=legends
        )

        assert len(config.legends) == 2
        assert config.legends[0].name == "Legend 1"
        assert config.legends[1].name == "Legend 2"

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_project_config_field_aliases(self, sample_main_settings):
        """Test project config field aliases."""
        config = SpecificProjectConfig(
            main=sample_main_settings,
            geomLayers=[],
            projectSpecificStyles={"style1": {"color": "red"}},
            pathAliases=None,
            blockInserts=[{"name": "block1"}],
            textInserts=[{"text": "sample"}],
            pathArrays=[{"path": "test"}],
            wmtsLayers=[{"url": "http://example.com"}],
            wmsLayers=[{"url": "http://example.com"}],
            dxfOperations={"operation": "test"}
        )

        assert config.geom_layers == []
        assert config.project_specific_styles == {"style1": {"color": "red"}}
        assert config.path_aliases is None
        assert config.block_inserts == [{"name": "block1"}]
        assert config.text_inserts == [{"text": "sample"}]
        assert config.path_arrays == [{"path": "test"}]
        assert config.wmts_layers == [{"url": "http://example.com"}]
        assert config.wms_layers == [{"url": "http://example.com"}]
        assert config.dxf_operations == {"operation": "test"}

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_project_config_required_field_validation(self):
        """Test that main field is required."""
        with pytest.raises(ValidationError) as exc_info:
            SpecificProjectConfig()
        assert "main" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_project_config_extra_fields_ignored(self, sample_main_settings):
        """Test that extra fields are ignored."""
        config = SpecificProjectConfig(
            main=sample_main_settings,
            unknown_field="ignored",
            extra_data={"should": "be_ignored"}
        )

        assert config.main == sample_main_settings
        assert not hasattr(config, 'unknown_field')
        assert not hasattr(config, 'extra_data')

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_project_config_complex_structure(self, sample_main_settings):
        """Test project config with complex nested structure."""
        config = SpecificProjectConfig(
            main=sample_main_settings,
            legends=[
                LegendDefinition(name="Legend 1", position={"x": 0, "y": 0}),
                LegendDefinition(name="Legend 2", position={"x": 100, "y": 100})
            ],
            projectSpecificStyles={
                "layer_style": {
                    "color": "blue",
                    "linetype": "CONTINUOUS"
                },
                "text_style": {
                    "height": 2.5,
                    "font": "Arial"
                }
            },
            viewports=[
                {"name": "viewport1", "scale": 1.0},
                {"name": "viewport2", "scale": 0.5}
            ],
            wmtsLayers=[
                {
                    "name": "satellite",
                    "url": "http://example.com/wmts",
                    "layer": "satellite_layer"
                }
            ]
        )

        assert len(config.legends) == 2
        assert "layer_style" in config.project_specific_styles
        assert "text_style" in config.project_specific_styles
        assert len(config.viewports) == 2
        assert len(config.wmts_layers) == 1
        assert config.wmts_layers[0]["name"] == "satellite"


class TestProjectModelsIntegration:
    """Integration tests for project models working together."""

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_complete_project_configuration(self):
        """Test a complete project configuration with all components."""
        main_settings = ProjectMainSettings(
            crs="EPSG:3857",
            dxf={
                "outputPath": "complete_project.dxf",
                "mode": "create"
            },
            exportFormat="all",
            dxfVersion="R2018",
            stylePresetsFile="project_styles.yaml",
            outputGeopackagePath="/output/complete_project.gpkg"
        )

        legends = [
            LegendDefinition(
                name="Main Legend",
                title="Project Legend",
                position={"x": 10, "y": 10, "width": 200, "height": 300},
                style="legend_style"
            )
        ]

        config = SpecificProjectConfig(
            main=main_settings,
            legends=legends,
            projectSpecificStyles={
                "building_style": {"color": "red", "linetype": "CONTINUOUS"},
                "road_style": {"color": "black", "lineweight": 0.5}
            },
            viewports=[
                {"name": "overview", "scale": 1000},
                {"name": "detail", "scale": 100}
            ]
        )

        # Verify the complete structure
        assert config.main.crs == "EPSG:3857"
        assert config.main.export_format == ExportFormat.ALL
        assert config.main.dxf_version == DXFVersion.R2018
        assert len(config.legends) == 1
        assert config.legends[0].name == "Main Legend"
        assert "building_style" in config.project_specific_styles
        assert len(config.viewports) == 2

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.config
    @pytest.mark.fast
    def test_enum_consistency_across_models(self):
        """Test that enums work consistently across different models."""
        # Test same enum values in different models
        main_settings = ProjectMainSettings(
            crs="EPSG:4326",
            dxf={
                "outputPath": "test.dxf",
                "mode": "create"
            },
            exportFormat="gpkg",
            dxfVersion="R2013"
        )

        global_settings = GlobalProjectSettings(
            default_export_format="gpkg",
            default_dxf_version="R2013"
        )

        # Verify enum consistency
        assert main_settings.export_format == global_settings.default_export_format
        assert main_settings.dxf_version == global_settings.default_dxf_version
        assert main_settings.export_format == ExportFormat.GEOPACKAGE
        assert main_settings.dxf_version == DXFVersion.R2013
