"""Pytest configuration and shared fixtures."""

import os
import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname

@pytest.fixture
def test_project_dir(temp_dir):
    """Create a test project directory structure."""
    project_dir = Path(temp_dir) / "test_project"
    project_dir.mkdir()
    
    # Create necessary subdirectories
    (project_dir / "output").mkdir()
    
    yield project_dir
    
    # Cleanup
    if project_dir.exists():
        shutil.rmtree(project_dir)

@pytest.fixture
def sample_project_files(test_project_dir):
    """Create sample project configuration files."""
    # Create project.yaml
    with open(test_project_dir / "project.yaml", "w") as f:
        f.write("""
crs: EPSG:25833
dxfFilename: output/test.dxf
template: templates/base.dxf
exportFormat: dxf
dxfVersion: R2010
        """.strip())
    
    # Create geom_layers.yaml
    with open(test_project_dir / "geom_layers.yaml", "w") as f:
        f.write("""
geomLayers:
  - name: test_layer
    updateDxf: true
    shapeFile: input/test.shp
    style: default
        """.strip())
    
    yield test_project_dir 