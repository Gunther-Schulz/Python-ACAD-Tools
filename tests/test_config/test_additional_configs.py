"""Tests for additional configuration types."""

import os
import pytest
from src.config.config_manager import ConfigManager, ConfigValidationError
from src.config.position_config import Position
from src.config.legend_config import LegendConfig, LegendsConfig
from src.config.viewport_config import ViewportConfig, ViewportsConfig
from src.config.block_insert_config import BlockInsertConfig, BlockInsertsConfig
from src.config.text_insert_config import TextInsertConfig, TextInsertsConfig
from src.config.path_array_config import PathArrayConfig, PathArraysConfig
from src.config.web_service_config import WebServiceConfig, WebServicesConfig

def test_load_legends(test_project_dir):
    """Test loading legends configuration."""
    # Create legends.yaml
    with open(os.path.join(test_project_dir, "legends.yaml"), "w") as f:
        f.write("""
legends:
  - name: main_legend
    position:
      x: 100.0
      y: 200.0
    style: legend_style
  - name: sub_legend
    position:
      x: 150.0
      y: 250.0
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_legends()
    
    assert "legends" in config
    assert len(config["legends"]) == 2
    
    legend1 = config["legends"][0]
    assert legend1["name"] == "main_legend"
    assert legend1["position"]["x"] == 100.0
    assert legend1["position"]["y"] == 200.0
    assert legend1["style"] == "legend_style"
    
    legend2 = config["legends"][1]
    assert legend2["name"] == "sub_legend"
    assert legend2["position"]["x"] == 150.0
    assert legend2["position"]["y"] == 250.0

def test_load_viewports(test_project_dir):
    """Test loading viewports configuration."""
    # Create viewports.yaml
    with open(os.path.join(test_project_dir, "viewports.yaml"), "w") as f:
        f.write("""
viewports:
  - name: main_view
    center:
      x: 1000.0
      y: 2000.0
    scale: 1.0
    rotation: 45.0
  - name: detail_view
    center:
      x: 1500.0
      y: 2500.0
    scale: 0.5
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_viewports()
    
    assert "viewports" in config
    assert len(config["viewports"]) == 2
    
    view1 = config["viewports"][0]
    assert view1["name"] == "main_view"
    assert view1["center"]["x"] == 1000.0
    assert view1["center"]["y"] == 2000.0
    assert view1["scale"] == 1.0
    assert view1["rotation"] == 45.0
    
    view2 = config["viewports"][1]
    assert view2["name"] == "detail_view"
    assert view2["center"]["x"] == 1500.0
    assert view2["center"]["y"] == 2500.0
    assert view2["scale"] == 0.5
    assert view2.get("rotation", 0) == 0  # Default value

def test_load_block_inserts(test_project_dir):
    """Test loading block inserts configuration."""
    # Create block_inserts.yaml
    with open(os.path.join(test_project_dir, "block_inserts.yaml"), "w") as f:
        f.write("""
blocks:
  - name: title_block
    position:
      x: 0.0
      y: 0.0
    scale: 1.0
    rotation: 0.0
    layer: title
  - name: north_arrow
    position:
      x: 100.0
      y: 100.0
    layer: symbols
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_block_inserts()
    
    assert "blocks" in config
    assert len(config["blocks"]) == 2
    
    block1 = config["blocks"][0]
    assert block1["name"] == "title_block"
    assert block1["position"]["x"] == 0.0
    assert block1["position"]["y"] == 0.0
    assert block1["scale"] == 1.0
    assert block1["rotation"] == 0.0
    assert block1["layer"] == "title"
    
    block2 = config["blocks"][1]
    assert block2["name"] == "north_arrow"
    assert block2["position"]["x"] == 100.0
    assert block2["position"]["y"] == 100.0
    assert block2["layer"] == "symbols"
    assert block2.get("scale", 1.0) == 1.0  # Default value
    assert block2.get("rotation", 0.0) == 0.0  # Default value

def test_load_text_inserts(test_project_dir):
    """Test loading text inserts configuration."""
    # Create text_inserts.yaml
    with open(os.path.join(test_project_dir, "text_inserts.yaml"), "w") as f:
        f.write("""
texts:
  - text: "Project Title"
    position:
      x: 10.0
      y: 20.0
    style: title_style
    layer: text
  - text: "Scale 1:1000"
    position:
      x: 15.0
      y: 25.0
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_text_inserts()
    
    assert "texts" in config
    assert len(config["texts"]) == 2
    
    text1 = config["texts"][0]
    assert text1["text"] == "Project Title"
    assert text1["position"]["x"] == 10.0
    assert text1["position"]["y"] == 20.0
    assert text1["style"] == "title_style"
    assert text1["layer"] == "text"
    
    text2 = config["texts"][1]
    assert text2["text"] == "Scale 1:1000"
    assert text2["position"]["x"] == 15.0
    assert text2["position"]["y"] == 25.0

def test_load_path_arrays(test_project_dir):
    """Test loading path arrays configuration."""
    # Create path_arrays.yaml
    with open(os.path.join(test_project_dir, "path_arrays.yaml"), "w") as f:
        f.write("""
pathArrays:
  - name: fence_posts
    path: "boundary_line"
    block: "post"
    spacing: 2.5
    align: true
    layer: fences
  - name: trees
    path: "garden_path"
    block: "tree"
    spacing: 5.0
    align: false
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_path_arrays()
    
    assert "pathArrays" in config
    assert len(config["pathArrays"]) == 2
    
    array1 = config["pathArrays"][0]
    assert array1["name"] == "fence_posts"
    assert array1["path"] == "boundary_line"
    assert array1["block"] == "post"
    assert array1["spacing"] == 2.5
    assert array1["align"] is True
    assert array1["layer"] == "fences"
    
    array2 = config["pathArrays"][1]
    assert array2["name"] == "trees"
    assert array2["path"] == "garden_path"
    assert array2["block"] == "tree"
    assert array2["spacing"] == 5.0
    assert array2["align"] is False

def test_load_wmts_wms_layers(test_project_dir):
    """Test loading WMTS/WMS layers configuration."""
    # Create wmts_wms_layers.yaml
    with open(os.path.join(test_project_dir, "wmts_wms_layers.yaml"), "w") as f:
        f.write("""
services:
  - name: basemap
    type: wmts
    url: "https://example.com/wmts"
    layer: "topo"
    style: "default"
    format: "image/png"
    crs: "EPSG:25833"
  - name: aerial
    type: wms
    url: "https://example.com/wms"
    layer: "orthophoto"
    crs: "EPSG:25833"
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    config = manager.load_wmts_wms_layers()
    
    assert "services" in config
    assert len(config["services"]) == 2
    
    service1 = config["services"][0]
    assert service1["name"] == "basemap"
    assert service1["type"] == "wmts"
    assert service1["url"] == "https://example.com/wmts"
    assert service1["layer"] == "topo"
    assert service1["style"] == "default"
    assert service1["format"] == "image/png"
    assert service1["crs"] == "EPSG:25833"
    
    service2 = config["services"][1]
    assert service2["name"] == "aerial"
    assert service2["type"] == "wms"
    assert service2["url"] == "https://example.com/wms"
    assert service2["layer"] == "orthophoto"
    assert service2["crs"] == "EPSG:25833"
    assert service2.get("format", "image/png") == "image/png"  # Default value

def test_invalid_configurations(test_project_dir):
    """Test handling of invalid configurations."""
    manager = ConfigManager(test_project_dir)
    
    # Test invalid legends config
    with open(os.path.join(test_project_dir, "legends.yaml"), "w") as f:
        f.write("""
legends:
  - name: invalid_legend
    position:
      x: "not a number"  # Should be a number
      y: 100.0
        """.strip())
    
    with pytest.raises(ConfigValidationError):
        manager.load_legends()
    
    # Test invalid viewports config
    with open(os.path.join(test_project_dir, "viewports.yaml"), "w") as f:
        f.write("""
viewports:
  - name: invalid_viewport
    # Missing required center field
    scale: 1.0
        """.strip())
    
    with pytest.raises(ConfigValidationError):
        manager.load_viewports()
    
    # Test invalid WMTS/WMS config
    with open(os.path.join(test_project_dir, "wmts_wms_layers.yaml"), "w") as f:
        f.write("""
services:
  - name: invalid_service
    type: invalid_type  # Should be wmts or wms
    url: "https://example.com"
    layer: "test"
    crs: "EPSG:25833"
        """.strip())
    
    with pytest.raises(ConfigValidationError):
        manager.load_wmts_wms_layers()

def test_missing_optional_configs(test_project_dir):
    """Test handling of missing optional configuration files."""
    manager = ConfigManager(test_project_dir)
    
    # All these should return empty dictionaries without raising errors
    assert manager.load_legends() == {}
    assert manager.load_viewports() == {}
    assert manager.load_block_inserts() == {}
    assert manager.load_text_inserts() == {}
    assert manager.load_path_arrays() == {}
    assert manager.load_wmts_wms_layers() == {}

def test_position():
    """Test Position configuration."""
    data = {'x': 100.0, 'y': 200.0}
    pos = Position.from_dict(data)
    assert pos.x == 100.0
    assert pos.y == 200.0
    assert pos.to_dict() == data

def test_legend():
    """Test Legend configuration."""
    data = {
        'name': 'test_legend',
        'position': {'x': 100.0, 'y': 200.0},
        'style': 'test_style'
    }
    legend = LegendConfig.from_dict(data)
    assert legend.name == 'test_legend'
    assert legend.position.x == 100.0
    assert legend.position.y == 200.0
    assert legend.style == 'test_style'
    assert legend.to_dict() == data

def test_legends():
    """Test Legends configuration."""
    data = {
        'legends': [
            {
                'name': 'legend1',
                'position': {'x': 100.0, 'y': 200.0}
            },
            {
                'name': 'legend2',
                'position': {'x': 300.0, 'y': 400.0},
                'style': 'test_style'
            }
        ]
    }
    legends = LegendsConfig.from_dict(data)
    assert len(legends.legends) == 2
    assert legends.to_dict() == data

def test_viewport():
    """Test Viewport configuration."""
    data = {
        'name': 'test_viewport',
        'center': {'x': 100.0, 'y': 200.0},
        'scale': 50.0,
        'rotation': 45.0
    }
    viewport = ViewportConfig.from_dict(data)
    assert viewport.name == 'test_viewport'
    assert viewport.center.x == 100.0
    assert viewport.center.y == 200.0
    assert viewport.scale == 50.0
    assert viewport.rotation == 45.0
    assert viewport.to_dict() == data

def test_viewports():
    """Test Viewports configuration."""
    data = {
        'viewports': [
            {
                'name': 'viewport1',
                'center': {'x': 100.0, 'y': 200.0},
                'scale': 50.0
            },
            {
                'name': 'viewport2',
                'center': {'x': 300.0, 'y': 400.0},
                'scale': 75.0,
                'rotation': 90.0
            }
        ]
    }
    viewports = ViewportsConfig.from_dict(data)
    assert len(viewports.viewports) == 2
    assert viewports.to_dict() == data

def test_block_insert():
    """Test BlockInsert configuration."""
    data = {
        'name': 'test_block',
        'position': {'x': 100.0, 'y': 200.0},
        'scale': 2.0,
        'rotation': 45.0,
        'layer': 'test_layer'
    }
    block = BlockInsertConfig.from_dict(data)
    assert block.name == 'test_block'
    assert block.position.x == 100.0
    assert block.position.y == 200.0
    assert block.scale == 2.0
    assert block.rotation == 45.0
    assert block.layer == 'test_layer'
    assert block.to_dict() == data

def test_block_inserts():
    """Test BlockInserts configuration."""
    data = {
        'blocks': [
            {
                'name': 'block1',
                'position': {'x': 100.0, 'y': 200.0}
            },
            {
                'name': 'block2',
                'position': {'x': 300.0, 'y': 400.0},
                'scale': 2.0,
                'rotation': 45.0,
                'layer': 'test_layer'
            }
        ]
    }
    blocks = BlockInsertsConfig.from_dict(data)
    assert len(blocks.blocks) == 2
    assert blocks.to_dict() == data

def test_text_insert():
    """Test TextInsert configuration."""
    data = {
        'text': 'test text',
        'position': {'x': 100.0, 'y': 200.0},
        'style': 'test_style',
        'layer': 'test_layer'
    }
    text = TextInsertConfig.from_dict(data)
    assert text.text == 'test text'
    assert text.position.x == 100.0
    assert text.position.y == 200.0
    assert text.style == 'test_style'
    assert text.layer == 'test_layer'
    assert text.to_dict() == data

def test_text_inserts():
    """Test TextInserts configuration."""
    data = {
        'texts': [
            {
                'text': 'text1',
                'position': {'x': 100.0, 'y': 200.0}
            },
            {
                'text': 'text2',
                'position': {'x': 300.0, 'y': 400.0},
                'style': 'test_style',
                'layer': 'test_layer'
            }
        ]
    }
    texts = TextInsertsConfig.from_dict(data)
    assert len(texts.texts) == 2
    assert texts.to_dict() == data

def test_path_array():
    """Test PathArray configuration."""
    data = {
        'name': 'test_array',
        'path': 'test_path',
        'block': 'test_block',
        'spacing': 50.0,
        'align': True,
        'layer': 'test_layer'
    }
    array = PathArrayConfig.from_dict(data)
    assert array.name == 'test_array'
    assert array.path == 'test_path'
    assert array.block == 'test_block'
    assert array.spacing == 50.0
    assert array.align is True
    assert array.layer == 'test_layer'
    assert array.to_dict() == data

def test_path_arrays():
    """Test PathArrays configuration."""
    data = {
        'pathArrays': [
            {
                'name': 'array1',
                'path': 'path1',
                'block': 'block1',
                'spacing': 50.0
            },
            {
                'name': 'array2',
                'path': 'path2',
                'block': 'block2',
                'spacing': 75.0,
                'align': False,
                'layer': 'test_layer'
            }
        ]
    }
    arrays = PathArraysConfig.from_dict(data)
    assert len(arrays.path_arrays) == 2
    assert arrays.to_dict() == data

def test_web_service():
    """Test WebService configuration."""
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
    assert service.to_dict() == data

def test_web_services():
    """Test WebServices configuration."""
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
    assert services.to_dict() == data

def test_web_service_invalid_type():
    """Test WebService with invalid type."""
    data = {
        'name': 'test_service',
        'type': 'invalid',
        'url': 'https://test.com/invalid',
        'layer': 'test_layer',
        'crs': 'EPSG:3857'
    }
    with pytest.raises(ValueError, match="Invalid service type: invalid"):
        WebServiceConfig.from_dict(data) 