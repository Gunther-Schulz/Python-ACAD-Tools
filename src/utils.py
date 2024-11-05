import logging
import os
import sys
import pyproj
from pyproj import CRS
import traceback
import yaml

# Setup logging
def setup_logging():
    logging.basicConfig(filename='convert.log', filemode='w', level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def log_info(*messages):
    logging.info(' '.join(str(msg) for msg in messages))

def log_warning(message):
    logging.warning(f"\033[93mWarning: {message}\033[0m")

def log_error(message):
    error_traceback = traceback.format_exc()
    logging.error(f"\033[91mError: {message}\033[0m")
    if error_traceback != "NoneType: None\n":
        logging.error(f"Traceback:\n{error_traceback}")

# PROJ setup
def setup_proj():
    if 'PROJ_DATA' in os.environ:
        log_info(f"Unsetting PROJ_DATA (was set to: {os.environ['PROJ_DATA']})")
        del os.environ['PROJ_DATA']

    proj_data_dirs = [
        '/usr/share/proj',
        '/usr/local/share/proj',
        '/opt/homebrew/share/proj',
        'C:\\Program Files\\PROJ\\share',
        '/home/g/.conda/envs/qgis/share/proj',
        os.path.join(sys.prefix, 'share', 'proj'),
    ]

    for directory in proj_data_dirs:
        if os.path.exists(os.path.join(directory, 'proj.db')):
            os.environ['PROJ_LIB'] = directory
            log_info(f"Set PROJ_LIB to: {directory}")
            break
    else:
        log_warning("Could not find proj.db in any of the standard locations.")

    os.environ['PROJ_NETWORK'] = 'OFF'
    log_info("Set PROJ_NETWORK to OFF")

    pyproj.datadir.set_data_dir(os.environ['PROJ_LIB'])
    log_info(f"PyProj data directory: {pyproj.datadir.get_data_dir()}")
    log_info(f"PyProj version: {pyproj.__version__}")

    try:
        crs = CRS("EPSG:4326")
        log_info(f"Successfully created CRS object: {crs}")
    except Exception as e:
        log_error(f"Error creating CRS object: {str(e)}")

    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        result = transformer.transform(0, 0)
        log_info(f"Successfully performed transformation: {result}")
    except Exception as e:
        log_error(f"Error performing transformation: {str(e)}")

    try:
        proj_version = pyproj.__proj_version__
        log_info(f"PROJ version (from pyproj): {proj_version}")
    except Exception as e:
        log_error(f"Error getting PROJ version: {str(e)}")

def get_folder_prefix():
    """Get the global folder prefix from projects.yaml"""
    try:
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            return data.get('folderPrefix', '')
    except Exception as e:
        log_error(f"Error reading folder prefix from projects.yaml: {str(e)}")
        return ''

def resolve_path(path, folder_prefix=''):
    """
    Resolves a path by expanding user directory and joining with optional folder prefix.
    
    Args:
        path (str): The path to resolve
        folder_prefix (str, optional): Prefix to prepend to the path. If empty, will be read from projects.yaml
        
    Returns:
        str: The resolved absolute path
    """
    if not path:
        return ''
    
    # Get folder prefix from projects.yaml if not provided
    if not folder_prefix:
        folder_prefix = get_folder_prefix()
    
    # First expand user directory in folder_prefix (if it exists)
    if folder_prefix:
        folder_prefix = os.path.expanduser(folder_prefix)
        folder_prefix = os.path.abspath(folder_prefix)
        
        # If path is relative, join it with folder_prefix
        if not os.path.isabs(path):
            return os.path.join(folder_prefix, path)
    
    # If we get here, either there's no folder_prefix or path is absolute
    expanded_path = os.path.expanduser(path)
    return os.path.abspath(expanded_path)

def ensure_path_exists(path):
    """
    Check if a path exists. Returns True if the path exists, False otherwise.
    Does not create directories.
    
    Args:
        path (str): The path to check
        
    Returns:
        bool: True if path exists, False otherwise
    """
    directory = os.path.dirname(path)
    if not directory:
        return True
        
    exists = os.path.exists(directory)
    if not exists:
        log_warning(f"Directory does not exist: {directory}")
    return exists

def create_sample_project(project_name: str) -> str:
    """Create a new project with the modular directory structure and sample files"""
    project_dir = os.path.join('projects', project_name)
    os.makedirs(project_dir, exist_ok=True)

    # Sample configurations for each module
    project_yaml = {
        'crs': 'EPSG:25833',
        'dxfFilename': 'output/project.dxf',
        'template': 'templates/template.dxf',
        'exportFormat': 'dxf',
        'dxfVersion': 'R2010',
        'shapefileOutputDir': 'output/shapefiles'
    }

    geom_layers_yaml = {
        'geomLayers': [{
            'name': 'Sample Layer',
            'shapeFile': 'input/sample.shp',
            'style': 'sampleStyle',
            'updateDxf': True
        }]
    }

    legends_yaml = {
        'legends': [{
            'name': 'Sample Legend',
            'position': {'x': 100, 'y': 100},
            'items': [{'text': 'Sample Legend Item', 'style': 'legendStyle'}]
        }]
    }

    viewports_yaml = {
        'viewports': [{
            'name': 'MainView',
            'center': {'x': 0, 'y': 0},
            'scale': 1000,
            'rotation': 0
        }]
    }

    block_inserts_yaml = {
        'blockInserts': [{
            'name': 'Sample Block',
            'blockName': 'SampleBlock',
            'updateDxf': True,
            'position': {
                'type': 'absolute',
                'x': 0,
                'y': 0
            }
        }]
    }

    text_inserts_yaml = {
        'textInserts': [{
            'name': 'Sample Text',
            'targetLayer': 'Text',
            'updateDxf': True,
            'text': 'Sample Text',
            'position': {
                'type': 'absolute',
                'x': 0,
                'y': 0
            }
        }]
    }

    path_arrays_yaml = {
        'pathArrays': [{
            'name': 'Sample Array',
            'blockName': 'ArrayBlock',
            'spacing': 10,
            'path': 'Sample Path Layer'
        }]
    }

    # Write all configuration files
    files_to_create = {
        'project.yaml': project_yaml,
        'geom_layers.yaml': geom_layers_yaml,
        'legends.yaml': legends_yaml,
        'viewports.yaml': viewports_yaml,
        'block_inserts.yaml': block_inserts_yaml,
        'text_inserts.yaml': text_inserts_yaml,
        'path_arrays.yaml': path_arrays_yaml
    }

    for filename, content in files_to_create.items():
        filepath = os.path.join(project_dir, filename)
        with open(filepath, 'w') as f:
            yaml.dump(content, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    log_info(f"Created new project directory structure at: {project_dir}")
    return project_dir