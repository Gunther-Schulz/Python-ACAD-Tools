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

def create_sample_project(project_name):
    """Creates a sample project file with basic settings."""
    # Create projects directory if it doesn't exist
    projects_dir = 'projects'
    if not os.path.exists(projects_dir):
        os.makedirs(projects_dir)
    
    # Create global settings if they don't exist
    if not os.path.exists('projects.yaml'):
        global_settings = {
            'folderPrefix': '~/Documents/Projects',
            'logFile': './log.txt',
            'styles': {
                'default': {
                    'layer': {
                        'color': 'white',
                        'lineweight': 0.25
                    }
                },
                'highlight': {
                    'layer': {
                        'color': 'red',
                        'lineweight': 0.5
                    }
                }
            }
        }
        with open('projects.yaml', 'w') as file:
            yaml.dump(global_settings, file, default_flow_style=False)
    
    project_file = os.path.join(projects_dir, f'{project_name}.yaml')
    
    sample_project = {
        'name': project_name,
        'crs': 'EPSG:25833',
        'dxfFilename': f'data/{project_name.lower()}.dxf',
        'dxfVersion': 'R2010',
        'exportFormat': 'dxf',
        'shapefileOutputDir': 'output/shapefiles',
        'dxfDumpOutputDir': 'output/dxf_dump',
        'geomLayers': [
            {
                'name': 'Buildings',
                'dxfLayer': 'BUILDINGS',
                'style': {
                    'color': 'red',
                    'lineweight': 0.35
                },
                'operations': [
                    {
                        'type': 'buffer',
                        'distance': 1.0
                    }
                ]
            }
        ]
    }
    
    with open(project_file, 'w') as file:
        yaml.dump(sample_project, file, default_flow_style=False)
    
    return project_file