"""Tests for web service configuration."""

import pytest
from src.config.web_service_config import WebServiceConfig, WebServicesConfig

def test_web_service_config_creation():
    """Test WebServiceConfig creation with valid data."""
    service = WebServiceConfig(
        name="test_service",
        type="wmts",
        url="https://test.com/wmts",
        layer="test_layer",
        crs="EPSG:3857",
        style="test_style",
        format="image/jpeg"
    )
    assert service.name == "test_service"
    assert service.type == "wmts"
    assert service.url == "https://test.com/wmts"
    assert service.layer == "test_layer"
    assert service.crs == "EPSG:3857"
    assert service.style == "test_style"
    assert service.format == "image/jpeg"

def test_web_service_config_from_dict():
    """Test WebServiceConfig creation from dictionary."""
    data = {
        'name': 'test_service',
        'type': 'wmts',
        'url': 'https://test.com/wmts',
        'layer': 'test_layer',
        'crs': 'EPSG:3857',
        'style': 'test_style',
        'format': 'image/jpeg'
    }
    service = WebServiceConfig.from_dict(data)
    assert service.name == 'test_service'
    assert service.type == 'wmts'
    assert service.url == 'https://test.com/wmts'
    assert service.layer == 'test_layer'
    assert service.crs == 'EPSG:3857'
    assert service.style == 'test_style'
    assert service.format == 'image/jpeg'

def test_web_service_config_to_dict():
    """Test WebServiceConfig conversion to dictionary."""
    service = WebServiceConfig(
        name="test_service",
        type="wmts",
        url="https://test.com/wmts",
        layer="test_layer",
        crs="EPSG:3857",
        style="test_style",
        format="image/jpeg"
    )
    data = service.to_dict()
    assert data == {
        'name': 'test_service',
        'type': 'wmts',
        'url': 'https://test.com/wmts',
        'layer': 'test_layer',
        'crs': 'EPSG:3857',
        'style': 'test_style',
        'format': 'image/jpeg'
    }

def test_web_service_config_defaults():
    """Test WebServiceConfig with default values."""
    data = {
        'name': 'test_service',
        'type': 'wmts',
        'url': 'https://test.com/wmts',
        'layer': 'test_layer',
        'crs': 'EPSG:3857'
    }
    service = WebServiceConfig.from_dict(data)
    assert service.style is None  # Default style
    assert service.format == "image/png"  # Default format
    
    # Test to_dict with default values
    data = service.to_dict()
    assert data['format'] == "image/png"
    assert 'style' not in data

def test_web_service_config_invalid_type():
    """Test WebServiceConfig with invalid service type."""
    data = {
        'name': 'test_service',
        'type': 'invalid',
        'url': 'https://test.com/invalid',
        'layer': 'test_layer',
        'crs': 'EPSG:3857'
    }
    with pytest.raises(ValueError, match="Invalid service type: invalid"):
        WebServiceConfig.from_dict(data)

def test_web_services_config_creation():
    """Test WebServicesConfig creation with valid data."""
    service1 = WebServiceConfig(
        name="service1",
        type="wmts",
        url="https://test.com/wmts",
        layer="layer1",
        crs="EPSG:3857"
    )
    service2 = WebServiceConfig(
        name="service2",
        type="wms",
        url="https://test.com/wms",
        layer="layer2",
        crs="EPSG:4326",
        style="test_style",
        format="image/jpeg"
    )
    services = WebServicesConfig(services=[service1, service2])
    assert len(services.services) == 2
    assert services.services[0] == service1
    assert services.services[1] == service2

def test_web_services_config_from_dict():
    """Test WebServicesConfig creation from dictionary."""
    data = {
        'services': [
            {
                'name': 'service1',
                'type': 'wmts',
                'url': 'https://test.com/wmts',
                'layer': 'layer1',
                'crs': 'EPSG:3857'
            },
            {
                'name': 'service2',
                'type': 'wms',
                'url': 'https://test.com/wms',
                'layer': 'layer2',
                'crs': 'EPSG:4326',
                'style': 'test_style',
                'format': 'image/jpeg'
            }
        ]
    }
    services = WebServicesConfig.from_dict(data)
    assert len(services.services) == 2
    assert services.services[0].type == 'wmts'
    assert services.services[1].format == 'image/jpeg'

def test_web_services_config_to_dict():
    """Test WebServicesConfig conversion to dictionary."""
    services = WebServicesConfig(services=[
        WebServiceConfig(
            name="service1",
            type="wmts",
            url="https://test.com/wmts",
            layer="layer1",
            crs="EPSG:3857"
        ),
        WebServiceConfig(
            name="service2",
            type="wms",
            url="https://test.com/wms",
            layer="layer2",
            crs="EPSG:4326",
            style="test_style",
            format="image/jpeg"
        )
    ])
    data = services.to_dict()
    assert data == {
        'services': [
            {
                'name': 'service1',
                'type': 'wmts',
                'url': 'https://test.com/wmts',
                'layer': 'layer1',
                'crs': 'EPSG:3857',
                'format': 'image/png'
            },
            {
                'name': 'service2',
                'type': 'wms',
                'url': 'https://test.com/wms',
                'layer': 'layer2',
                'crs': 'EPSG:4326',
                'style': 'test_style',
                'format': 'image/jpeg'
            }
        ]
    }

def test_web_services_config_empty():
    """Test WebServicesConfig with empty services list."""
    services = WebServicesConfig(services=[])
    assert len(services.services) == 0
    assert services.to_dict() == {'services': []} 