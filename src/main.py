#!/usr/bin/env python3

import sys
import argparse
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .core.pipeline import Pipeline
from .utils.logging import (
    log_info, log_error,
    LoggerSetup, set_log_level
)
from .utils.base import ProjectManager
from .utils.operations import print_layer_operations, print_layer_settings

@dataclass
class CommandLineArgs:
    """Data class to hold command line arguments."""
    project_name: Optional[str]
    plot_ops: bool
    cleanup: bool
    list_operations: bool
    list_settings: bool
    list_projects: bool
    create_project: bool
    log_level: str

class CommandLineInterface:
    """Handles command line interface setup and execution."""
    
    @staticmethod
    def setup_parser() -> argparse.ArgumentParser:
        """Setup and return the argument parser."""
        parser = argparse.ArgumentParser(description="Process and export project data to DXF.")
        parser.add_argument("project_name", nargs="?", help="Name of the project to process")
        parser.add_argument('--plot-ops', action='store_true', help="Plot the result of each operation")
        parser.add_argument('--cleanup', action='store_true', help="Perform thorough document cleanup after processing")
        parser.add_argument('-l', '--list-operations', action='store_true', help="List all possible layer operations and their options")
        parser.add_argument('-s', '--list-settings', action='store_true', help="List all possible layer settings and their options")
        parser.add_argument('--list-projects', action='store_true', help="List all available projects")
        parser.add_argument('--create-project', action='store_true', help="Create a new project with basic settings")
        parser.add_argument('--log-level', 
                          choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                          default='INFO',
                          help='Set the logging level')
        return parser
    
    @staticmethod
    def parse_args() -> CommandLineArgs:
        """Parse command line arguments into a data class."""
        parser = CommandLineInterface.setup_parser()
        args = parser.parse_args()
        
        # Validate arguments
        if not args.project_name and not (args.list_operations or args.list_settings or args.list_projects):
            parser.error("project_name is required unless --list-operations, --list-settings, or --list-projects is specified")
        
        return CommandLineArgs(
            project_name=args.project_name,
            plot_ops=args.plot_ops,
            cleanup=args.cleanup,
            list_operations=args.list_operations,
            list_settings=args.list_settings,
            list_projects=args.list_projects,
            create_project=args.create_project,
            log_level=args.log_level
        )
    
    @staticmethod
    def list_available_projects() -> List[str]:
        """List all available projects in the projects directory."""
        projects_dir = 'projects'
        if not os.path.exists(projects_dir):
            return []
        
        return [
            name for name in os.listdir(projects_dir)
            if os.path.isdir(os.path.join(projects_dir, name))
            and not name.startswith('.')
            and not name.startswith('__')
        ]
    
    @staticmethod
    def handle_project_creation(project_name: str) -> None:
        """Handle project creation command."""
        # Check if project already exists
        project_dir = os.path.join('projects', project_name)
        if os.path.exists(project_dir):
            log_error(
                f"Project '{project_name}' already exists at: {project_dir}\n"
                "Please choose a different project name or remove the existing project directory."
            )
        
        project_dir = ProjectManager.create_sample_project(project_name)
        log_info(f"\nCreated new project directory: {project_dir}")
        log_info("\nThe following files were created with sample configurations:")
        for config_file in [
            "project.yaml         (required core settings)",
            "geom_layers.yaml     (geometry layer definitions)",
            "legends.yaml         (legend configurations)",
            "viewports.yaml       (viewport settings)",
            "block_inserts.yaml   (block insertion definitions)",
            "text_inserts.yaml    (text insertion definitions)",
            "path_arrays.yaml     (path array definitions)",
            "web_services.yaml    (WMS/WMTS service configurations)"
        ]:
            log_info(f"  - {config_file}")
        log_info("\nPlease edit these files with your project-specific settings.")
    
    @staticmethod
    def handle_project_processing(project_name: str, plot_ops: bool, cleanup: bool) -> None:
        """Handle project processing command."""
        log_info(f"Processing project: {project_name}")
        
        try:
            # Initialize and run the pipeline
            pipeline = Pipeline(project_name, plot_ops)
            pipeline.process()
            
            # Add cleanup step if requested
            if cleanup:
                pipeline.cleanup()
                
        except Exception as e:
            # Log the error with full details
            log_error(
                f"Error processing project: {str(e)}",
                exc_info=e,
                abort=True
            )

def main() -> None:
    """Main entry point for the application."""
    args = CommandLineInterface.parse_args()

    # Initialize logging with the specified level
    LoggerSetup.setup(args.log_level)
    set_log_level(args.log_level)

    # Handle list commands
    if args.list_projects:
        projects = CommandLineInterface.list_available_projects()
        if projects:
            log_info("Available projects:")
            for project in projects:
                log_info(f"  - {project}")
        else:
            log_info("No projects found.")
        return

    if args.list_operations:
        print_layer_operations()
        return

    if args.list_settings:
        print_layer_settings()
        return

    # Handle project creation or processing
    if args.create_project:
        CommandLineInterface.handle_project_creation(args.project_name)
    else:
        CommandLineInterface.handle_project_processing(args.project_name, args.plot_ops, args.cleanup)

if __name__ == "__main__":
    main()