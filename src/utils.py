import logging
import os
import sys
import pyproj
from pyproj import CRS
import traceback

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

def resolve_path(path, folder_prefix=''):
    """
    Resolves a path by expanding user directory and joining with optional folder prefix.
    
    Args:
        path (str): The path to resolve
        folder_prefix (str, optional): Prefix to prepend to the path
        
    Returns:
        str: The resolved absolute path
    """
    if not path:
        return ''
    return os.path.expanduser(os.path.join(folder_prefix, path))