#!/usr/bin/env python3
"""
DXF to Shapefile Converter
A simple command-line tool to convert DXF files to shapefiles.

Usage:
    python dxf2shp.py input.dxf [output_directory]
    python dxf2shp.py input.dxf -o output_directory
    python dxf2shp.py --project project_name

Features:
- Converts all layers from DXF to separate shapefiles
- Handles multiple geometry types (points, lines, polygons)
- Groups geometries by type within each layer
- Sets coordinate reference system (default: EPSG:25833)
"""

import sys
import os
import argparse
from pathlib import Path

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.dump_to_shape import dxf_to_shapefiles, load_project_config
    from src.utils import resolve_path, ensure_path_exists, log_info, log_error
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you're running this from the project root directory and have activated the conda environment.")
    sys.exit(1)


def create_output_dir(dxf_file, output_dir=None):
    """Create output directory based on DXF filename if not specified."""
    if output_dir:
        return Path(output_dir)

    # Create output directory next to the DXF file
    dxf_path = Path(dxf_file)
    output_path = dxf_path.parent / f"{dxf_path.stem}_shapefiles"
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert DXF files to shapefiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert DXF to shapefiles in auto-created directory
  python dxf2shp.py my_drawing.dxf

  # Convert DXF to specific output directory
  python dxf2shp.py my_drawing.dxf output_shapefiles/

  # Convert using -o flag
  python dxf2shp.py my_drawing.dxf -o /path/to/output/

  # Convert using project configuration
  python dxf2shp.py --project Bibow

  # Specify coordinate reference system
  python dxf2shp.py my_drawing.dxf -o output/ --crs EPSG:4326
"""
    )

    # Positional arguments
    parser.add_argument('dxf_file', nargs='?', help='Path to the input DXF file')
    parser.add_argument('output_dir', nargs='?', help='Output directory for shapefiles (optional)')

    # Optional arguments
    parser.add_argument('-o', '--output', dest='output_folder',
                       help='Output directory for shapefiles')
    parser.add_argument('--project', '--project-name', dest='project_name',
                       help='Name of the project in projects.yaml')
    parser.add_argument('--crs', default='EPSG:25833',
                       help='Coordinate reference system (default: EPSG:25833)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    # Coordinate correction options
    parser.add_argument('-fx', '--fix-x', type=int, metavar='N',
                       help='Remove N leading digits from X coordinates (e.g., -fx 33 removes "33" prefix)')
    parser.add_argument('-f', '--fix-coords', action='store_true',
                       help='Auto-detect and fix coordinate zone prefix issues')

    args = parser.parse_args()

    # Validate arguments
    if args.project_name:
        # Project-based conversion
        try:
            project_config = load_project_config(args.project_name)
            if not project_config:
                log_error(f"Project '{args.project_name}' not found in projects.yaml")
                return 1

            folder_prefix = project_config.get('folderPrefix', '')
            dxf_filename = resolve_path(project_config.get('dxfFilename', ''), folder_prefix)
            dump_output_dir = resolve_path(project_config.get('dxfDumpOutputDir', ''), folder_prefix)

            if not os.path.exists(dxf_filename):
                log_error(f"DXF file not found: {dxf_filename}")
                return 1

            if not ensure_path_exists(dump_output_dir):
                log_error(f"Could not create output directory: {dump_output_dir}")
                return 1

            geometry_types = project_config.get('dxfDumpGeometryTypes', None)
            if geometry_types:
                log_info(f"Converting project '{args.project_name}' (geometry types: {', '.join(geometry_types)}): {dxf_filename} -> {dump_output_dir}")
            else:
                log_info(f"Converting project '{args.project_name}': {dxf_filename} -> {dump_output_dir}")
            dxf_to_shapefiles(dxf_filename, dump_output_dir, target_crs=args.crs, geometry_types=geometry_types,
                            fix_x_digits=args.fix_x, auto_fix_coords=args.fix_coords)

        except Exception as e:
            log_error(f"Error processing project '{args.project_name}': {e}")
            return 1

    elif args.dxf_file:
        # Direct file conversion
        dxf_file = Path(args.dxf_file)

        if not dxf_file.exists():
            log_error(f"DXF file not found: {dxf_file}")
            return 1

        # Determine output directory (priority: -o flag, positional arg, auto-created)
        output_dir = args.output_folder or args.output_dir
        output_path = create_output_dir(dxf_file, output_dir)

        # Create output directory
        try:
            output_path.mkdir(parents=True, exist_ok=True)
            log_info(f"Output directory: {output_path}")
        except Exception as e:
            log_error(f"Could not create output directory {output_path}: {e}")
            return 1

        # Convert DXF to shapefiles
        try:
            log_info(f"Converting: {dxf_file} -> {output_path}")
            log_info(f"Using CRS: {args.crs}")
            if args.fix_x or args.fix_coords:
                coord_msg = f"fix X prefix: {args.fix_x}" if args.fix_x else "auto-fix coordinates"
                log_info(f"Coordinate correction: {coord_msg}")
            dxf_to_shapefiles(str(dxf_file), str(output_path), target_crs=args.crs,
                            fix_x_digits=args.fix_x, auto_fix_coords=args.fix_coords)
            log_info(f"✅ Conversion completed successfully!")
            log_info(f"📁 Shapefiles saved to: {output_path.absolute()}")

        except Exception as e:
            log_error(f"Error converting DXF file: {e}")
            if args.verbose:
                import traceback
                log_error(f"Traceback:\n{traceback.format_exc()}")
            return 1

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
