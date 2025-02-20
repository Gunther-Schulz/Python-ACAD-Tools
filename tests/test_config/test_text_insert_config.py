"""Tests for text insert configuration."""

import pytest
from src.config.text_insert_config import TextInsertConfig, TextInsertsConfig
from src.config.position_config import Position

def test_text_insert_config_creation():
    """Test TextInsertConfig creation with valid data."""
    pos = Position(x=100.0, y=200.0)
    text = TextInsertConfig(
        text="test text",
        position=pos,
        style="test_style",
        layer="test_layer"
    )
    assert text.text == "test text"
    assert text.position == pos
    assert text.style == "test_style"
    assert text.layer == "test_layer"

def test_text_insert_config_from_dict():
    """Test TextInsertConfig creation from dictionary."""
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

def test_text_insert_config_to_dict():
    """Test TextInsertConfig conversion to dictionary."""
    text = TextInsertConfig(
        text="test text",
        position=Position(x=100.0, y=200.0),
        style="test_style",
        layer="test_layer"
    )
    data = text.to_dict()
    assert data == {
        'text': 'test text',
        'position': {'x': 100.0, 'y': 200.0},
        'style': 'test_style',
        'layer': 'test_layer'
    }

def test_text_insert_config_optional_fields():
    """Test TextInsertConfig with optional fields."""
    data = {
        'text': 'test text',
        'position': {'x': 100.0, 'y': 200.0}
    }
    text = TextInsertConfig.from_dict(data)
    assert text.style is None
    assert text.layer is None
    
    # Test to_dict with None values
    data = text.to_dict()
    assert 'style' not in data
    assert 'layer' not in data

def test_text_inserts_config_creation():
    """Test TextInsertsConfig creation with valid data."""
    text1 = TextInsertConfig(
        text="text1",
        position=Position(x=100.0, y=200.0)
    )
    text2 = TextInsertConfig(
        text="text2",
        position=Position(x=300.0, y=400.0),
        style="test_style",
        layer="test_layer"
    )
    texts = TextInsertsConfig(texts=[text1, text2])
    assert len(texts.texts) == 2
    assert texts.texts[0] == text1
    assert texts.texts[1] == text2

def test_text_inserts_config_from_dict():
    """Test TextInsertsConfig creation from dictionary."""
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
    assert texts.texts[0].text == 'text1'
    assert texts.texts[1].style == 'test_style'

def test_text_inserts_config_to_dict():
    """Test TextInsertsConfig conversion to dictionary."""
    texts = TextInsertsConfig(texts=[
        TextInsertConfig(
            text="text1",
            position=Position(x=100.0, y=200.0)
        ),
        TextInsertConfig(
            text="text2",
            position=Position(x=300.0, y=400.0),
            style="test_style",
            layer="test_layer"
        )
    ])
    data = texts.to_dict()
    assert data == {
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

def test_text_inserts_config_empty():
    """Test TextInsertsConfig with empty texts list."""
    texts = TextInsertsConfig(texts=[])
    assert len(texts.texts) == 0
    assert texts.to_dict() == {'texts': []} 