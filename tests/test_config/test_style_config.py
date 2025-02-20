"""Tests for style configuration."""

import pytest
from src.config.style_config import (
    LayerProperties,
    EntityProperties,
    TextProperties,
    StyleConfig
)

def test_layer_properties():
    """Test LayerProperties configuration."""
    # Test default values
    props = LayerProperties()
    assert props.color is None
    assert props.plot is True
    assert props.frozen is False
    
    # Test custom values
    props = LayerProperties(
        color="red",
        linetype="CONTINUOUS",
        lineweight=13
    )
    assert props.color == "red"
    assert props.linetype == "CONTINUOUS"
    assert props.lineweight == 13
    
    # Test from_dict
    data = {
        'color': "blue",
        'lineweight': 15,
        'frozen': True
    }
    props = LayerProperties.from_dict(data)
    assert props.color == "blue"
    assert props.lineweight == 15
    assert props.frozen is True
    
    # Test to_dict
    data = props.to_dict()
    assert data['color'] == "blue"
    assert data['lineweight'] == 15
    assert data['frozen'] is True

def test_entity_properties():
    """Test EntityProperties configuration."""
    # Test default values
    props = EntityProperties()
    assert props.close is True
    assert props.linetype_scale == 1.0
    assert props.linetype_generation is False
    
    # Test custom values
    props = EntityProperties(
        close=False,
        linetype_scale=2.0,
        linetype_generation=True
    )
    assert props.close is False
    assert props.linetype_scale == 2.0
    assert props.linetype_generation is True
    
    # Test from_dict
    data = {
        'close': False,
        'linetypeScale': 0.5
    }
    props = EntityProperties.from_dict(data)
    assert props.close is False
    assert props.linetype_scale == 0.5
    assert props.linetype_generation is False
    
    # Test to_dict
    data = props.to_dict()
    assert data['close'] is False
    assert data['linetypeScale'] == 0.5
    assert data['linetypeGeneration'] is False

def test_text_properties():
    """Test TextProperties configuration."""
    # Test default values
    props = TextProperties()
    assert props.height == 2.5
    assert props.font == "Arial"
    assert props.color is None
    
    # Test custom values
    props = TextProperties(
        height=3.0,
        font="Helvetica",
        color="red",
        attachment_point="TOP_LEFT"
    )
    assert props.height == 3.0
    assert props.font == "Helvetica"
    assert props.color == "red"
    assert props.attachment_point == "TOP_LEFT"
    
    # Test from_dict
    data = {
        'height': 4.0,
        'font': "Times",
        'color': "blue",
        'attachmentPoint': "MIDDLE_CENTER",
        'paragraph': {
            'align': "CENTER"
        }
    }
    props = TextProperties.from_dict(data)
    assert props.height == 4.0
    assert props.font == "Times"
    assert props.color == "blue"
    assert props.attachment_point == "MIDDLE_CENTER"
    assert props.paragraph_align == "CENTER"
    
    # Test to_dict
    data = props.to_dict()
    assert data['height'] == 4.0
    assert data['font'] == "Times"
    assert data['color'] == "blue"
    assert data['attachmentPoint'] == "MIDDLE_CENTER"
    assert data['paragraph']['align'] == "CENTER"

def test_style_config():
    """Test StyleConfig configuration."""
    # Test minimal style
    style = StyleConfig(
        layer_properties=LayerProperties(),
        entity_properties=EntityProperties()
    )
    assert style.text_properties is None
    
    # Test complete style
    style = StyleConfig(
        layer_properties=LayerProperties(color="red"),
        entity_properties=EntityProperties(close=False),
        text_properties=TextProperties(height=3.0)
    )
    assert style.layer_properties.color == "red"
    assert style.entity_properties.close is False
    assert style.text_properties.height == 3.0
    
    # Test from_dict
    data = {
        'layer': {
            'color': "blue",
            'lineweight': 13
        },
        'entity': {
            'close': True,
            'linetypeScale': 2.0
        },
        'text': {
            'height': 4.0,
            'color': "red"
        }
    }
    style = StyleConfig.from_dict(data)
    assert style.layer_properties.color == "blue"
    assert style.layer_properties.lineweight == 13
    assert style.entity_properties.close is True
    assert style.entity_properties.linetype_scale == 2.0
    assert style.text_properties.height == 4.0
    assert style.text_properties.color == "red"
    
    # Test to_dict
    data = style.to_dict()
    assert data['layer']['color'] == "blue"
    assert data['layer']['lineweight'] == 13
    assert data['entity']['close'] is True
    assert data['entity']['linetypeScale'] == 2.0
    assert data['text']['height'] == 4.0
    assert data['text']['color'] == "red" 