"""Pytest configuration and fixtures for styling tests."""
import pytest
from pathlib import Path

# Import all fixtures from base_test_utils
from .base_test_utils import (
    style_fixtures,
    mock_dxf_drawing,
    test_geodataframe,
    mixed_geometry_gdf,
    style_assertions,
    mock_style_applicator,
    comprehensive_styles,
    color_mappings,
    mock_config_loader,
    style_applicator_service
)

# Re-export fixtures to make them available to tests
__all__ = [
    'style_fixtures',
    'mock_dxf_drawing',
    'test_geodataframe',
    'mixed_geometry_gdf',
    'style_assertions',
    'mock_style_applicator',
    'comprehensive_styles',
    'color_mappings',
    'mock_config_loader',
    'style_applicator_service'
]
