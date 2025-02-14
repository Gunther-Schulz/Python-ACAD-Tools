"""Base utility functions for environment setup and path handling."""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union
import pyproj
from pyproj import CRS
import traceback
import yaml
import warnings
from functools import lru_cache
from .logging import log_error, log_warning

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

class EnvironmentSetup:
    """Handles environment variable setup and configuration."""
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_conda_paths() -> Dict[str, Path]:
        """Get relevant paths from conda environment."""
        conda_prefix = os.environ.get('CONDA_PREFIX')
        if not conda_prefix:
            return {}
            
        prefix_path = Path(conda_prefix)
        return {
            'proj_lib': prefix_path / 'share' / 'proj',
            'ca_bundle': prefix_path / 'ssl' / 'cacert.pem'
        }
    
    @classmethod
    def setup_environment(cls) -> None:
        """Setup environment variables and configurations."""
        paths = cls.get_conda_paths()
        
        # Set PROJ paths and configuration
        if proj_lib := paths.get('proj_lib'):
            if proj_lib.exists():
                os.environ['PROJ_LIB'] = str(proj_lib)
                pyproj.datadir.set_data_dir(str(proj_lib))
                os.environ['PROJ_NETWORK'] = 'OFF'
        
        # Set SSL certificate paths
        if ca_bundle := paths.get('ca_bundle'):
            if ca_bundle.exists():
                os.environ['CURL_CA_BUNDLE'] = str(ca_bundle)
                os.environ['SSL_CERT_FILE'] = str(ca_bundle)
        
        # Verify PROJ setup
        try:
            CRS("EPSG:4326")
        except Exception as e:
            log_error(f"Error initializing PROJ: {str(e)}", abort=False)

class PathManager:
    """Handles path resolution and management."""
    
    _folder_prefix: Optional[str] = None
    _config_file = 'projects.yaml'
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_folder_prefix(cls) -> str:
        """Get the global folder prefix from projects.yaml."""
        if cls._folder_prefix is None:
            try:
                with open(cls._config_file, 'r') as file:
                    data = yaml.safe_load(file)
                    cls._folder_prefix = data.get('folderPrefix', '')
            except Exception as e:
                log_error(f"Error reading folder prefix from {cls._config_file}: {str(e)}", abort=False)
                cls._folder_prefix = ''
        return cls._folder_prefix
    
    @classmethod
    def resolve_path(cls, path: Union[str, Path], folder_prefix: str = '') -> str:
        """
        Resolves a path by expanding user directory and joining with optional folder prefix.
        
        Args:
            path: The path to resolve
            folder_prefix: Prefix to prepend to the path. If empty, will be read from projects.yaml
            
        Returns:
            The resolved absolute path
        """
        if not path:
            return ''
        
        # Convert to string if Path object
        path_str = str(path)
        
        # Get folder prefix if not provided
        prefix = folder_prefix or cls.get_folder_prefix()
        
        if prefix:
            # Expand and normalize folder prefix
            prefix = os.path.abspath(os.path.expanduser(prefix))
            
            # Join with path if path is relative
            if not os.path.isabs(path_str):
                return os.path.join(prefix, path_str)
        
        # Handle path without prefix
        return os.path.abspath(os.path.expanduser(path_str))
    
    @staticmethod
    def ensure_path_exists(path: Union[str, Path]) -> bool:
        """
        Check if a path exists. Returns True if the path exists, False otherwise.
        Does not create directories.
        
        Args:
            path: The path to check
            
        Returns:
            True if path exists, False otherwise
        """
        path_str = str(path)
        directory = os.path.dirname(path_str)
        if not directory:
            return True
            
        exists = os.path.exists(directory)
        if not exists:
            log_warning(f"Directory does not exist: {directory}")
        return exists

class ProjectManager:
    """Handles project creation and management."""
    
    _sample_configs = {
        'project.yaml': {
            'crs': 'EPSG:25833',
            'dxfFilename': 'output/project.dxf',
            'template': 'templates/template.dxf',
            'exportFormat': 'dxf',
            'dxfVersion': 'R2010',
            'shapefileOutputDir': 'output/shapefiles'
        },
        'geom_layers.yaml': {
            'geomLayers': [{
                'name': 'Sample Layer',
                'shapeFile': 'input/sample.shp',
                'style': 'sampleStyle',
                'updateDxf': True
            }]
        },
        'legends.yaml': {
            'legends': [{
                'name': 'Sample Legend',
                'position': {'x': 100, 'y': 100},
                'items': [{'text': 'Sample Legend Item', 'style': 'legendStyle'}]
            }]
        },
        'viewports.yaml': {
            'viewports': [{
                'name': 'MainView',
                'center': {'x': 0, 'y': 0},
                'scale': 1000,
                'rotation': 0
            }]
        },
        'block_inserts.yaml': {
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
        },
        'text_inserts.yaml': {
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
        },
        'path_arrays.yaml': {
            'pathArrays': [{
                'name': 'Sample Array',
                'blockName': 'ArrayBlock',
                'spacing': 10,
                'path': 'Sample Path Layer'
            }]
        },
        'web_services.yaml': {
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
    }
    
    @classmethod
    def create_sample_project(cls, project_name: str) -> str:
        """Create a new project with the modular directory structure and sample files."""
        project_dir = os.path.join('projects', project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # Create sample configuration files
        for filename, content in cls._sample_configs.items():
            file_path = os.path.join(project_dir, filename)
            with open(file_path, 'w') as f:
                yaml.dump(content, f, default_flow_style=False, sort_keys=False)
        
        return project_dir

# Initialize environment on module import
EnvironmentSetup.setup_environment()

def warning_to_logger(message, category, filename, lineno, file=None, line=None):
    """Convert warnings to log messages with operation context"""
    import traceback
    import inspect
    # from src.operations.common_operations import format_operation_warning
    
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
    
    # # Format the message
    # if layer_name:
    #     formatted_message = format_operation_warning(layer_name, op_type or 'unknown', str(message))
    # else:
    #     formatted_message = str(message)
    
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