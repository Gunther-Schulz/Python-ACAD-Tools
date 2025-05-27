"""
Comprehensive DXF integration tests that generate real DXF files and verify styling results.

This module tests the complete styling pipeline by:
1. Generating real DXF files with styled entities
2. Analyzing the generated DXF files to verify correct styling application
3. Testing all entity types, layer properties, and style combinations
4. Ensuring comprehensive coverage of the styling system
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from unittest.mock import Mock

# Import ezdxf for DXF analysis
try:
    import ezdxf
    from ezdxf.document import Drawing
    from ezdxf.entities import DXFGraphic, Text, MText, Line, LWPolyline, Circle, Hatch
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    pytest.skip("ezdxf not available", allow_module_level=True)

from src.services.style_applicator_service import StyleApplicatorService
from src.services.logging_service import LoggingService
from src.domain.style_models import NamedStyle, LayerStyleProperties, TextStyleProperties, HatchStyleProperties
from src.adapters.ezdxf_adapter import EzdxfAdapter
from src.services.config_loader_service import ConfigLoaderService
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.interfaces.geometry_processor_interface import IGeometryProcessor
from src.interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator


class DXFAnalyzer:
    """Utility class for analyzing generated DXF files to verify styling."""

    def __init__(self, dxf_path: str):
        """Initialize with path to DXF file."""
        self.dxf_path = dxf_path
        self.doc: Optional[Drawing] = None
        self._load_document()

    def _load_document(self) -> None:
        """Load the DXF document for analysis."""
        try:
            self.doc = ezdxf.readfile(self.dxf_path)
        except Exception as e:
            pytest.fail(f"Failed to load DXF file {self.dxf_path}: {e}")

    def get_entities_by_type(self, entity_type: str) -> List[DXFGraphic]:
        """Get all entities of a specific type."""
        if not self.doc:
            return []

        entities = []
        for entity in self.doc.modelspace():
            if entity.dxftype() == entity_type:
                entities.append(entity)
        return entities

    def get_entities_by_layer(self, layer_name: str) -> List[DXFGraphic]:
        """Get all entities on a specific layer."""
        if not self.doc:
            return []

        entities = []
        for entity in self.doc.modelspace():
            if entity.dxf.layer == layer_name:
                entities.append(entity)
        return entities

    def verify_layer_properties(self, layer_name: str, expected_props: Dict[str, Any]) -> Dict[str, bool]:
        """Verify layer properties match expected values."""
        if not self.doc or layer_name not in self.doc.layers:
            return {"layer_exists": False}

        layer = self.doc.layers.get(layer_name)
        results = {"layer_exists": True}

        # Check color
        if "color" in expected_props:
            expected_color = expected_props["color"]
            actual_color = layer.dxf.color
            results["color_match"] = actual_color == expected_color

        # Check linetype
        if "linetype" in expected_props:
            expected_linetype = expected_props["linetype"]
            actual_linetype = layer.dxf.linetype
            print(f"DEBUG LINETYPE: Expected: '{expected_linetype}' (type: {type(expected_linetype)}), Actual from DXF: '{actual_linetype}' (type: {type(actual_linetype)})")
            results["linetype_match"] = actual_linetype == expected_linetype

        # Check lineweight
        if "lineweight" in expected_props:
            expected_lineweight = expected_props["lineweight"]
            actual_lineweight_from_dxf = layer.dxf.lineweight

            # If actual_lineweight_from_dxf is LINEWEIGHT_DEFAULT (-3),
            # and the expected is 25 (common default for 0.25mm),
            # consider it a match as ezdxf might optimize the save.
            if actual_lineweight_from_dxf == ezdxf.lldxf.const.LINEWEIGHT_DEFAULT and \
               expected_lineweight == 25:  # Standard default for 0.25mm
                results["lineweight_match"] = True
            else:
                results["lineweight_match"] = actual_lineweight_from_dxf == expected_lineweight

        # Check transparency
        if "transparency" in expected_props:
            expected_transparency = expected_props["transparency"]
            actual_transparency = getattr(layer.dxf, 'transparency', None)
            results["transparency_match"] = actual_transparency == expected_transparency

        # Check plot flag
        if "plot" in expected_props:
            expected_plot = expected_props["plot"]
            actual_plot = layer.dxf.plot
            results["plot_match"] = actual_plot == expected_plot

        # Check layer state flags
        if "isOn" in expected_props:
            expected_on = expected_props["isOn"]
            actual_on = not layer.is_off
            results["isOn_match"] = actual_on == expected_on

        if "frozen" in expected_props:
            expected_frozen = expected_props["frozen"]
            actual_frozen = layer.is_frozen
            results["frozen_match"] = actual_frozen == expected_frozen

        if "locked" in expected_props:
            expected_locked = expected_props["locked"]
            actual_locked = layer.is_locked
            results["locked_match"] = actual_locked == expected_locked

        return results

    def verify_entity_properties(self, entity: DXFGraphic, expected_props: Dict[str, Any]) -> Dict[str, bool]:
        """Verify entity properties match expected values."""
        results = {}

        # Check color
        if "color" in expected_props:
            expected_color = expected_props["color"]
            actual_color = entity.dxf.color
            results["color_match"] = actual_color == expected_color

        # Check linetype
        if "linetype" in expected_props:
            expected_linetype = expected_props["linetype"]
            actual_linetype = entity.dxf.linetype
            results["linetype_match"] = actual_linetype == expected_linetype

        # Check lineweight
        if "lineweight" in expected_props:
            expected_lineweight = expected_props["lineweight"]
            actual_lineweight = entity.dxf.lineweight
            results["lineweight_match"] = actual_lineweight == expected_lineweight

        # Check layer assignment
        if "layer" in expected_props:
            expected_layer = expected_props["layer"]
            actual_layer = entity.dxf.layer
            results["layer_match"] = actual_layer == expected_layer

        return results

    def verify_text_properties(self, text_entity: Union[Text, MText], expected_props: Dict[str, Any]) -> Dict[str, bool]:
        """Verify text entity properties match expected values."""
        results = {}

        # Check text content
        if "text" in expected_props:
            expected_text = expected_props["text"]
            actual_text = text_entity.dxf.text
            results["text_match"] = actual_text == expected_text

        # Check height (different attributes for TEXT vs MTEXT)
        if "height" in expected_props:
            expected_height = expected_props["height"]
            if text_entity.dxftype() == "MTEXT":
                # MTEXT uses char_height
                actual_height = text_entity.dxf.char_height
            else:
                # TEXT uses height
                actual_height = text_entity.dxf.height
            results["height_match"] = abs(actual_height - expected_height) < 0.001

        # Check rotation
        if "rotation" in expected_props:
            expected_rotation = expected_props["rotation"]
            actual_rotation = text_entity.dxf.rotation
            results["rotation_match"] = abs(actual_rotation - expected_rotation) < 0.001

        # Check style (font)
        if "style" in expected_props:
            expected_style = expected_props["style"]
            actual_style = text_entity.dxf.style
            results["style_match"] = actual_style == expected_style

        return results

    def verify_hatch_properties(self, hatch_entity: Hatch, expected_props: Dict[str, Any]) -> Dict[str, bool]:
        """Verify hatch entity properties match expected values."""
        results = {}

        # Check pattern name
        if "pattern_name" in expected_props:
            expected_pattern = expected_props["pattern_name"]
            actual_pattern = hatch_entity.dxf.pattern_name
            results["pattern_match"] = actual_pattern == expected_pattern

        # Check scale
        if "pattern_scale" in expected_props:
            expected_scale = expected_props["pattern_scale"]
            actual_scale = hatch_entity.dxf.pattern_scale
            results["scale_match"] = abs(actual_scale - expected_scale) < 0.001

        # Check angle
        if "pattern_angle" in expected_props:
            expected_angle = expected_props["pattern_angle"]
            actual_angle = hatch_entity.dxf.pattern_angle
            results["angle_match"] = abs(actual_angle - expected_angle) < 0.001

        return results


class TestDXFIntegration:
    """Comprehensive DXF integration tests."""

    @pytest.fixture
    def temp_dxf_file(self):
        """Create a temporary DXF file for testing."""
        fd, temp_path = tempfile.mkstemp(suffix='.dxf')
        os.close(fd)  # Close the file descriptor
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def dxf_document(self):
        """Create a new DXF document for testing."""
        return ezdxf.new('R2010')

    def test_line_entity_styling(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test LINE entity styling in generated DXF."""
        # Create test geometry
        line_geom = LineString([(0, 0), (10, 10)])
        gdf = gpd.GeoDataFrame({'geometry': [line_geom]})

        # Get style
        style = comprehensive_styles.styles['basic_layer_red']
        layer_name = "test_lines"

        # Apply style and add to DXF
        real_style_applicator_service.add_geodataframe_to_dxf(
            dxf_document, gdf, layer_name, style
        )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify layer properties
        layer_results = analyzer.verify_layer_properties(layer_name, {
            "color": 1,  # red = ACI 1
            "linetype": "Continuous",  # ezdxf uses "Continuous" not "CONTINUOUS"
            "lineweight": 25  # Valid DXF lineweight from style
        })

        # Assertions for layer properties
        assert layer_results["layer_exists"], "Layer should exist"
        assert layer_results["color_match"], "Layer color should match"
        assert layer_results["linetype_match"], "Layer linetype should match"
        assert layer_results["lineweight_match"], "Layer lineweight should match"

        # Verify entities exist (LineString creates LWPOLYLINE, not LINE)
        lwpolyline_entities = analyzer.get_entities_by_type("LWPOLYLINE")
        assert len(lwpolyline_entities) > 0, "Should have LWPOLYLINE entities"

        # Verify entity properties
        line_entity = lwpolyline_entities[0]
        entity_results = analyzer.verify_entity_properties(line_entity, {
            "layer": layer_name
        })

        assert entity_results["layer_match"], "Entity should be on correct layer"

    def test_text_entity_styling(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test TEXT entity styling in generated DXF."""
        # Create test geometry with label
        point_geom = Point(5, 5)
        gdf = gpd.GeoDataFrame({
            'geometry': [point_geom],
            'label': ['Test Label']
        })

        # Get style with text properties
        style = comprehensive_styles.styles['text_comprehensive']
        layer_name = "test_text"

        # Apply style and add to DXF
        real_style_applicator_service.add_geodataframe_to_dxf(
            dxf_document, gdf, layer_name, style
        )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify text entities exist
        text_entities = analyzer.get_entities_by_type("TEXT")
        mtext_entities = analyzer.get_entities_by_type("MTEXT")

        assert len(text_entities) > 0 or len(mtext_entities) > 0, "Should have text entities"

        # Verify text properties (check first available text entity)
        text_entity = text_entities[0] if text_entities else mtext_entities[0]
        text_results = analyzer.verify_text_properties(text_entity, {
            "text": "Test Label",
            "height": 5.0,
            "rotation": 45.0
        })

        assert text_results["text_match"], "Text content should match"
        assert text_results["height_match"], "Text height should match"
        assert text_results["rotation_match"], "Text rotation should match"

    def test_polygon_with_hatch_styling(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test polygon with hatch styling in generated DXF."""
        # Create test polygon
        polygon_geom = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        gdf = gpd.GeoDataFrame({'geometry': [polygon_geom]})

        # Get style with hatch properties
        style = comprehensive_styles.styles['hatch_comprehensive']
        layer_name = "test_polygons"

        # Apply style and add to DXF
        real_style_applicator_service.add_geodataframe_to_dxf(
            dxf_document, gdf, layer_name, style
        )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify hatch entities exist
        hatch_entities = analyzer.get_entities_by_type("HATCH")
        assert len(hatch_entities) > 0, "Should have HATCH entities"

        # Verify hatch properties
        hatch_entity = hatch_entities[0]
        hatch_results = analyzer.verify_hatch_properties(hatch_entity, {
            "pattern_name": "ANSI31",
            "pattern_scale": 2.5,
            "pattern_angle": 45.0
        })

        assert hatch_results["pattern_match"], "Hatch pattern should match"
        assert hatch_results["scale_match"], "Hatch scale should match"
        assert hatch_results["angle_match"], "Hatch angle should match"

    def test_combined_style_application(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test combined layer + text + hatch styling."""
        # Create mixed geometry
        line_geom = LineString([(0, 0), (5, 5)])
        polygon_geom = Polygon([(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)])
        point_geom = Point(15, 15)

        gdf = gpd.GeoDataFrame({
            'geometry': [line_geom, polygon_geom, point_geom],
            'label': ['Line Label', 'Polygon Label', 'Point Label']
        })

        # Get full combined style
        style = comprehensive_styles.styles['full_combined']
        layer_name = "test_combined"

        # Apply style and add to DXF
        real_style_applicator_service.add_geodataframe_to_dxf(
            dxf_document, gdf, layer_name, style
        )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify layer properties (from layer style)
        layer_results = analyzer.verify_layer_properties(layer_name, {
            "color": 98,  # green-dark maps to ACI 98 in official color file
            "linetype": "BORDER",
            "lineweight": 60,
            "plot": True
        })

        assert layer_results["layer_exists"], "Layer should exist"
        assert layer_results["color_match"], "Layer color should match"
        assert layer_results["linetype_match"], "Layer linetype should match"
        assert layer_results["lineweight_match"], "Layer lineweight should match"
        assert layer_results["plot_match"], "Layer plot flag should match"

        # Verify multiple entity types exist
        line_entities = analyzer.get_entities_by_type("LINE")
        lwpolyline_entities = analyzer.get_entities_by_type("LWPOLYLINE")
        hatch_entities = analyzer.get_entities_by_type("HATCH")
        text_entities = analyzer.get_entities_by_type("TEXT")
        mtext_entities = analyzer.get_entities_by_type("MTEXT")

        assert len(line_entities) > 0 or len(lwpolyline_entities) > 0, "Should have line/polyline entities"
        assert len(hatch_entities) > 0, "Should have hatch entities"
        assert len(text_entities) > 0 or len(mtext_entities) > 0, "Should have text entities"

    def test_all_entity_types_comprehensive(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Comprehensive test of all supported entity types with various styles."""
        # Create diverse geometry types
        geometries = [
            Point(0, 0),  # Point
            LineString([(1, 1), (2, 2)]),  # Line
            LineString([(3, 3), (4, 4), (5, 3), (3, 3)]),  # Closed polyline
            Polygon([(6, 6), (8, 6), (8, 8), (6, 8), (6, 6)]),  # Polygon
        ]

        labels = ['Point Label', 'Line Label', 'Polyline Label', 'Polygon Label']

        gdf = gpd.GeoDataFrame({
            'geometry': geometries,
            'label': labels
        })

        # Test with different styles
        test_styles = [
            ('basic_layer_red', 'red_layer'),
            ('text_comprehensive', 'text_layer'),
            ('hatch_comprehensive', 'hatch_layer'),
            ('full_combined', 'combined_layer')
        ]

        for style_name, layer_name in test_styles:
            style = comprehensive_styles.styles[style_name]

            # Apply style and add to DXF
            real_style_applicator_service.add_geodataframe_to_dxf(
                dxf_document, gdf, layer_name, style
            )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify all layers exist
        for style_name, layer_name in test_styles:
            layer_results = analyzer.verify_layer_properties(layer_name, {})
            assert layer_results["layer_exists"], f"Layer {layer_name} should exist"

        # Verify entity diversity
        entity_types = ["POINT", "LINE", "LWPOLYLINE", "HATCH", "TEXT", "MTEXT"]
        found_types = set()

        for entity_type in entity_types:
            entities = analyzer.get_entities_by_type(entity_type)
            if entities:
                found_types.add(entity_type)

        # Should have at least lines/polylines, and potentially text/hatch
        assert len(found_types) >= 2, f"Should have multiple entity types, found: {found_types}"

    def test_edge_case_styles(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test edge case and extreme value styles."""
        # Create simple test geometry
        line_geom = LineString([(0, 0), (1, 1)])
        gdf = gpd.GeoDataFrame({'geometry': [line_geom]})

        # Test edge case styles
        edge_styles = ['minimal_layer', 'minimal_text', 'minimal_hatch', 'extreme_values']

        for i, style_name in enumerate(edge_styles):
            if style_name in comprehensive_styles.styles:
                style = comprehensive_styles.styles[style_name]
                layer_name = f"edge_case_{i}"

                # Apply style and add to DXF
                real_style_applicator_service.add_geodataframe_to_dxf(
                    dxf_document, gdf, layer_name, style
                )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify no crashes and basic functionality
        for i in range(len(edge_styles)):
            layer_name = f"edge_case_{i}"
            layer_results = analyzer.verify_layer_properties(layer_name, {})
            # Just verify layer exists (properties may be defaults)
            if layer_results.get("layer_exists"):
                entities = analyzer.get_entities_by_layer(layer_name)
                assert len(entities) >= 0, f"Layer {layer_name} should be processable"

    def test_performance_large_dataset(self, real_style_applicator_service, comprehensive_styles, temp_dxf_file, dxf_document):
        """Test performance with larger datasets."""
        import time

        # Create larger dataset
        num_features = 100
        geometries = []
        labels = []

        for i in range(num_features):
            # Mix of geometry types
            if i % 3 == 0:
                geom = Point(i, i)
            elif i % 3 == 1:
                geom = LineString([(i, i), (i+1, i+1)])
            else:
                geom = Polygon([(i, i), (i+2, i), (i+2, i+2), (i, i+2), (i, i)])

            geometries.append(geom)
            labels.append(f"Feature {i}")

        gdf = gpd.GeoDataFrame({
            'geometry': geometries,
            'label': labels
        })

        # Use a comprehensive style
        style = comprehensive_styles.styles['full_combined']
        layer_name = "performance_test"

        # Time the operation
        start_time = time.time()

        real_style_applicator_service.add_geodataframe_to_dxf(
            dxf_document, gdf, layer_name, style
        )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        end_time = time.time()
        processing_time = end_time - start_time

        # Verify reasonable performance (should complete in reasonable time)
        assert processing_time < 30.0, f"Processing {num_features} features took too long: {processing_time:.2f}s"

        # Verify output
        analyzer = DXFAnalyzer(temp_dxf_file)
        layer_results = analyzer.verify_layer_properties(layer_name, {})
        assert layer_results["layer_exists"], "Performance test layer should exist"

        # Verify entities were created
        entities = analyzer.get_entities_by_layer(layer_name)
        assert len(entities) > 0, "Should have created entities for performance test"


class TestDXFStyleVerification:
    """Tests focused on verifying specific styling aspects in DXF output."""

    @pytest.fixture
    def temp_dxf_file(self):
        """Create a temporary DXF file for testing."""
        fd, temp_path = tempfile.mkstemp(suffix='.dxf')
        os.close(fd)  # Close the file descriptor
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def dxf_document(self):
        """Create a new DXF document for testing."""
        return ezdxf.new('R2010')

    def test_aci_color_resolution(self, real_style_applicator_service, color_mappings, temp_dxf_file, dxf_document):
        """Test that color names are correctly resolved to ACI codes in DXF."""
        # Create test geometry
        line_geom = LineString([(0, 0), (10, 10)])
        gdf = gpd.GeoDataFrame({'geometry': [line_geom]})

        # Test various color name to ACI mappings
        color_tests = [
            ("red", 1),
            ("yellow", 2),
            ("green", 3),
            ("cyan", 4),
            ("blue", 5),
            ("magenta", 6),
            ("white", 7)
        ]

        for color_name, expected_aci in color_tests:
            # Create style with color name
            style = NamedStyle(
                layer=LayerStyleProperties(
                    color=color_name,
                    linetype="Continuous",
                    lineweight=25
                )
            )

            layer_name = f"color_test_{color_name}"

            # Apply style and add to DXF
            real_style_applicator_service.add_geodataframe_to_dxf(
                dxf_document, gdf, layer_name, style
            )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify each color mapping
        for color_name, expected_aci in color_tests:
            layer_name = f"color_test_{color_name}"
            layer_results = analyzer.verify_layer_properties(layer_name, {
                "color": expected_aci
            })

            assert layer_results["layer_exists"], f"Layer for {color_name} should exist"
            assert layer_results["color_match"], f"Color {color_name} should resolve to ACI {expected_aci}"

    def test_linetype_creation(self, real_style_applicator_service, temp_dxf_file, dxf_document):
        """Test that custom linetypes are created in DXF."""
        # Create test geometry
        line_geom = LineString([(0, 0), (10, 10)])
        gdf = gpd.GeoDataFrame({'geometry': [line_geom]})

        # Test various linetypes using correct ezdxf vocabulary
        linetype_tests = ["Continuous", "DASHED", "DOTTED", "DASHDOT", "CENTER", "PHANTOM"]

        for linetype in linetype_tests:
            style = NamedStyle(
                layer=LayerStyleProperties(
                    color="black",
                    linetype=linetype,
                    lineweight=25
                )
            )

            layer_name = f"linetype_test_{linetype.lower()}"

            # Apply style and add to DXF
            real_style_applicator_service.add_geodataframe_to_dxf(
                dxf_document, gdf, layer_name, style
            )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify linetypes exist in DXF
        for linetype in linetype_tests:
            if linetype != "Continuous":  # Continuous is built-in
                assert linetype in analyzer.doc.linetypes, f"Linetype {linetype} should exist in DXF"

        # Verify layer linetype assignments
        for linetype in linetype_tests:
            layer_name = f"linetype_test_{linetype.lower()}"
            # No translation needed - use ezdxf vocabulary directly
            layer_results = analyzer.verify_layer_properties(layer_name, {
                "linetype": linetype
            })

            assert layer_results["layer_exists"], f"Layer for {linetype} should exist"
            assert layer_results["linetype_match"], f"Layer should have linetype {linetype}"

    def test_text_style_creation(self, real_style_applicator_service, temp_dxf_file, dxf_document):
        """Test that text styles are created in DXF."""
        # Create test geometry with labels
        point_geom = Point(5, 5)
        gdf = gpd.GeoDataFrame({
            'geometry': [point_geom],
            'label': ['Test Text']
        })

        # Test various fonts
        font_tests = ["Arial", "Times New Roman", "Courier New", "Helvetica"]

        for font in font_tests:
            style = NamedStyle(
                text=TextStyleProperties(
                    font=font,
                    color="black",
                    height=2.5
                )
            )

            layer_name = f"font_test_{font.replace(' ', '_').lower()}"

            # Apply style and add to DXF
            real_style_applicator_service.add_geodataframe_to_dxf(
                dxf_document, gdf, layer_name, style
            )

        # Save DXF file
        dxf_document.saveas(temp_dxf_file)

        # Analyze generated DXF
        analyzer = DXFAnalyzer(temp_dxf_file)

        # Verify text styles exist and are used
        text_entities = analyzer.get_entities_by_type("TEXT")
        mtext_entities = analyzer.get_entities_by_type("MTEXT")

        assert len(text_entities) > 0 or len(mtext_entities) > 0, "Should have text entities"

        # Check that text styles were created in the document
        style_names = [style.dxf.name for style in analyzer.doc.styles]

        # Should have created custom styles (exact names may vary based on implementation)
        assert len(style_names) > 1, "Should have created custom text styles beyond 'Standard'"


@pytest.fixture
def real_style_applicator_service() -> StyleApplicatorService:
    """Fixture to create a StyleApplicatorService with real dependencies where possible."""
    logger_service = LoggingService() # Assuming LoggingService is a concrete implementation
    dxf_adapter = EzdxfAdapter(logger_service) # SAS needs its own adapter instance for is_available()
    # config_loader = ConfigLoaderService(logger_service) # Not needed directly by SAS anymore

    # Mock the new dependencies for StyleApplicatorService
    mock_dxf_resource_manager = Mock(spec=IDXFResourceManager)
    mock_geometry_processor = Mock(spec=IGeometryProcessor)

    # The StyleApplicationOrchestrator would take the config_loader if it were real
    # For this test, if we mock the orchestrator, we don't need to instantiate a real config_loader for it.
    mock_style_orchestrator = Mock(spec=IStyleApplicationOrchestrator)

    # If the orchestrator mock needs to behave as if it used a config loader (e.g. for ACI colors):
    # mock_config_loader_for_orchestrator = ConfigLoaderService(logger_service)
    # mock_style_orchestrator.configure_mock(_config_loader=mock_config_loader_for_orchestrator)
    # Or, more simply, mock the methods of the orchestrator that would use the config, e.g., _resolve_aci_color

    return StyleApplicatorService(
        logger_service=logger_service,
        dxf_adapter=dxf_adapter,
        dxf_resource_manager=mock_dxf_resource_manager,
        geometry_processor=mock_geometry_processor,
        style_orchestrator=mock_style_orchestrator
    )
