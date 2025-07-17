import argparse
import os
import ezdxf
import shapefile
from ezdxf.entities import LWPolyline, Polyline, Line, Arc, Circle, Point as DxfPoint, Hatch
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
import pyproj
import re
import yaml
import math
from src.utils import resolve_path, ensure_path_exists, log_warning, log_error, log_debug, log_info

def polygon_area(polygon):
    """Calculate the area of a polygon."""
    return Polygon(polygon).area

def get_entity_vertices(entity):
    """Safely get vertices from any polyline entity type."""
    try:
        # Try calling vertices() method first
        if hasattr(entity, 'vertices') and callable(entity.vertices):
            vertices = list(entity.vertices())
        # If vertices is a property/list, use it directly
        elif hasattr(entity, 'vertices') and not callable(entity.vertices):
            vertices = list(entity.vertices)
        else:
            return []

        # Convert vertices to consistent format (x, y) tuples
        result = []
        for v in vertices:
            if hasattr(v, 'x') and hasattr(v, 'y'):
                # Vertex object with .x and .y attributes
                result.append((float(v.x), float(v.y)))
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                # Vertex as tuple/list [x, y, ...]
                result.append((float(v[0]), float(v[1])))
            elif hasattr(v, '__iter__') and not isinstance(v, str):
                # Try to iterate and get first two values
                coords = list(v)
                if len(coords) >= 2:
                    result.append((float(coords[0]), float(coords[1])))

        return result
    except Exception as e:
        log_warning(f"Could not get vertices from entity {entity.dxftype()}: {e}")
        return []

def is_valid_coordinate(coord):
    """Check if a coordinate is valid (not NaN, not infinite)."""
    try:
        return isinstance(coord, (int, float)) and not (math.isnan(coord) or math.isinf(coord))
    except:
        return False

def validate_geometry(geom):
    """Validate that a geometry has valid coordinates."""
    try:
        if geom.geom_type == 'Point':
            return is_valid_coordinate(geom.x) and is_valid_coordinate(geom.y)
        elif geom.geom_type == 'LineString':
            coords = list(geom.coords)
            return all(is_valid_coordinate(x) and is_valid_coordinate(y) for x, y in coords)
        elif geom.geom_type == 'Polygon':
            coords = list(geom.exterior.coords)
            return all(is_valid_coordinate(x) and is_valid_coordinate(y) for x, y in coords)
        return False
    except:
        return False

def convert_entity_to_geometry(entity):
    """Convert a DXF entity to Shapely geometry."""
    try:
        entity_type = entity.dxftype()

        if entity_type in ['LWPOLYLINE', 'POLYLINE']:
            vertices = get_entity_vertices(entity)
            if len(vertices) >= 2:
                # Vertices are now already (x, y) tuples
                points = vertices
                if len(points) >= 3 and hasattr(entity, 'is_closed') and entity.is_closed:
                    # Closed polyline -> Polygon
                    geom = Polygon(points)
                else:
                    # Open polyline -> LineString
                    geom = LineString(points)

                if validate_geometry(geom):
                    return geom

        elif entity_type == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            geom = LineString([(start.x, start.y), (end.x, end.y)])
            if validate_geometry(geom):
                return geom

        elif entity_type == 'ARC':
            # Convert arc to LineString with multiple points
            center = entity.dxf.center
            radius = entity.dxf.radius
            start_angle = math.radians(entity.dxf.start_angle)
            end_angle = math.radians(entity.dxf.end_angle)

            # Handle angle wrap-around
            if end_angle <= start_angle:
                end_angle += 2 * math.pi

            # Create points along the arc
            num_points = max(8, int((end_angle - start_angle) * 180 / math.pi / 10))  # ~10 degrees per segment
            points = []
            for i in range(num_points + 1):
                angle = start_angle + (end_angle - start_angle) * i / num_points
                x = center.x + radius * math.cos(angle)
                y = center.y + radius * math.sin(angle)
                points.append((x, y))
            geom = LineString(points)
            if validate_geometry(geom):
                return geom

        elif entity_type == 'CIRCLE':
            # Convert circle to Polygon
            center = entity.dxf.center
            radius = entity.dxf.radius
            num_points = 36  # 10 degrees per segment
            points = []
            for i in range(num_points):
                angle = 2 * math.pi * i / num_points
                x = center.x + radius * math.cos(angle)
                y = center.y + radius * math.sin(angle)
                points.append((x, y))
            geom = Polygon(points)
            if validate_geometry(geom):
                return geom

        elif entity_type == 'POINT':
            location = entity.dxf.location
            geom = Point(location.x, location.y)
            if validate_geometry(geom):
                return geom

        elif entity_type == 'HATCH':
            # Try to get the boundary of the hatch
            if hasattr(entity, 'paths') and entity.paths:
                # Get the first path as the outer boundary
                path = entity.paths[0]
                if hasattr(path, 'edges') and path.edges:
                    points = []
                    for edge in path.edges:
                        if hasattr(edge, 'start'):
                            points.append((edge.start.x, edge.start.y))
                    if len(points) >= 3:
                        geom = Polygon(points)
                        if validate_geometry(geom):
                            return geom
            return None

    except Exception as e:
        log_warning(f"Could not convert entity {entity_type}: {e}")
        return None

    return None

def dxf_to_shapefiles(dxf_path, output_dir, target_crs='EPSG:25833'):
    """
    Convert all layers from a DXF file to separate shapefiles.
    Now handles LINE, ARC, CIRCLE, POINT, HATCH in addition to POLYLINE/LWPOLYLINE.
    """
    try:
        # Read the DXF file
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # Ensure output directory exists
        ensure_path_exists(output_dir)

        # Get all entities and group by layer
        layer_entities = {}
        for entity in msp:
            layer_name = entity.dxf.layer
            entity_type = entity.dxftype()

            # Only process geometric entities
            if entity_type in ['LWPOLYLINE', 'POLYLINE', 'LINE', 'ARC', 'CIRCLE', 'POINT', 'HATCH']:
                if layer_name not in layer_entities:
                    layer_entities[layer_name] = []
                layer_entities[layer_name].append(entity)

        log_info(f"Found {len(layer_entities)} layers with geometric entities")

        # Process each layer
        for layer_name, entities in layer_entities.items():
            try:
                log_info(f"Processing layer '{layer_name}' with {len(entities)} entities")

                # Convert entities to geometries
                geometries = []
                for entity in entities:
                    geom = convert_entity_to_geometry(entity)
                    if geom:
                        geometries.append(geom)

                if not geometries:
                    log_warning(f"No valid geometries found in layer '{layer_name}'")
                    continue

                # Group geometries by type for shapefile creation
                points = [g for g in geometries if g.geom_type == 'Point']
                lines = [g for g in geometries if g.geom_type == 'LineString']
                polygons = [g for g in geometries if g.geom_type == 'Polygon']

                # Create shapefiles for each geometry type present
                if points:
                    create_shapefile(points, os.path.join(output_dir, f"{layer_name}_points"), 'POINT', target_crs)
                    log_info(f"Created {layer_name}_points.shp with {len(points)} points")

                if lines:
                    create_shapefile(lines, os.path.join(output_dir, f"{layer_name}_lines"), 'POLYLINE', target_crs)
                    log_info(f"Created {layer_name}_lines.shp with {len(lines)} lines")

                if polygons:
                    create_shapefile(polygons, os.path.join(output_dir, f"{layer_name}_polygons"), 'POLYGON', target_crs)
                    log_info(f"Created {layer_name}_polygons.shp with {len(polygons)} polygons")

                # If layer has mixed types, also create a combined file with the predominant type
                if len(geometries) > 0:
                    # Use the most common geometry type for the main layer file
                    if len(polygons) >= len(lines) and len(polygons) >= len(points):
                        main_geoms = polygons
                        shape_type = 'POLYGON'
                    elif len(lines) >= len(points):
                        main_geoms = lines
                        shape_type = 'POLYLINE'
                    else:
                        main_geoms = points
                        shape_type = 'POINT'

                    if main_geoms:
                        create_shapefile(main_geoms, os.path.join(output_dir, layer_name), shape_type, target_crs)
                        log_info(f"Created {layer_name}.shp with {len(main_geoms)} {shape_type.lower()}s")

            except Exception as e:
                log_error(f"Error processing layer '{layer_name}': {e}")
                continue

    except Exception as e:
        log_error(f"Error processing DXF file: {e}")
        raise

def create_shapefile(geometries, output_path, shape_type, target_crs):
    """Create a shapefile from a list of geometries."""
    try:
        # Create the shapefile writer
        w = shapefile.Writer(output_path, shapeType=getattr(shapefile, shape_type))

        # Add fields
        w.field('ID', 'N')
        w.field('AREA', 'F', 10, 3)
        w.field('LENGTH', 'F', 10, 3)

        # Add records and shapes
        record_count = 0
        for i, geom in enumerate(geometries):
            try:
                if shape_type == 'POINT':
                    if is_valid_coordinate(geom.x) and is_valid_coordinate(geom.y):
                        w.point(float(geom.x), float(geom.y))
                        w.record(i+1, 0.0, 0.0)
                        record_count += 1

                elif shape_type == 'POLYLINE':
                    if geom.geom_type == 'LineString':
                        coords = list(geom.coords)
                        # Clean and validate coordinates
                        clean_coords = []
                        for x, y in coords:
                            if is_valid_coordinate(x) and is_valid_coordinate(y):
                                clean_coords.append([float(x), float(y)])

                        if len(clean_coords) >= 2:
                            w.line([clean_coords])
                            length = geom.length if hasattr(geom, 'length') and is_valid_coordinate(geom.length) else 0.0
                            w.record(i+1, 0.0, float(length))
                            record_count += 1

                elif shape_type == 'POLYGON':
                    if geom.geom_type == 'Polygon':
                        exterior_coords = list(geom.exterior.coords)
                        # Clean and validate coordinates
                        clean_coords = []
                        for x, y in exterior_coords:
                            if is_valid_coordinate(x) and is_valid_coordinate(y):
                                clean_coords.append([float(x), float(y)])

                        if len(clean_coords) >= 3:
                            # Ensure polygon is closed
                            if clean_coords[0] != clean_coords[-1]:
                                clean_coords.append(clean_coords[0])

                            w.poly([clean_coords])
                            area = geom.area if hasattr(geom, 'area') and is_valid_coordinate(geom.area) else 0.0
                            length = geom.length if hasattr(geom, 'length') and is_valid_coordinate(geom.length) else 0.0
                            w.record(i+1, float(area), float(length))
                            record_count += 1

            except Exception as e:
                log_warning(f"Skipping geometry {i+1} due to error: {e}")
                continue

        w.close()

        if record_count == 0:
            log_warning(f"No valid geometries written to {output_path}")
            return

        # Create .prj file with CRS information
        prj_content = get_prj_content(target_crs)
        if prj_content:
            with open(f"{output_path}.prj", 'w') as prj_file:
                prj_file.write(prj_content)

        log_info(f"Successfully created {output_path}.shp with {record_count} features")

    except Exception as e:
        log_error(f"Error creating shapefile {output_path}: {e}")
        # Try to clean up partial files
        for ext in ['.shp', '.shx', '.dbf', '.prj']:
            try:
                if os.path.exists(f"{output_path}{ext}"):
                    os.remove(f"{output_path}{ext}")
            except:
                pass
        raise

def get_prj_content(crs):
    """Get projection file content for the given CRS in ESRI WKT1 format for QGIS compatibility."""
    try:
        crs_obj = pyproj.CRS(crs)
        # Use to_wkt with ESRI format for better QGIS compatibility
        return crs_obj.to_wkt(pretty=False, version='WKT1_ESRI')
    except Exception as e:
        log_warning(f"Could not get ESRI WKT for CRS {crs}: {e}")
        # Fallback to standard WKT if ESRI format fails
        try:
            return crs_obj.to_wkt(pretty=False, version='WKT1_GDAL')
        except Exception as e2:
            log_warning(f"Could not get any WKT for CRS {crs}: {e2}")
            return None

def get_crs_from_dxf(dxf_path):
    # Read the entire DXF file as text
    with open(dxf_path, 'r', errors='ignore') as file:
        dxf_content = file.read()

    # Search for the EPSG code in the entire file content
    match = re.search(r'<Alias id="(\d+)" type="CoordinateSystem">', dxf_content)
    if match:
        epsg = int(match.group(1))
        return pyproj.CRS.from_epsg(epsg), f"EPSG:{epsg} found in DXF file"

    # If not found, return the default EPSG:25833 (ETRS89 / UTM zone 33N)
    log_info("CRS not found in DXF file. Using default EPSG:25833 (ETRS89 / UTM zone 33N).")
    return pyproj.CRS.from_epsg(25833), "Default EPSG:25833 (ETRS89 / UTM zone 33N) used"

def write_prj_file(output_path, crs):
    prj_path = output_path.replace('.shp', '.prj')

    # Use a known, valid WKT string for EPSG:25833
    wkt = 'PROJCS["ETRS89 / UTM zone 33N",GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_System_1989",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4258"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",15],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","25833"]]'

    with open(prj_path, 'w') as prj_file:
        prj_file.write(wkt)

def merge_dxf_layer_to_shapefile(dxf_path, output_folder, layer_name, entities, crs):
    points = []
    lines = []
    polygons = []

    log_info(f"Processing DXF layer to shapefile {layer_name}")

    for entity in entities:
        log_debug(f"Processing entity: {entity}")
        if isinstance(entity, (LWPolyline, Polyline)) or (hasattr(entity, 'dxf') and hasattr(entity.dxf, 'location')):
            points_list = get_entity_vertices(entity)
            log_debug(f"Entity vertices: {points_list}")
            if len(points_list) >= 2:
                # Always treat as polygon if entity has closed property set to True
                if hasattr(entity, 'closed') and entity.closed and len(points_list) >= 3:
                    try:
                        # Ensure the polygon is closed by adding first point if needed
                        if points_list[0] != points_list[-1]:
                            points_list.append(points_list[0])
                        poly = Polygon(points_list)
                        log_debug(f"Created polygon: {poly}")
                        if poly.is_valid and not poly.is_empty:
                            polygons.append(poly)
                    except Exception as e:
                        log_warning(f"Invalid polygon in layer {layer_name}: {e}")
                else:
                    try:
                        line = LineString(points_list)
                        log_debug(f"Created line: {line}")
                        if line.is_valid and not line.is_empty and line.length > 0:
                            lines.append(line)
                    except Exception as e:
                        log_warning(f"Invalid line in layer {layer_name}: {e}")
        else:
            # Handle point entities
            if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'location'):
                try:
                    point = Point(entity.dxf.location[:2])  # Take only x, y coordinates
                    if point.is_valid and not point.is_empty:
                        points.append(point)
                except Exception as e:
                    log_warning(f"Invalid point in layer {layer_name}: {e}")

    # Write points shapefile
    if points:
        valid_points = [p for p in points if p.is_valid and not p.is_empty]
        log_debug(f"Valid points: {valid_points}")
        if valid_points:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POINT) as shp:
                shp.field('Layer', 'C', 40)
                for point in valid_points:
                    shp.point(point.x, point.y)
                    shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid points found in layer {layer_name}")

    if lines:
        valid_lines = [l for l in lines if l.is_valid and not l.is_empty and l.length > 0]
        log_debug(f"Valid lines: {valid_lines}")
        if valid_lines:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYLINE) as shp:
                shp.field('Layer', 'C', 40)
                for line in valid_lines:
                    shp.line([list(line.coords)])
                    shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid lines found in layer {layer_name}")

    if polygons:
        valid_polygons = [p for p in polygons if p.is_valid and not p.is_empty and p.area > 0]
        log_debug(f"Valid polygons: {valid_polygons}")
        if valid_polygons:
            shp_path = os.path.join(output_folder, f"{layer_name}.shp")
            with shapefile.Writer(shp_path, shapeType=shapefile.POLYGON) as shp:
                shp.field('Layer', 'C', 40)
                for poly in valid_polygons:
                    if poly.is_valid and not poly.is_empty and poly.area > 0:
                        shp.poly([list(poly.exterior.coords)] + [list(interior.coords) for interior in poly.interiors])
                        shp.record(Layer=layer_name)
            write_prj_file(shp_path, crs)
        else:
            log_warning(f"No valid polygons found in layer {layer_name}")

    log_info(f"Finished processing DXF layer to shapefile {layer_name}")

def load_project_config(project_name):
    project_file = os.path.join('projects', f'{project_name}.yaml')
    if not os.path.exists(project_file):
        return None

    with open(project_file, 'r') as file:
        return yaml.safe_load(file)

def main():
    parser = argparse.ArgumentParser(description="Convert DXF layers to shapefiles with holes cut out by inner polygons")
    parser.add_argument("--dxf_file", help="Path to the input DXF file")
    parser.add_argument("--output_folder", help="Path to the output folder for shapefiles")
    parser.add_argument("--project_name", help="Name of the project in projects.yaml")
    args = parser.parse_args()

    if args.project_name:
        project_config = load_project_config(args.project_name)
        if project_config:
            folder_prefix = project_config.get('folderPrefix', '')
            dxf_filename = resolve_path(project_config.get('dxfFilename', ''), folder_prefix)
            dump_output_dir = resolve_path(project_config.get('dxfDumpOutputDir', ''), folder_prefix)

            if not os.path.exists(dxf_filename):
                log_error(f"DXF file not found: {dxf_filename}")
                return

            if not ensure_path_exists(dump_output_dir):
                log_warning(f"Dump output directory does not exist: {dump_output_dir}")
                return

            dxf_to_shapefiles(dxf_filename, dump_output_dir)
        else:
            log_info(f"Error: Project '{args.project_name}' not found in projects.yaml")
    elif args.dxf_file and args.output_folder:
        dxf_to_shapefiles(args.dxf_file, args.output_folder)
    else:
        log_info("Error: Please provide either a project name or both DXF file and output folder.")

if __name__ == "__main__":
    main()
