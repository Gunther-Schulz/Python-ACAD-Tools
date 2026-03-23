"""Sample project creation for --create-project CLI command."""
import os
import yaml
from src.utils import log_info


def create_sample_project(project_name: str) -> str:
    """Create a new project with geom_layers at root, generated/ and interactive/ folders"""
    project_dir = os.path.join('projects', project_name)
    os.makedirs(project_dir, exist_ok=True)

    generated_dir = os.path.join(project_dir, 'generated')
    interactive_dir = os.path.join(project_dir, 'interactive')
    layers_dir = os.path.join(project_dir, 'layers')
    os.makedirs(generated_dir, exist_ok=True)
    os.makedirs(interactive_dir, exist_ok=True)
    os.makedirs(layers_dir, exist_ok=True)

    configs = {
        'project.yaml': {
            'crs': 'EPSG:25833',
            'dxfFilename': 'output/project.dxf',
            'templateDxfFilename': 'templates/template.dxf',
            'exportFormat': 'dxf',
            'dxfVersion': 'R2018',
            'shapefileOutputDir': 'output/shapefiles',
        },
        'geom_layers.yaml': {
            'geomLayers': [{
                'name': 'Sample Layer',
                'shapeFile': 'input/sample.shp',
                'style': 'sampleStyle',
                'sync': 'push',
            }],
        },
        'generated/legends.yaml': {
            'legends': [{
                'name': 'Sample Legend',
                'position': {'x': 100, 'y': 100},
                'groups': [],
            }],
        },
        'generated/path_arrays.yaml': {
            'pathArrays': [],
        },
        'generated/wmts_wms_layers.yaml': {
            'wmtsLayers': [],
            'wmsLayers': [],
        },
        'interactive/viewports.yaml': {
            'viewports': [{
                'name': 'MainView',
                'center': {'x': 0, 'y': 0},
                'scale': 1000,
            }],
        },
        'interactive/block_inserts.yaml': {
            'blocks': [],
        },
        'interactive/text_inserts.yaml': {
            'texts': [],
        },
    }

    for filename, content in configs.items():
        filepath = os.path.join(project_dir, filename)
        with open(filepath, 'w') as f:
            yaml.dump(content, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    log_info(f"Created new project at: {project_dir}")
    return project_dir
