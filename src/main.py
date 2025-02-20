"""Main entry point for Python ACAD Tools."""

import sys
import os
from pathlib import Path
from src.core.utils import setup_logger
from src.core.project import Project
from src.config.config_manager import ConfigManager, ConfigError, ConfigFileNotFoundError

def get_project_dir(project_name: str) -> Path:
    """Get project directory from name."""
    # Get repository root directory
    root_dir = Path(__file__).parent.parent
    
    # Project directory is always in the projects/ subdirectory
    project_dir = root_dir / 'projects' / project_name
    
    if not project_dir.exists():
        raise ConfigError(f"Project directory does not exist: {project_dir}")
    
    return project_dir

def process_project(project_name: str) -> None:
    """Process a project by name."""
    logger = setup_logger(f"main.{project_name}")
    
    try:
        # Get project directory
        project_dir = get_project_dir(project_name)
        logger.info(f"Processing project '{project_name}' in: {project_dir}")
        
        # Initialize project (this will handle config loading and validation)
        project = Project(project_name, log_file=str(project_dir / "project.log"))
        
        # Log loaded configuration summary
        config = project.project_config
        logger.info("\nProject configuration:")
        logger.info(f"  CRS: {config.crs}")
        logger.info(f"  DXF Output: {config.dxf_filename}")
        logger.info(f"  Export Format: {config.export_format}")
        logger.info(f"  DXF Version: {config.dxf_version}")
        if config.template_dxf:
            logger.info(f"  Template: {config.template_dxf}")
        if config.shapefile_output_dir:
            logger.info(f"  Shapefile Output: {config.shapefile_output_dir}")
        
        # Log geometry layers configuration file
        geom_layers_file = project_dir / "geom_layers.yaml"
        logger.info(f"\nProcessing geometry layers from: {geom_layers_file}")
        
        # Log geometry layers summary
        layers = project.geometry_manager.get_layer_names()
        if layers:
            logger.info(f"\nFound {len(layers)} geometry layers:")
            for layer_name in layers:
                layer = project.geometry_manager.get_layer(layer_name)
                logger.info(f"\n  Layer: {layer_name}")
                
                # Log style information
                if layer.style_id:
                    logger.info(f"    Style: {layer.style_id}")
                if hasattr(layer, 'inline_style') and layer.inline_style:
                    logger.info("    Inline Style:")
                    if layer.inline_style.layer:
                        logger.info("      Layer properties:")
                        for key, value in layer.inline_style.layer.items():
                            logger.info(f"        {key}: {value}")
                    if layer.inline_style.polygon:
                        logger.info("      Polygon properties:")
                        for key, value in layer.inline_style.polygon.items():
                            logger.info(f"        {key}: {value}")
                    if layer.inline_style.text:
                        logger.info("      Text properties:")
                        for key, value in layer.inline_style.text.items():
                            logger.info(f"        {key}: {value}")
                    if layer.inline_style.hatch:
                        logger.info("      Hatch properties:")
                        for key, value in layer.inline_style.hatch.items():
                            logger.info(f"        {key}: {value}")
                elif not layer.style_id:
                    logger.info("    Style: default")  # Only show default if no style or inline style
                
                if hasattr(layer, 'shape_file') and layer.shape_file:
                    logger.info(f"    Shapefile: {layer.shape_file}")
                
                # Log operations for the layer
                if layer.operations:
                    logger.info(f"    Operations ({len(layer.operations)}):")
                    for i, op in enumerate(layer.operations, 1):
                        op_type = op.get('type', 'unknown')
                        params = op.get('parameters', {})
                        if op_type == 'buffer':
                            logger.info(f"      {i}. Buffer operation:")
                            logger.info(f"         Distance: {params.get('distance', 'not specified')}")
                            logger.info(f"         Resolution: {params.get('resolution', 16)}")
                            logger.info(f"         Cap style: {params.get('cap_style', 'round')}")
                            logger.info(f"         Join style: {params.get('join_style', 'round')}")
                        elif op_type == 'dissolve':
                            logger.info(f"      {i}. Dissolve operation:")
                            if params:
                                for param, value in params.items():
                                    logger.info(f"         {param}: {value}")
                        elif op_type == 'difference':
                            logger.info(f"      {i}. Difference operation:")
                            if 'layers' in op:
                                logger.info(f"         Layers: {op['layers']}")
                            logger.info(f"         Reverse: {op.get('reverseDifference', False)}")
                        elif op_type == 'intersection':
                            logger.info(f"      {i}. Intersection operation:")
                            if 'layers' in op:
                                logger.info(f"         Layers: {op['layers']}")
                        elif op_type == 'copy':
                            logger.info(f"      {i}. Copy operation:")
                            if 'layers' in op:
                                logger.info(f"         From layers: {op['layers']}")
                        else:
                            logger.info(f"      {i}. {op_type} operation")
                            if params:
                                for param, value in params.items():
                                    logger.info(f"         {param}: {value}")
        
        # Process the project
        logger.info("\nStarting geometry processing...")
        total_layers = len(layers)
        for layer_idx, layer_name in enumerate(layers, 1):
            layer = project.geometry_manager.get_layer(layer_name)
            logger.info(f"\nProcessing layer [{layer_idx}/{total_layers}]: {layer_name}")
            
            if hasattr(layer, 'shape_file') and layer.shape_file:
                logger.info(f"  Reading from shapefile: {layer.shape_file}")
            
            # Log operation execution
            if layer.operations:
                total_ops = len(layer.operations)
                logger.info(f"  Found {total_ops} operations to execute")
                
                # First log all operations that will be performed
                for i, op in enumerate(layer.operations, 1):
                    op_type = op.get('type', 'unknown')
                    logger.info(f"\n  Operation [{i}/{total_ops}]: {op_type}")
                    
                    # Log operation details
                    if op_type == 'buffer':
                        params = op.get('parameters', {})
                        logger.info(f"    Parameters:")
                        logger.info(f"      Distance: {params.get('distance', 'not specified')}")
                        logger.info(f"      Resolution: {params.get('resolution', 16)}")
                        logger.info(f"      Cap style: {params.get('cap_style', 'round')}")
                        logger.info(f"      Join style: {params.get('join_style', 'round')}")
                    elif op_type == 'copy':
                        if 'layers' in op:
                            logger.info(f"    Copying from layers: {op['layers']}")
                        if 'values' in op:
                            logger.info(f"    With values: {op['values']}")
                    elif op_type == 'difference':
                        if 'layers' in op:
                            logger.info(f"    Using layers: {op['layers']}")
                        logger.info(f"    Reverse difference: {op.get('reverseDifference', False)}")
                    elif op_type == 'intersection':
                        if 'layers' in op:
                            logger.info(f"    With layers: {op['layers']}")
                    elif op_type == 'dissolve':
                        params = op.get('parameters', {})
                        if params:
                            logger.info(f"    Parameters:")
                            for param, value in params.items():
                                logger.info(f"      {param}: {value}")
                    elif op_type == 'filterGeometry':
                        if 'minArea' in op:
                            logger.info(f"    Minimum area: {op['minArea']}")
                    elif op_type == 'filterByIntersection':
                        if 'layers' in op:
                            logger.info(f"    Filter using layers:")
                            for layer_info in op['layers']:
                                logger.info(f"      Layer: {layer_info.get('name')}")
                                if 'values' in layer_info:
                                    logger.info(f"      Values: {layer_info['values']}")
                
                # Now process the layer (which will execute all operations)
                logger.info("\n  Executing all operations...")
                try:
                    project.geometry_manager.process_layer(layer_name)
                    logger.info("  ✓ All operations completed successfully")
                    
                    # Log final operation results
                    if layer.geometry and layer.geometry.metadata.operations_log:
                        logger.info("  Operation results:")
                        for log_entry in layer.geometry.metadata.operations_log:
                            logger.info(f"    {log_entry}")
                except Exception as e:
                    logger.error(f"  ✗ Processing failed: {str(e)}")
                    raise
            else:
                logger.info("  No operations to perform")
            
            # Log export status
            if layer.update_dxf:
                logger.info(f"  Layer will be exported to DXF")
            
            logger.info(f"  ✓ Layer {layer_name} processed successfully")
        
        logger.info("\n✓ All geometry layers processed successfully")
        
    except ConfigFileNotFoundError as e:
        logger.error(f"Missing configuration file: {str(e)}")
        sys.exit(1)
    except ConfigError as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise  # Re-raise for debugging in development

def print_usage():
    """Print usage information."""
    print("\nPython ACAD Tools")
    print("\nUsage:")
    print("  python -m src.main <project_name>")
    print("\nAvailable projects:")
    
    # List available projects
    root_dir = Path(__file__).parent.parent
    projects_dir = root_dir / 'projects'
    if projects_dir.exists():
        for project in projects_dir.iterdir():
            if project.is_dir() and (project / 'project.yaml').exists():
                print(f"  - {project.name}")
    else:
        print("  No projects found in projects/ directory")
    
    print("\nRequired project structure:")
    print("  project_name/")
    print("  ├── project.yaml       (required: core settings)")
    print("  ├── geom_layers.yaml   (optional: geometry definitions)")
    print("  ├── styles.yaml        (optional: project styles)")
    print("  ├── viewports.yaml     (optional: viewport definitions)")
    print("  └── legends.yaml       (optional: legend definitions)")
    print("\nGlobal configuration:")
    print("  styles.yaml            (optional: in root directory)")

def main():
    """Main entry point."""
    if len(sys.argv) != 2 or sys.argv[1] in ['-h', '--help']:
        print_usage()
        sys.exit(1)
    
    process_project(sys.argv[1])

if __name__ == "__main__":
    main() 