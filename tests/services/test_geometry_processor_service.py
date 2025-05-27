import pytest
from unittest.mock import MagicMock, call, patch
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
import pandas as pd

from src.services.geometry_processor_service import GeometryProcessorService
from src.interfaces.dxf_adapter_interface import IDXFAdapter
from src.interfaces.logging_service_interface import ILoggingService
from src.interfaces.dxf_resource_manager_interface import IDXFResourceManager
from src.domain.geometry_models import GeomLayerDefinition
from src.domain.style_models import NamedStyle, HatchStyleProperties, TextStyleProperties, LayerStyleProperties
from src.domain.exceptions import DXFProcessingError, ConfigError

# Fixtures
@pytest.fixture
def mock_dxf_adapter() -> MagicMock:
    adapter = MagicMock(spec=IDXFAdapter)
    adapter.is_available.return_value = True
    adapter.get_modelspace.return_value = MagicMock(name="mock_modelspace")
    return adapter

@pytest.fixture
def mock_logger_service() -> MagicMock:
    logger = MagicMock(name="mock_logger")
    service = MagicMock(spec=ILoggingService)
    service.get_logger.return_value = logger
    return service

@pytest.fixture
def mock_dxf_resource_manager() -> MagicMock:
    manager = MagicMock(spec=IDXFResourceManager)
    manager.ensure_text_style.return_value = "StandardTextStyle" # Default mock return
    return manager

@pytest.fixture
def geometry_processor_service(
    mock_dxf_adapter: MagicMock,
    mock_logger_service: MagicMock,
    mock_dxf_resource_manager: MagicMock
) -> GeometryProcessorService:
    return GeometryProcessorService(
        dxf_adapter=mock_dxf_adapter,
        logger_service=mock_logger_service,
        dxf_resource_manager=mock_dxf_resource_manager
    )

@pytest.fixture
def mock_dxf_drawing() -> MagicMock:
    return MagicMock(name="mock_dxf_drawing")

# Test Data
def create_sample_gdf(geom_type: str, num_features: int = 1) -> gpd.GeoDataFrame:
    data = []
    for i in range(num_features):
        if geom_type == "Point":
            geom = Point(i, i)
            data.append({"id": i, "label_col": f"Point {i}", "geometry": geom})
        elif geom_type == "LineString":
            geom = LineString([(i, i), (i + 1, i + 1)])
            data.append({"id": i, "label_col": f"Line {i}", "geometry": geom})
        elif geom_type == "Polygon":
            geom = Polygon([(i, i), (i + 1, i), (i + 1, i + 1), (i, i + 1)])
            data.append({"id": i, "label_col": f"Polygon {i}", "geometry": geom})
        elif geom_type == "MultiPoint":
            geom = MultiPoint([Point(i,i), Point(i+0.5, i+0.5)])
            data.append({"id": i, "label_col": f"MultiPoint {i}", "geometry": geom})
        elif geom_type == "MultiLineString":
            geom = MultiLineString([LineString([(i,i), (i+1,i)]), LineString([(i,i+1), (i+1,i+1)])])
            data.append({"id": i, "label_col": f"MultiLineString {i}", "geometry": geom})
        elif geom_type == "MultiPolygon":
            p1 = Polygon([(i,i), (i+0.4,i), (i+0.4,i+0.4), (i,i+0.4)])
            p2 = Polygon([(i+0.5,i+0.5), (i+0.9,i+0.5), (i+0.9,i+0.9), (i+0.5,i+0.9)])
            geom = MultiPolygon([p1,p2])
            data.append({"id": i, "label_col": f"MultiPolygon {i}", "geometry": geom})


    if not data:
        return gpd.GeoDataFrame([], columns=["id", "label_col", "geometry"], crs="EPSG:4326")
    return gpd.GeoDataFrame(data, crs="EPSG:4326")

@pytest.fixture
def sample_style() -> NamedStyle:
    return NamedStyle(
        name="TestStyle",
        layer=LayerStyleProperties(color="red", linetype="Continuous", lineweight=25), # 25 -> 0.25mm
        text=TextStyleProperties(font="Arial", color="blue", height=0.5, rotation=15, attachment_point="MIDDLE_CENTER"),
        hatch=HatchStyleProperties(pattern_name="SOLID", color="green", scale=1.0, angle=0.0)
    )

@pytest.fixture
def sample_layer_def() -> GeomLayerDefinition:
    return GeomLayerDefinition(
        name="TestLayer",
        type="extraction", # or other valid type
        label_column="label_col"
    )

# Tests
def test_add_geodataframe_to_dxf_empty_gdf(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock
):
    """Test that no processing occurs for an empty GeoDataFrame."""
    empty_gdf = create_sample_gdf("Point", 0)
    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, empty_gdf, "EmptyLayer")
    mock_dxf_adapter.get_modelspace.assert_not_called() # Modelspace not needed if GDF is empty
    mock_dxf_adapter.add_point.assert_not_called()
    # logger might be called with debug message, can assert that if needed

def test_add_geodataframe_to_dxf_adapter_not_available(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock
):
    """Test that DXFProcessingError is raised if adapter is not available."""
    mock_dxf_adapter.is_available.return_value = False
    gdf = create_sample_gdf("Point")
    with pytest.raises(DXFProcessingError, match="ezdxf library not available via adapter"):
        geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, "TestLayer")

@pytest.mark.parametrize("geom_type, adapter_method_name", [
    ("Point", "add_point"),
    ("LineString", "add_lwpolyline"),
])
def test_add_simple_geometries(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    geom_type: str,
    adapter_method_name: str
):
    """Test adding simple geometries (Point, LineString)."""
    gdf = create_sample_gdf(geom_type)
    layer_name = f"{geom_type}Layer"
    mock_modelspace = mock_dxf_adapter.get_modelspace.return_value

    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name)

    mock_dxf_adapter.get_modelspace.assert_called_once_with(mock_dxf_drawing)
    adapter_method_to_check = getattr(mock_dxf_adapter, adapter_method_name)
    adapter_method_to_check.assert_called_once()
    call_args = adapter_method_to_check.call_args
    assert call_args[0][0] == mock_modelspace # First arg is modelspace
    assert call_args[1]['dxfattribs']['layer'] == layer_name

def test_add_polygon_with_hatch_and_boundary(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    sample_style: NamedStyle
):
    """Test adding a Polygon with hatch and boundary."""
    gdf = create_sample_gdf("Polygon")
    layer_name = "PolygonLayer"
    mock_modelspace = mock_dxf_adapter.get_modelspace.return_value

    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name, style=sample_style)

    mock_dxf_adapter.get_modelspace.assert_called_once_with(mock_dxf_drawing)

    # Check HATCH creation
    mock_dxf_adapter.add_hatch.assert_called_once()
    hatch_call_args = mock_dxf_adapter.add_hatch.call_args
    assert hatch_call_args[1]['dxfattribs']['layer'] == layer_name
    hatch_entity_mock = mock_dxf_adapter.add_hatch.return_value

    # Check HATCH boundary paths (exterior)
    # Assuming 1 exterior path for a simple polygon
    path_calls = [c for c in mock_dxf_adapter.add_hatch_boundary_path.call_args_list if c[0][0] == hatch_entity_mock]
    assert len(path_calls) >= 1
    assert path_calls[0][1]['flags'] == 1 # BOUNDARY_PATH_EXTERNAL for the first path

    # Check HATCH pattern/solid fill (SOLID in sample_style)
    mock_dxf_adapter.set_hatch_solid_fill.assert_called_once_with(
        hatch_entity_mock,
        # sample_style.hatch.color is "green", needs resolving to ACI if not already int
        # For this test, assume GeometryProcessorService passes ACI directly or resource_manager does it.
        # If direct color name, need to mock color resolution or provide ACI in style.
        # Assuming simple case where "green" is a valid ACI for mock, or test style has ACI
        # color=sample_style.hatch.color # if color is already ACI
    )
    # If pattern: mock_dxf_adapter.set_hatch_pattern_fill.assert_called_once_with(...)


    # Check LWPOLYLINE creation for boundary
    lwpolyline_calls = [
        c for c in mock_dxf_adapter.add_lwpolyline.call_args_list
        if c[1].get('dxfattribs', {}).get('layer') == layer_name and c[1].get('close') is True
    ]
    assert len(lwpolyline_calls) >= 1 # At least one for exterior


def test_add_multipolygon(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    sample_style: NamedStyle
):
    """Test adding a MultiPolygon."""
    gdf = create_sample_gdf("MultiPolygon", num_features=1) # Contains 2 polygons
    layer_name = "MultiPolygonLayer"

    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, gdf, layer_name, style=sample_style)

    # Expect 2 hatches, 2 exterior lwpolylines
    assert mock_dxf_adapter.add_hatch.call_count == 2
    lwpolyline_boundary_calls = [
        c for c in mock_dxf_adapter.add_lwpolyline.call_args_list
        if c[1].get('dxfattribs', {}).get('layer') == layer_name and c[1].get('close') is True
    ]
    assert len(lwpolyline_boundary_calls) == 2


def test_add_multilinestring_and_multipoint(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
):
    """Test adding MultiLineString and MultiPoint."""
    # MultiLineString
    mls_gdf = create_sample_gdf("MultiLineString") # Contains 2 linestrings
    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, mls_gdf, "MultiLineLayer")
    assert mock_dxf_adapter.add_lwpolyline.call_count == 2 # From the 2 sub-linestrings

    mock_dxf_adapter.reset_mock() # Reset for next geom type

    # MultiPoint
    mp_gdf = create_sample_gdf("MultiPoint") # Contains 2 points
    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, mp_gdf, "MultiPointLayer")
    assert mock_dxf_adapter.add_point.call_count == 2 # From the 2 sub-points


def test_label_creation_with_layer_definition(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    mock_dxf_resource_manager: MagicMock, # For ensure_text_style
    sample_style: NamedStyle, # Has text style
    sample_layer_def: GeomLayerDefinition # Has label_column
):
    """Test label creation when layer_definition specifies a label_column."""
    gdf = create_sample_gdf("Point") # Contains "Point 0" in 'label_col'
    layer_name = "LabelLayerDefLayer"
    mock_modelspace = mock_dxf_adapter.get_modelspace.return_value

    geometry_processor_service.add_geodataframe_to_dxf(
        mock_dxf_drawing, gdf, layer_name, style=sample_style, layer_definition=sample_layer_def
    )

    # Point is added
    mock_dxf_adapter.add_point.assert_called_once()

    # Text/MText is added for label
    # As the sample label "Point 0" is simple, expect add_text
    mock_dxf_adapter.add_text.assert_called_once()
    text_call_args = mock_dxf_adapter.add_text.call_args
    assert text_call_args[1]['text'] == "Point 0"
    assert text_call_args[1]['dxfattribs']['layer'] == layer_name
    assert text_call_args[1]['dxfattribs']['style'] == "StandardTextStyle" # from mock_dxf_resource_manager
    assert text_call_args[1]['height'] == sample_style.text.height
    mock_dxf_resource_manager.ensure_text_style.assert_called_once_with(mock_dxf_drawing, sample_style.text)

def test_label_creation_fallback_common_columns(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    sample_style: NamedStyle # Has text style
):
    """Test label creation fallback to common columns like 'label', 'name', 'id' if no layer_def."""
    # Create GDF with a 'name' column but no 'label_col'
    data = [{"id": 0, "name": "FeatureName", "geometry": Point(0,0)}]
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
    layer_name = "LabelCommonColLayer"

    geometry_processor_service.add_geodataframe_to_dxf(
        mock_dxf_drawing, gdf, layer_name, style=sample_style, layer_definition=None # No layer_def
    )
    mock_dxf_adapter.add_text.assert_called_once()
    text_call_args = mock_dxf_adapter.add_text.call_args
    assert text_call_args[1]['text'] == "FeatureName"

def test_mtext_label_creation_for_newline(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_dxf_adapter: MagicMock,
    sample_style: NamedStyle,
    sample_layer_def: GeomLayerDefinition # label_col exists
):
    """Test that MTEXT is used if label text contains newline characters."""
    data = [{"id": 0, "label_col": "Line1\\nLine2", "geometry": Point(0,0)}] # Text with newline
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
    layer_name = "MtextLayer"

    geometry_processor_service.add_geodataframe_to_dxf(
        mock_dxf_drawing, gdf, layer_name, style=sample_style, layer_definition=sample_layer_def
    )
    mock_dxf_adapter.add_mtext.assert_called_once()
    mtext_call_args = mock_dxf_adapter.add_mtext.call_args
    assert mtext_call_args[1]['text'] == "Line1\\nLine2"
    assert mtext_call_args[1]['dxfattribs']['char_height'] == sample_style.text.height
    assert mtext_call_args[1]['dxfattribs']['attachment_point'] == 5 # MIDDLE_CENTER


def test_unsupported_geometry_type_warning(
    geometry_processor_service: GeometryProcessorService,
    mock_dxf_drawing: MagicMock,
    mock_logger_service: MagicMock
):
    """Test that a warning is logged for unsupported geometry types."""
    # Custom geometry type not handled by the service
    class UnknownGeom:
        geom_type = "UnknownGeomType"
        is_empty = False

    data = [{"id": 0, "geometry": UnknownGeom()}]
    # Need a GeoSeries first, then GeoDataFrame
    geoseries = gpd.GeoSeries([UnknownGeom()], crs="EPSG:4326")
    # This direct construction is a bit hacky for a true GDF,
    # but suitable for testing the geom_type dispatch
    # gdf = gpd.GeoDataFrame(data) # This won't work as GDF expects Shapely geometries

    # More robust way to create a GDF with a custom geom type for testing this path
    # is to mock the iterrows() part or the geom object itself.
    # For simplicity, we'll assume if a row's geom.geom_type is something unexpected, it logs.

    # Let's mock the gdf.iterrows() part
    mock_row = pd.Series({"geometry": UnknownGeom(), "id":0})
    mock_gdf = MagicMock(spec=gpd.GeoDataFrame)
    mock_gdf.empty = False
    mock_gdf.iterrows.return_value = [(0, mock_row)]

    mock_logger = mock_logger_service.get_logger.return_value

    geometry_processor_service.add_geodataframe_to_dxf(mock_dxf_drawing, mock_gdf, "UnsupportedGeomLayer")

    # Check if logger.warning was called with a message containing "Unsupported geometry type"
    warning_found = False
    for call_item in mock_logger.warning.call_args_list:
        if "Unsupported geometry type: UnknownGeomType" in call_item[0][0]:
            warning_found = True
            break
    assert warning_found, "Warning for unsupported geometry type not logged"
