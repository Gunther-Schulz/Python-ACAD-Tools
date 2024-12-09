import logging
import os
import sys
import pyproj
from pyproj import CRS
import traceback
import yaml

# Add this near the top of the file, after the imports
def set_log_level(level):
    """Set the logging level for console handler only"""
    log_level = level.upper()
    root_logger = logging.getLogger('')
    
    # Only modify console handler level
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(getattr(logging, log_level))
            break

# Setup logging
def setup_logging(console_level='INFO'):
    # Set logging levels for external libraries
    logging.getLogger('fiona').setLevel(logging.WARNING)
    logging.getLogger('osgeo').setLevel(logging.WARNING)
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    
    # Setup root logger to capture everything
    root_logger = logging.getLogger('')
    root_logger.setLevel(logging.DEBUG)  # Always capture all levels
    
    # Create and configure handlers
    handlers = {
        'debug': logging.FileHandler('logs/debug.log', mode='w'),
        'info': logging.FileHandler('logs/info.log', mode='w'),
        'warning': logging.FileHandler('logs/warning.log', mode='w'),
        'error': logging.FileHandler('logs/error.log', mode='w'),
        'console': logging.StreamHandler()
    }
    
    # Set levels for file handlers (these won't change based on console_level)
    handlers['debug'].setLevel(logging.DEBUG)
    handlers['info'].setLevel(logging.INFO)
    handlers['warning'].setLevel(logging.WARNING)
    handlers['error'].setLevel(logging.ERROR)
    
    # Set console level based on parameter
    handlers['console'].setLevel(getattr(logging, console_level.upper()))
    
    # Add formatters to handlers
    for handler in handlers.values():
        if isinstance(handler, logging.FileHandler):
            handler.setFormatter(file_formatter)
        else:
            handler.setFormatter(console_formatter)
        root_logger.addHandler(handler)

def log_info(*messages):
    logging.info(' '.join(str(msg) for msg in messages))

def log_warning(message):
    logging.warning(f"\033[93m{message}\033[0m")

def log_error(message, abort=True):
    """
    Log an error message and optionally abort execution.
    
    Args:
        message (str): The error message to log
        abort (bool, optional): Whether to abort execution. Defaults to True.
    """
    import traceback
    stack = traceback.extract_stack()
    caller = stack[-2]  # Get caller's info
    error_traceback = traceback.format_exc()
    logging.error(f"\033[91mError: {message} (from {caller.filename}:{caller.lineno})\033[0m")
    if error_traceback != "NoneType: None\n":
        logging.error(f"Traceback:\n{error_traceback}")
    
    if abort:
        sys.exit(1)

def log_debug(message):
    import traceback
    stack = traceback.extract_stack()
    caller = stack[-2]  # Get caller's info
    logging.debug(f"{message} (from {caller.filename}:{caller.lineno})")

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
            log_debug(f"Set PROJ_LIB to: {directory}")
            break
    else:
        log_warning("Could not find proj.db in any of the standard locations.")

    os.environ['PROJ_NETWORK'] = 'OFF'
    log_debug("Set PROJ_NETWORK to OFF")

    pyproj.datadir.set_data_dir(os.environ['PROJ_LIB'])
    log_debug(f"PyProj data directory: {pyproj.datadir.get_data_dir()}")
    log_debug(f"PyProj version: {pyproj.__version__}")

    try:
        crs = CRS("EPSG:4326")
        log_debug(f"Successfully created CRS object: {crs}")
    except Exception as e:
        log_error(f"Error creating CRS object: {str(e)}")

    try:
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        result = transformer.transform(0, 0)
        log_debug(f"Successfully performed transformation: {result}")
    except Exception as e:
        log_error(f"Error performing transformation: {str(e)}")

    try:
        proj_version = pyproj.__proj_version__
        log_debug(f"PROJ version (from pyproj): {proj_version}")
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

    # Create web_services.yaml with sample configuration
    web_services_yaml = {
        'wmsServices': {
            'sample_wms': {
                'url': 'https://example.com/wms',
                'layer': 'sample_layer',
                'srs': 'EPSG:3857',
                'format': 'image/png',
                'targetFolder': 'wms_cache',
                'buffer': 100,
                'zoom': 15,
                'overwrite': False,
                'postProcess': {
                    'colorMap': {'255,255,255': '0,0,0'},
                    'alphaColor': '255,255,255',
                    'grayscale': False,
                    'removeText': False
                }
            }
        },
        'wmtsServices': {
            'sample_wmts': {
                'url': 'https://example.com/wmts',
                'layer': 'sample_layer',
                'srs': 'EPSG:3857',
                'format': 'image/png',
                'targetFolder': 'wmts_cache',
                'buffer': 100,
                'zoom': 15,
                'overwrite': False,
                'postProcess': {
                    'colorMap': {'255,255,255': '0,0,0'},
                    'alphaColor': '255,255,255',
                    'grayscale': False,
                    'removeText': False
                }
            }
        }
    }

    with open(os.path.join(project_dir, 'web_services.yaml'), 'w') as f:
        yaml.dump(web_services_yaml, f, default_flow_style=False, sort_keys=False)

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