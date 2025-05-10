import pytest
import pytest_asyncio
from shapely.geometry import Point, LineString, Polygon
from dxfplanner.services.geoprocessing.label_placement_service import LabelPlacementServiceImpl
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.interfaces import PlacedLabel, IStyleService
from dxfplanner.config.schemas import LabelSettings

class DummyStyleService(IStyleService):
    async def get_text_style_properties(self, text_style_name, layer_name):
        class DummyTextStyle:
            font_properties = type('FontProps', (), {'cap_height': 1.0})()
            height = 1.0
            width_factor = 1.0
        return DummyTextStyle()

@pytest.mark.asyncio
async def test_place_labels_for_features_point():
    # Arrange
    service = LabelPlacementServiceImpl(style_service=DummyStyleService())
    feature = GeoFeature(
        geometry=Point(10, 20),
        attributes={'name': 'TestLabel'}
    )
    config = LabelSettings(
        fixed_label_text=None,
        label_attribute='name',
        text_height=1.0,
        offset=0.0,
        point_position_preference='top-right'
    )
    features = iter([feature])

    async def async_iter(it):
        for x in it:
            yield x

    # Act
    results = []
    async for label in service.place_labels_for_features(async_iter(features), 'TestLayer', config):
        results.append(label)

    # Assert
    assert len(results) == 1
    assert isinstance(results[0], PlacedLabel)
    assert results[0].text == 'TestLabel'
    assert isinstance(results[0].position, Coordinate)

@pytest.mark.asyncio
async def test_place_labels_for_features_line():
    service = LabelPlacementServiceImpl(style_service=DummyStyleService())
    feature = GeoFeature(
        geometry=LineString([(0, 0), (10, 0)]),
        attributes={'name': 'LineLabel'}
    )
    config = LabelSettings(
        fixed_label_text=None,
        label_attribute='name',
        text_height=1.0,
        offset=0.0,
        point_position_preference=None
    )
    features = iter([feature])

    async def async_iter(it):
        for x in it:
            yield x

    results = []
    async for label in service.place_labels_for_features(async_iter(features), 'TestLayer', config):
        results.append(label)

    assert len(results) == 1
    assert isinstance(results[0], PlacedLabel)
    assert results[0].text == 'LineLabel'
    assert isinstance(results[0].position, Coordinate)

@pytest.mark.asyncio
async def test_place_labels_for_features_polygon():
    service = LabelPlacementServiceImpl(style_service=DummyStyleService())
    feature = GeoFeature(
        geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
        attributes={'name': 'PolyLabel'}
    )
    config = LabelSettings(
        fixed_label_text=None,
        label_attribute='name',
        text_height=1.0,
        offset=0.0,
        point_position_preference=None
    )
    features = iter([feature])

    async def async_iter(it):
        for x in it:
            yield x

    results = []
    async for label in service.place_labels_for_features(async_iter(features), 'TestLayer', config):
        results.append(label)

    assert len(results) == 1
    assert isinstance(results[0], PlacedLabel)
    assert results[0].text == 'PolyLabel'
    assert isinstance(results[0].position, Coordinate)

@pytest.mark.asyncio
async def test_place_labels_for_features_missing_geometry():
    service = LabelPlacementServiceImpl(style_service=DummyStyleService())
    feature = GeoFeature(
        geometry=None,
        attributes={'name': 'NoGeom'}
    )
    config = LabelSettings(
        fixed_label_text=None,
        label_attribute='name',
        text_height=1.0,
        offset=0.0,
        point_position_preference=None
    )
    features = iter([feature])

    async def async_iter(it):
        for x in it:
            yield x

    results = []
    async for label in service.place_labels_for_features(async_iter(features), 'TestLayer', config):
        results.append(label)

    assert len(results) == 0

@pytest.mark.asyncio
async def test_place_labels_for_features_missing_label_attribute():
    service = LabelPlacementServiceImpl(style_service=DummyStyleService())
    feature = GeoFeature(
        geometry=Point(1, 2),
        attributes={'other': 'NoLabel'}
    )
    config = LabelSettings(
        fixed_label_text=None,
        label_attribute='name',
        text_height=1.0,
        offset=0.0,
        point_position_preference=None
    )
    features = iter([feature])

    async def async_iter(it):
        for x in it:
            yield x

    results = []
    async for label in service.place_labels_for_features(async_iter(features), 'TestLayer', config):
        results.append(label)

    assert len(results) == 0
