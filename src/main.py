#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

from pycad.core.application import Application
from pycad.utils.logging import log_error

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Python CAD/GIS Tools'
    )
    
    parser.add_argument(
        'project_dir',
        help='Project directory'
    )
    
    parser.add_argument(
        '--log-level',
        default='INFO',
        help='Set the logging level'
    )
    
    return parser.parse_args()

def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Create and run application
        app = Application(args.project_dir)
        app.run()
        
        return 0
        
    except KeyboardInterrupt:
        log_error("Processing interrupted by user")
        return 130
    except Exception as e:
        log_error(f"Processing failed: {str(e)}")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 