import pytest
from unittest.mock import MagicMock, call, patch, ANY
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
import pandas as pd
from ezdxf.document import Drawing
from ezdxf.enums import MTextEntityAlignment

from src.services.geometry_processor_service import GeometryProcessorService
from src.services.logging_service import LoggingService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.style_models import NamedStyle, HatchStyleProperties, TextStyleProperties, LayerStyleProperties
from src.domain.exceptions import DXFProcessingError

# Fixtures
@pytest.fixture
def real_logger_service() -> LoggingService:
    return LoggingService()

@pytest.fixture
def mock_dxf_adapter() -> MagicMock:
    adapter = MagicMock(spec=IDXFAdapter)
    adapter.is_available.return_value = True
    adapter.get_modelspace.return_value = MagicMock(name="mock_modelspace_instance")
    adapter.add_hatch.return_value = MagicMock(name="mock_hatch_entity")
    adapter.add_point.return_value = MagicMock(name="mock_point_entity")
    adapter.add_lwpolyline.return_value = MagicMock(name="mock_lwpolyline_entity")
    adapter.add_text.return_value = MagicMock(name="mock_text_entity")
    adapter.add_mtext.return_value = MagicMock(name="mock_mtext_entity")
    return adapter

@pytest.fixture
def mock_dxf_resource_manager() -> MagicMock:
    manager = MagicMock(spec=IDXFResourceManager)
    manager.ensure_text_style.return_value = "MockedTextStyleName"
    return manager

@pytest.fixture
def mock_dxf_drawing() -> MagicMock:
    return MagicMock(spec=Drawing)

@pytest.fixture
def processor_real_logger(
    mock_dxf_adapter: MagicMock,
    real_logger_service: LoggingService,
    mock_dxf_resource_manager: MagicMock
) -> GeometryProcessorService:
    return GeometryProcessorService(
        dxf_adapter=mock_dxf_adapter,
        logger_service=real_logger_service,
        dxf_resource_manager=mock_dxf_resource_manager
    )

@pytest.fixture
def processor(processor_real_logger: GeometryProcessorService) -> GeometryProcessorService:
    return processor_real_logger

# Test Data
def create_sample_gdf(geom_type: str, num_features: int = 1, custom_props: dict = None) -> gpd.GeoDataFrame:
    data = []
    base_props = {"id": 0, "name": "DefaultName", "label": "DefaultLabel", "description": "DefaultDesc"}
    if custom_props:
        base_props.update(custom_props)

    for i in range(num_features):
        current_props = base_props.copy()
        current_props["id"] = i
        if "name" not in (custom_props or {}): current_props["name"] = f"{geom_type}Name{i}"
        if "label" not in (custom_props or {}): current_props["label"] = f"{geom_type}Label{i}"

        if geom_type == "Point":
            geom = Point(i, i)
        elif geom_type == "LineString":
            geom = LineString([(i, i), (i + 1, i + 1)])
        elif geom_type == "Polygon":
            geom = Polygon([(i, i), (i + 1, i), (i + 1, i + 1), (i, i + 1)])
        elif geom_type == "MultiPoint":
            geom = MultiPoint([Point(i,i), Point(i+0.5, i+0.5)])
        elif geom_type == "MultiLineString":
            geom = MultiLineString([LineString([(i,i), (i+1,i)]), LineString([(i,i+1), (i+1,i+1)])])
        elif geom_type == "MultiPolygon":
            p1 = Polygon([(i,i), (i+0.4,i), (i+0.4,i+0.4), (i,i+0.4)])
            p2 = Polygon([(i+0.5,i+0.5), (i+0.9,i+0.5), (i+0.9,i+0.9), (i+0.5,i+0.9)])
            geom = MultiPolygon([p1,p2])
        else:
            raise ValueError(f"Unsupported geom_type for test data: {geom_type}")

        current_props["geometry"] = geom
        data.append(current_props)

    if not data:
        return gpd.GeoDataFrame([], columns=list(base_props.keys()) + ["geometry"], crs="EPSG:4326")
    return gpd.GeoDataFrame(data, crs="EPSG:4326")

@pytest.fixture
def sample_style_all_defined() -> NamedStyle:
    return NamedStyle(
        name="ComprehensiveStyle",
        layer=LayerStyleProperties(color=1, linetype="DASHED", lineweight=30),
        text=TextStyleProperties(font="Arial", color=4, height=0.7, rotation=0, attachment_point="TOP_LEFT"),
        hatch=HatchStyleProperties(pattern_name="ANSI31", color=3, scale=0.5, angle=45.0)
    )

@pytest.fixture
def sample_style_solid_hatch() -> NamedStyle:
    return NamedStyle(
        name="SolidHatchStyle",
        hatch=HatchStyleProperties(pattern_name="SOLID", color=2)
    )

@pytest.fixture
def sample_layer_def_with_label_col() -> GeomLayerDefinition:
    return GeomLayerDefinition(name="MyLayer", type="detail", label_column="custom_label_field")

# Tests
class TestAddGeodataframeToDXF_BasicOperation:

    def test_empty_gdf_logs_debug_and_returns(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock, caplog
    ):
        empty_gdf = create_sample_gdf("Point", 0)
        layer_name = "EmptyLayer"

        with caplog.at_level("DEBUG", logger="src.services.geometry_processor_service"):
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, empty_gdf, layer_name)

        assert f"GeoDataFrame for layer '{layer_name}' is empty. No geometries to add." in caplog.text
        mock_dxf_adapter.get_modelspace.assert_not_called()
        mock_dxf_adapter.add_point.assert_not_called()

    def test_adapter_not_available_raises_dxf_processing_error(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock
    ):
        mock_dxf_adapter.is_available.return_value = False
        gdf = create_sample_gdf("Point")

        with pytest.raises(DXFProcessingError, match="Cannot add geometries to DXF: ezdxf library not available via adapter."):
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, "TestLayer")
        mock_dxf_adapter.get_modelspace.assert_not_called()

    def test_unsupported_geometry_type_logs_warning_and_skips_feature(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock, caplog
    ):
        class UnsupportedGeom: geom_type = "HyperNURBS"; is_empty = False

        mixed_gdf_data = [
            {"id": 0, "geometry": Point(1,1)},
            {"id": 1, "geometry": UnsupportedGeom()}
        ]
        geometries = gpd.GeoSeries([Point(1,1), UnsupportedGeom()])
        mock_gdf = gpd.GeoDataFrame({'id': [0,1], 'geometry': geometries})

        layer_name = "MixedGeomLayer"

        with caplog.at_level("WARNING", logger="src.services.geometry_processor_service"):
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, mock_gdf, layer_name)

        assert "Unsupported geometry type: HyperNURBS for feature 1" in caplog.text
        mock_dxf_adapter.add_point.assert_called_once()

    def test_individual_geometry_processing_error_logs_warning_and_continues(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock, caplog
    ):
        gdf = create_sample_gdf("Point", num_features=2)

        call_count = 0
        def side_effect_add_point(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated adapter error for first point")
            return MagicMock(name="mock_point_entity")
        mock_dxf_adapter.add_point.side_effect = side_effect_add_point

        layer_name = "ErrorHandlingLayer"
        with caplog.at_level("WARNING", logger="src.services.geometry_processor_service"):
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name)

        assert "Failed to add geometry part for index 0 (type: Point) to DXF: Simulated adapter error for first point" in caplog.text
        assert mock_dxf_adapter.add_point.call_count == 2
        assert "Processed 1 primary geometry entities" in caplog.text

    def test_add_gdf_with_none_drawing_raises_error(self, processor: GeometryProcessorService):
        """Test add_geodataframe_to_dxf with dxf_drawing=None."""
        gdf = create_sample_gdf("Point")
        # Expect AttributeError if get_modelspace is called on None, or specific check in service
        with pytest.raises((AttributeError, DXFProcessingError, TypeError)):
            processor.add_geodataframe_to_dxf(None, gdf, "TestLayerNoneDrawing")

    def test_add_gdf_with_none_gdf_raises_error(self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock):
        """Test add_geodataframe_to_dxf with gdf=None."""
        # Expect AttributeError if gdf.empty is called on None, or specific check
        with pytest.raises((AttributeError, TypeError)):
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, None, "TestLayerNoneGDF")

    def test_add_gdf_missing_geometry_column_logs_error(self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, caplog):
        """Test GDF missing 'geometry' column is handled (e.g. KeyError caught)."""
        bad_gdf = pd.DataFrame({'id': [1, 2], 'name': ['A', 'B']})
        layer_name = "BadGDFLayer"

        # The service's main try-except should catch KeyErrors from row.geometry if it occurs before geom type check
        # or an error if geom is assigned None and then accessed.
        # It should log and raise DXFProcessingError or complete without adding entities.
        with caplog.at_level("ERROR", logger="src.services.geometry_processor_service"):
            with pytest.raises(DXFProcessingError, match=f"Failed to add geometries to DXF layer '{layer_name}'"):
                processor.add_geodataframe_to_dxf(mock_dxf_drawing, bad_gdf, layer_name) # type: ignore

        assert f"Major error in add_geodataframe_to_dxf for layer '{layer_name}'" in caplog.text
        # Check for specific mention of KeyError or similar if possible, depends on logging detail
        # assert "KeyError: 'geometry'" in caplog.text # This might be too specific to internal error message

    def test_add_gdf_with_none_geometry_in_row_skips_and_logs(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock, caplog
    ):
        """Test GDF with a row containing None geometry is skipped and logged."""
        gdf_with_none = gpd.GeoDataFrame([
            {'id': 0, 'geometry': Point(1,1)},
            {'id': 1, 'geometry': None},
            {'id': 2, 'geometry': Point(2,2)}
        ])
        layer_name = "NoneGeomInRowLayer"
        with caplog.at_level("DEBUG"): # Service logs geom is None or empty at DEBUG
            processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf_with_none, layer_name)

        # Point for id=1 has None geometry, so it should be skipped.
        # Check if the DEBUG log for skipping is present, though not strictly an error.
        # The primary check is that it doesn't crash and processes other valid geometries.
        mock_dxf_adapter.add_point.assert_any_call(ANY, location=(1.0,1.0,0.0), dxfattribs={'layer': layer_name})
        mock_dxf_adapter.add_point.assert_any_call(ANY, location=(2.0,2.0,0.0), dxfattribs={'layer': layer_name})
        assert mock_dxf_adapter.add_point.call_count == 2

class TestAddGeodataframeToDXF_SimpleGeometries:
    @pytest.mark.parametrize("geom_type, adapter_method_name, num_sub_geoms", [
        ("Point", "add_point", 1),
        ("LineString", "add_lwpolyline", 1),
        ("MultiPoint", "add_point", 2),
        ("MultiLineString", "add_lwpolyline", 2)
    ])
    def test_add_simple_and_multi_geometries_calls_adapter_correctly(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        geom_type: str, adapter_method_name: str, num_sub_geoms: int
    ):
        gdf = create_sample_gdf(geom_type)
        layer_name = f"{geom_type}Layer"
        mock_modelspace_instance = mock_dxf_adapter.get_modelspace.return_value

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name)

        mock_dxf_adapter.get_modelspace.assert_called_once_with(mock_dxf_drawing)
        adapter_method_mock = getattr(mock_dxf_adapter, adapter_method_name)

        assert adapter_method_mock.call_count == num_sub_geoms
        call_args = adapter_method_mock.call_args_list[0]
        assert call_args[0][0] == mock_modelspace_instance
        assert call_args[1]['dxfattribs']['layer'] == layer_name

        if geom_type == "Point":
            expected_coords = (0.0, 0.0, 0.0)
            assert call_args[1]['location'] == expected_coords
        elif geom_type == "LineString":
            expected_coords = [(0.0,0.0), (1.0,1.0)]
            assert call_args[1]['points'] == expected_coords

class TestAddGeodataframeToDXF_PolygonsAndHatches:
    def test_polygon_with_solid_hatch_style_calls_adapter_correctly(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_solid_hatch: NamedStyle
    ):
        gdf = create_sample_gdf("Polygon")
        layer_name = "SolidHatchPolyLayer"
        mock_modelspace_instance = mock_dxf_adapter.get_modelspace.return_value

        hatch_entity_mock = MagicMock(name="specific_hatch_for_solid_test")
        mock_dxf_adapter.add_hatch.return_value = hatch_entity_mock

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name, style=sample_style_solid_hatch)

        mock_dxf_adapter.add_hatch.assert_called_once_with(
            mock_modelspace_instance,
            color=sample_style_solid_hatch.hatch.color,
            dxfattribs={'layer': layer_name}
        )
        mock_dxf_adapter.add_hatch_boundary_path.assert_any_call(
            hatch_entity_mock,
            points=ANY,
            flags=BOUNDARY_PATH_EXTERNAL
        )
        mock_dxf_adapter.set_hatch_solid_fill.assert_called_once_with(
            hatch_entity_mock, sample_style_solid_hatch.hatch.color
        )
        mock_dxf_adapter.set_hatch_pattern_fill.assert_not_called()

        mock_dxf_adapter.add_lwpolyline.assert_any_call(
            mock_modelspace_instance, points=ANY, close=True, dxfattribs={'layer': layer_name}
        )

    def test_polygon_with_pattern_hatch_style_calls_adapter_correctly(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_all_defined: NamedStyle
    ):
        gdf = create_sample_gdf("Polygon")
        layer_name = "PatternHatchPolyLayer"
        hatch_style = sample_style_all_defined.hatch

        hatch_entity_mock = MagicMock(name="specific_hatch_for_pattern_test")
        mock_dxf_adapter.add_hatch.return_value = hatch_entity_mock

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name, style=sample_style_all_defined)

        mock_dxf_adapter.add_hatch.assert_called_once_with(
            ANY,
            color=None,
            dxfattribs={'layer': layer_name}
        )
        mock_dxf_adapter.set_hatch_pattern_fill.assert_called_once_with(
            hatch_entity=hatch_entity_mock,
            pattern_name=hatch_style.pattern_name,
            color=hatch_style.color,
            scale=hatch_style.scale,
            angle=hatch_style.angle
        )
        mock_dxf_adapter.set_hatch_solid_fill.assert_not_called()

    def test_multipolygon_processes_each_sub_polygon_for_hatch_and_boundary(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_solid_hatch: NamedStyle
    ):
        gdf = create_sample_gdf("MultiPolygon", num_features=1)
        layer_name = "MultiPolyLayer"

        hatch_mocks = [MagicMock(name=f"hatch_{i}") for i in range(2)]
        mock_dxf_adapter.add_hatch.side_effect = hatch_mocks

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name, style=sample_style_solid_hatch)

        assert mock_dxf_adapter.add_hatch.call_count == 2
        assert mock_dxf_adapter.set_hatch_solid_fill.call_count == 2
        for hm in hatch_mocks:
            mock_dxf_adapter.add_hatch_boundary_path.assert_any_call(hm, points=ANY, flags=BOUNDARY_PATH_EXTERNAL)

        assert mock_dxf_adapter.add_lwpolyline.call_count == 2 * gdf.iloc[0].geometry.geoms[0].interiors.__len__() + 2
        lwpolyline_boundary_calls = [
            c for c in mock_dxf_adapter.add_lwpolyline.call_args_list
            if c[1].get('dxfattribs',{}).get('layer') == layer_name and c[1].get('close') is True
        ]
        assert len(lwpolyline_boundary_calls) == 2

    def test_process_single_polygon_adapter_errors_are_logged(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_solid_hatch: NamedStyle, caplog
    ):
        """Test that errors from adapter calls in _process_single_polygon_for_dxf are logged."""
        polygon = Polygon([(0,0), (1,0), (1,1), (0,1)])
        msp = mock_dxf_adapter.get_modelspace.return_value
        layer_name = "PolyErrorLayer"

        # Test add_hatch error
        mock_dxf_adapter.add_hatch.side_effect = DXFProcessingError("Hatch creation failed")
        caplog.clear()
        with caplog.at_level("WARNING"):
            processor._process_single_polygon_for_dxf(msp, polygon, layer_name, sample_style_solid_hatch, mock_dxf_drawing)
        assert "Failed to create or style HATCH for polygon: Hatch creation failed" in caplog.text
        mock_dxf_adapter.add_hatch.side_effect = None # Reset side effect
        mock_dxf_adapter.add_hatch.return_value = MagicMock() # Return a mock hatch for next tests

        # Test add_hatch_boundary_path error
        mock_dxf_adapter.add_hatch_boundary_path.side_effect = DXFProcessingError("Boundary path failed")
        caplog.clear()
        with caplog.at_level("WARNING"):
            processor._process_single_polygon_for_dxf(msp, polygon, layer_name, sample_style_solid_hatch, mock_dxf_drawing)
        assert "Failed to create or style HATCH for polygon: Boundary path failed" in caplog.text
        mock_dxf_adapter.add_hatch_boundary_path.side_effect = None

        # Test set_hatch_solid_fill error
        mock_dxf_adapter.set_hatch_solid_fill.side_effect = DXFProcessingError("Solid fill failed")
        caplog.clear()
        with caplog.at_level("WARNING"):
            processor._process_single_polygon_for_dxf(msp, polygon, layer_name, sample_style_solid_hatch, mock_dxf_drawing)
        assert "Failed to create or style HATCH for polygon: Solid fill failed" in caplog.text
        mock_dxf_adapter.set_hatch_solid_fill.side_effect = None

        # Test add_lwpolyline error for boundary (should still log but not stop all processing if in a loop)
        # Note: _process_single_polygon_for_dxf itself is not in a loop here, so this error would propagate if not caught inside it.
        # The current implementation doesn't catch errors from add_lwpolyline within _process_single_polygon_for_dxf.
        # This might be an area for improvement in the service if granular error handling per polygon part is needed.

class TestAddGeodataframeToDXF_Labels:
    def test_label_from_layer_definition_column_uses_add_text_correctly(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        mock_dxf_resource_manager: MagicMock, sample_style_all_defined: NamedStyle,
        sample_layer_def_with_label_col: GeomLayerDefinition
    ):
        custom_label_value = "My Custom Label Text"
        gdf = create_sample_gdf("Point", custom_props={sample_layer_def_with_label_col.label_column: custom_label_value})
        layer_name = "LayerDefLabelLayer"
        text_style_props = sample_style_all_defined.text

        expected_text_dxf_style_name = "TextStyleFromManager"
        mock_dxf_resource_manager.ensure_text_style.return_value = expected_text_dxf_style_name

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name,
                                          style=sample_style_all_defined,
                                          layer_definition=sample_layer_def_with_label_col)

        mock_dxf_resource_manager.ensure_text_style.assert_called_once_with(mock_dxf_drawing, text_style_props)

        mock_dxf_adapter.add_text.assert_called_once()
        text_call_args = mock_dxf_adapter.add_text.call_args[1]

        assert text_call_args['text'] == custom_label_value
        assert text_call_args['height'] == text_style_props.height
        assert text_call_args['rotation'] == text_style_props.rotation
        assert text_call_args['dxfattribs']['layer'] == layer_name
        assert text_call_args['dxfattribs']['style'] == expected_text_dxf_style_name
        assert text_call_args['dxfattribs']['color'] == text_style_props.color
        assert text_call_args['dxfattribs']['halign'] == 0
        assert text_call_args['dxfattribs']['valign'] == 3
        assert 'align_point' in text_call_args['dxfattribs']

    def test_label_with_newline_uses_add_mtext_correctly(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        mock_dxf_resource_manager: MagicMock, sample_style_all_defined: NamedStyle,
        sample_layer_def_with_label_col: GeomLayerDefinition
    ):
        label_with_newline = "First Line\\nSecond Line"
        gdf = create_sample_gdf("Point", custom_props={sample_layer_def_with_label_col.label_column: label_with_newline})
        layer_name = "MtextLabelLayer"
        text_style_props = sample_style_all_defined.text
        expected_text_dxf_style_name = "TextStyleForMtext"
        mock_dxf_resource_manager.ensure_text_style.return_value = expected_text_dxf_style_name

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name,
                                          style=sample_style_all_defined,
                                          layer_definition=sample_layer_def_with_label_col)

        mock_dxf_adapter.add_mtext.assert_called_once()
        mtext_call_args = mock_dxf_adapter.add_mtext.call_args[1]

        assert mtext_call_args['text'] == label_with_newline
        assert mtext_call_args['dxfattribs']['char_height'] == text_style_props.height
        assert mtext_call_args['dxfattribs']['rotation'] == text_style_props.rotation
        assert mtext_call_args['dxfattribs']['layer'] == layer_name
        assert mtext_call_args['dxfattribs']['style'] == expected_text_dxf_style_name
        assert mtext_call_args['dxfattribs']['color'] == text_style_props.color
        assert mtext_call_args['dxfattribs']['attachment_point'] == MTextEntityAlignment.TOP_LEFT.value

        mock_dxf_adapter.add_text.assert_not_called()

    @pytest.mark.parametrize("common_col_name, common_col_value", [
        ("label", "From Label Col"),
        ("name", "From Name Col"),
        ("id", "ID123"),
        ("text", "From Text Col"),
        ("description", "From Description Col")
    ])
    def test_label_fallback_to_common_columns_without_layer_def(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_all_defined: NamedStyle, common_col_name: str, common_col_value: str
    ):
        gdf = create_sample_gdf("Point", custom_props={common_col_name: common_col_value})
        for col in ['label', 'name', 'id', 'text', 'description']:
            if col != common_col_name and col in gdf.columns:
                del gdf[col]
        if common_col_name != 'id':
             gdf[common_col_name] = common_col_value

        layer_name = "FallbackLabelLayer"
        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name,
                                          style=sample_style_all_defined,
                                          layer_definition=None)

        mock_dxf_adapter.add_text.assert_called_once()
        assert mock_dxf_adapter.add_text.call_args[1]['text'] == str(common_col_value)

    def test_no_label_if_no_specified_or_fallback_column_has_text(
        self, processor: GeometryProcessorService, mock_dxf_drawing: MagicMock, mock_dxf_adapter: MagicMock,
        sample_style_all_defined: NamedStyle
    ):
        gdf = create_sample_gdf("Point", custom_props={"other_data": "some value"})
        for col in ['label', 'name', 'id', 'text', 'description', 'custom_label_field']:
            if col in gdf.columns:
                del gdf[col]

        layer_def_no_label_col = GeomLayerDefinition(name="NoLabelLayer", type="generic", label_column=None)

        processor.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, "NoLabelLayer",
                                          style=sample_style_all_defined,
                                          layer_definition=layer_def_no_label_col)

        mock_dxf_adapter.add_text.assert_not_called()
        mock_dxf_adapter.add_mtext.assert_not_called()
