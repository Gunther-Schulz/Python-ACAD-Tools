"""Tests for block insert configuration."""

import pytest
from src.config.block_insert_config import BlockInsertConfig, BlockInsertsConfig
from src.config.position_config import Position

def test_block_insert_config_creation():
    """Test BlockInsertConfig creation with valid data."""
    pos = Position(x=100.0, y=200.0)
    block = BlockInsertConfig(
        name="test_block",
        position=pos,
        scale=2.0,
        rotation=45.0,
        layer="test_layer"
    )
    assert block.name == "test_block"
    assert block.position == pos
    assert block.scale == 2.0
    assert block.rotation == 45.0
    assert block.layer == "test_layer"

def test_block_insert_config_from_dict():
    """Test BlockInsertConfig creation from dictionary."""
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

def test_block_insert_config_to_dict():
    """Test BlockInsertConfig conversion to dictionary."""
    block = BlockInsertConfig(
        name="test_block",
        position=Position(x=100.0, y=200.0),
        scale=2.0,
        rotation=45.0,
        layer="test_layer"
    )
    data = block.to_dict()
    assert data == {
        'name': 'test_block',
        'position': {'x': 100.0, 'y': 200.0},
        'scale': 2.0,
        'rotation': 45.0,
        'layer': 'test_layer'
    }

def test_block_insert_config_defaults():
    """Test BlockInsertConfig with default values."""
    data = {
        'name': 'test_block',
        'position': {'x': 100.0, 'y': 200.0}
    }
    block = BlockInsertConfig.from_dict(data)
    assert block.scale == 1.0  # Default scale
    assert block.rotation == 0.0  # Default rotation
    assert block.layer is None  # Default layer
    
    # Test to_dict with default values
    data = block.to_dict()
    assert data['scale'] == 1.0
    assert data['rotation'] == 0.0
    assert 'layer' not in data

def test_block_inserts_config_creation():
    """Test BlockInsertsConfig creation with valid data."""
    block1 = BlockInsertConfig(
        name="block1",
        position=Position(x=100.0, y=200.0)
    )
    block2 = BlockInsertConfig(
        name="block2",
        position=Position(x=300.0, y=400.0),
        scale=2.0,
        rotation=45.0,
        layer="test_layer"
    )
    blocks = BlockInsertsConfig(blocks=[block1, block2])
    assert len(blocks.blocks) == 2
    assert blocks.blocks[0] == block1
    assert blocks.blocks[1] == block2

def test_block_inserts_config_from_dict():
    """Test BlockInsertsConfig creation from dictionary."""
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
    assert blocks.blocks[0].name == 'block1'
    assert blocks.blocks[1].layer == 'test_layer'

def test_block_inserts_config_to_dict():
    """Test BlockInsertsConfig conversion to dictionary."""
    blocks = BlockInsertsConfig(blocks=[
        BlockInsertConfig(
            name="block1",
            position=Position(x=100.0, y=200.0)
        ),
        BlockInsertConfig(
            name="block2",
            position=Position(x=300.0, y=400.0),
            scale=2.0,
            rotation=45.0,
            layer="test_layer"
        )
    ])
    data = blocks.to_dict()
    assert data == {
        'blocks': [
            {
                'name': 'block1',
                'position': {'x': 100.0, 'y': 200.0},
                'scale': 1.0,
                'rotation': 0.0
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

def test_block_inserts_config_empty():
    """Test BlockInsertsConfig with empty blocks list."""
    blocks = BlockInsertsConfig(blocks=[])
    assert len(blocks.blocks) == 0
    assert blocks.to_dict() == {'blocks': []} 