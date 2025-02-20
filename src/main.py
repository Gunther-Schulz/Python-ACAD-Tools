"""Main entry point for Python ACAD Tools."""

import sys
import os
import logging
import yaml
from pathlib import Path
from src.config.config_manager import ConfigManager, ConfigError

def setup_logging():
    """Set up basic logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

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
    logger = setup_logging()
    
    try:
        # Get project directory
        project_dir = get_project_dir(project_name)
        logger.info(f"Processing project '{project_name}' in: {project_dir}")
        
        # Initialize configuration manager
        config_manager = ConfigManager(str(project_dir))
        
        # Load and display project configuration
        project_config = config_manager.load_project_config()
        logger.info("Project configuration loaded:")
        logger.info(f"  CRS: {project_config.crs}")
        logger.info(f"  DXF Output: {project_config.dxf_filename}")
        logger.info(f"  Export Format: {project_config.export_format}")
        logger.info(f"  DXF Version: {project_config.dxf_version}")
        if project_config.template_dxf:
            logger.info(f"  Template: {project_config.template_dxf}")
        if project_config.shapefile_output_dir:
            logger.info(f"  Shapefile Output: {project_config.shapefile_output_dir}")
        
        # Load and display geometry layers
        geom_layers = config_manager.load_geometry_layers()
        if geom_layers:
            logger.info("\nGeometry layers loaded:")
            for layer in geom_layers:
                logger.info(f"  Layer: {layer.name}")
                logger.info(f"    Update DXF: {layer.update_dxf}")
                logger.info(f"    Style: {layer.style or 'default'}")
                if layer.shape_file:
                    logger.info(f"    Shapefile: {layer.shape_file}")
                if layer.simple_label_column:
                    logger.info(f"    Simple Label Column: {layer.simple_label_column}")
                if layer.operations:
                    logger.info(f"    Operations: {len(layer.operations)}")
                    for op in layer.operations:
                        logger.info(f"      - {op.type}")
                        if op.distance:
                            logger.info(f"        Distance: {op.distance}")
                        if op.layers:
                            logger.info(f"        Layers: {op.layers}")
        
        # Load and display styles (merging global and project styles)
        # First try to load global styles
        root_styles_path = Path(__file__).parent.parent / 'styles.yaml'
        if root_styles_path.exists():
            logger.info("\nGlobal styles found")
        
        # Then load project-specific styles
        styles = config_manager.load_styles()
        if styles:
            logger.info("\nStyles loaded:")
            for style_name, style in styles.items():
                logger.info(f"  Style: {style_name}")
                if style.layer_properties.color:
                    logger.info(f"    Layer Color: {style.layer_properties.color}")
                if style.layer_properties.lineweight:
                    logger.info(f"    Line Weight: {style.layer_properties.lineweight}")
                if style.text_properties:
                    logger.info(f"    Text Height: {style.text_properties.height}")
                    if style.text_properties.color:
                        logger.info(f"    Text Color: {style.text_properties.color}")
        
    except ConfigError as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)

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
            if project.is_dir():
                print(f"  - {project.name}")
    else:
        print("  No projects found in projects/ directory")
    
    print("\nRequired configuration files in project directory:")
    print("  - project.yaml         (required core settings)")
    print("  - geom_layers.yaml     (geometry layer definitions)")
    print("  - styles.yaml          (style definitions)")
    print("\nOptional global configuration:")
    print("  - styles.yaml          (in root directory)")

def main():
    """Main entry point."""
    if len(sys.argv) != 2 or sys.argv[1] in ['-h', '--help']:
        print_usage()
        sys.exit(1)
    
    process_project(sys.argv[1])

if __name__ == "__main__":
    main() 