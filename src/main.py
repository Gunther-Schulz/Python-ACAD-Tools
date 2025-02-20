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
        logger.info("Project configuration loaded:")
        logger.info(f"  CRS: {config.crs}")
        logger.info(f"  DXF Output: {config.dxf_filename}")
        logger.info(f"  Export Format: {config.export_format}")
        logger.info(f"  DXF Version: {config.dxf_version}")
        if config.template_dxf:
            logger.info(f"  Template: {config.template_dxf}")
        if config.shapefile_output_dir:
            logger.info(f"  Shapefile Output: {config.shapefile_output_dir}")
        
        # Log geometry layers summary
        layers = project.geometry_manager.get_layer_names()
        if layers:
            logger.info("\nGeometry layers loaded:")
            for layer_name in layers:
                layer = project.geometry_manager.get_layer(layer_name)
                logger.info(f"  Layer: {layer_name}")
                logger.info(f"    Style: {layer.style or 'default'}")
                if hasattr(layer, 'shape_file') and layer.shape_file:
                    logger.info(f"    Shapefile: {layer.shape_file}")
        
        # Log styles summary
        styles = project.config_manager.load_styles()
        if styles:
            logger.info("\nStyles loaded:")
            for style_name, style in styles.items():
                logger.info(f"  Style: {style_name}")
                if style.layer_properties.color:
                    logger.info(f"    Layer Color: {style.layer_properties.color}")
                if style.layer_properties.lineweight:
                    logger.info(f"    Line Weight: {style.layer_properties.lineweight}")
        
        # Process the project (this is where actual work would happen)
        # For now, we only have config loading implemented
        logger.info("\nProject loaded successfully. Processing not yet implemented.")
        
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