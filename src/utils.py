import logging
import os
import sys
from pathlib import Path
import pyproj
from pyproj import CRS
import traceback
import yaml
import warnings
from contextlib import contextmanager
from functools import wraps

# Global profiling control
_PROFILING_ENABLED = False

# Set environment variables before any other imports
conda_prefix = os.environ.get('CONDA_PREFIX')
if conda_prefix:
    # Set PROJ_LIB
    proj_lib = Path(conda_prefix) / 'share' / 'proj'
    if proj_lib.exists():
        os.environ['PROJ_LIB'] = str(proj_lib)

    # Set SSL certificate path
    ca_bundle = Path(conda_prefix) / 'ssl' / 'cacert.pem'
    if ca_bundle.exists():
        os.environ['CURL_CA_BUNDLE'] = str(ca_bundle)
        os.environ['SSL_CERT_FILE'] = str(ca_bundle)

# Now import required packages
try:
    from pyproj import CRS
except ImportError as e:
    print(f"Error importing pyproj: {e}")

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
    logging.getLogger('pyogrio._io').setLevel(logging.WARNING)

    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')  # This format shows logger name

    # Setup root logger to capture everything
    root_logger = logging.getLogger('')
    root_logger.setLevel(logging.DEBUG)  # Always capture all levels

    # Clear existing handlers
    root_logger.handlers.clear()

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

    # Route warnings through our logging system
    warnings.showwarning = warning_to_logger

    # Specifically for unary_union warnings
    warnings.filterwarnings('always', message='.*overflow encountered in unary_union.*')

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
    if os.getenv('DEBUG') == '1':
        caller = traceback.extract_stack()[-2]
        logging.debug(f"{message} (from {caller.filename}:{caller.lineno})")

def set_profiling_enabled(enabled: bool):
    """Enable or disable performance profiling globally"""
    global _PROFILING_ENABLED
    _PROFILING_ENABLED = enabled
    if enabled:
        log_info("Performance profiling enabled - logs will be written to logs/performance.log")
    else:
        log_debug("Performance profiling disabled")

def is_profiling_enabled() -> bool:
    """Check if profiling is currently enabled"""
    global _PROFILING_ENABLED
    return _PROFILING_ENABLED

# Performance Profiling System
import time

# Create performance logger
def setup_performance_logger():
    """Set up a separate logger for performance profiling."""
    perf_logger = logging.getLogger('performance')
    perf_logger.setLevel(logging.INFO)

    # Only add handler if not already present
    if not perf_logger.handlers:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)

        # Create performance log file handler
        perf_handler = logging.FileHandler('logs/performance.log', mode='w')
        perf_formatter = logging.Formatter('%(asctime)s - %(message)s')
        perf_handler.setFormatter(perf_formatter)
        perf_logger.addHandler(perf_handler)

        # Prevent propagation to root logger (keeps it out of console)
        perf_logger.propagate = False

    return perf_logger

# Initialize performance logger
perf_logger = setup_performance_logger()

@contextmanager
def profile_operation(operation_name, details=None):
    """Context manager for profiling operations."""
    if not is_profiling_enabled():
        # If profiling is disabled, just yield without doing anything
        yield
        return

    start_time = time.time()
    perf_logger.info(f"START: {operation_name}" + (f" - {details}" if details else ""))

    try:
        yield
    finally:
        end_time = time.time()
        duration = end_time - start_time
        perf_logger.info(f"END: {operation_name} - Duration: {duration:.3f}s" + (f" - {details}" if details else ""))

def profile_function(operation_name=None):
    """Decorator for profiling functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_profiling_enabled():
                # If profiling is disabled, just call the function directly
                return func(*args, **kwargs)

            name = operation_name or f"{func.__module__}.{func.__name__}"
            with profile_operation(name):
                return func(*args, **kwargs)
        return wrapper
    return decorator

def log_performance(message):
    """Log a performance-related message."""
    if not is_profiling_enabled():
        return
    perf_logger.info(message)

def log_memory_usage(operation_name):
    """Log current memory usage (if psutil is available)."""
    if not is_profiling_enabled():
        return
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        perf_logger.info(f"MEMORY: {operation_name} - {memory_mb:.1f} MB")
    except ImportError:
        pass  # psutil not available

# PROJ setup
def setup_proj():
    """Setup PROJ environment and configuration"""
    conda_prefix = os.environ.get('CONDA_PREFIX')
    if conda_prefix:
        # Set PROJ paths
        proj_lib = Path(conda_prefix) / 'share' / 'proj'
        if proj_lib.exists():
            os.environ['PROJ_LIB'] = str(proj_lib)
            pyproj.datadir.set_data_dir(str(proj_lib))

        # Set network settings
        os.environ['PROJ_NETWORK'] = 'OFF'

        # Set SSL certificates
        ca_bundle = Path(conda_prefix) / 'ssl' / 'cacert.pem'
        if ca_bundle.exists():
            os.environ['CURL_CA_BUNDLE'] = str(ca_bundle)
            os.environ['SSL_CERT_FILE'] = str(ca_bundle)

    # Verify PROJ setup
    try:
        crs = CRS("EPSG:4326")
    except Exception as e:
        print(f"Error creating CRS object: {str(e)}")

# Call setup_proj() before any other imports
setup_proj()

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
        'blocks': [{
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
        'texts': [{
            'name': 'Sample Text',
            'layer': 'Text',
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

def warning_to_logger(message, category, filename, lineno, file=None, line=None):
    """Convert warnings to log messages with operation context"""
    import traceback
    import inspect
    from src.operations.common_operations import format_operation_warning

    # Get the current call stack
    current_stack = inspect.stack()

    # Find the operation context
    layer_name = None
    op_type = None

    # Look through the stack for operation context
    for frame_info in current_stack:
        frame = frame_info.frame
        code = frame_info.code_context[0] if frame_info.code_context else ''

        # Check if we're in an operation
        if '/operations/' in frame_info.filename:
            # Try to get layer_name from locals
            if 'layer_name' in frame.f_locals:
                layer_name = frame.f_locals['layer_name']
            elif 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'layer_name'):
                layer_name = frame.f_locals['self'].layer_name

            # Try to get operation type
            if 'operation' in frame.f_locals:
                op_type = frame.f_locals['operation'].get('type')
            else:
                # Try to get from filename
                op_name = frame_info.filename.split('/')[-1]
                if op_name.endswith('_operation.py'):
                    op_type = op_name[:-12]

            if layer_name:
                break

    # Format the message
    if layer_name:
        formatted_message = format_operation_warning(layer_name, op_type or 'unknown', str(message))
    else:
        formatted_message = str(message)

    log_message = f"""\033[38;5;166mWarning:
    [Layer: {layer_name}] [{op_type or 'unknown'}]
    {str(message)}
    File: {filename}
    Line: {lineno}
    \033[0m"""

    logging.warning(log_message)

# Set up the warning capture at module import
import warnings
warnings.showwarning = warning_to_logger
