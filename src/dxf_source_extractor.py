import ezdxf
import geopandas as gpd
from pathlib import Path

from shapely import MultiPolygon
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug
from src.shapefile_utils import write_shapefile
from src.preprocessors.block_exploder import explode_blocks
from src.preprocessors.circle_extractor import extract_circle_centers
from src.layer_processor import LayerProcessor
from shapely.geometry import LineString, Point, Polygon
import math
import numpy as np

class DXFSourceExtractor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.dxf_extracts = project_loader.project_settings.get('updateFromSource', [])
        self.crs = project_loader.crs
        self.preprocessors = {
            'block_exploder': explode_blocks,
            'circle_extractor': extract_circle_centers
        }

    def process_extracts(self, default_doc):
        """Process all DXF extracts defined in updateFromSource configuration"""
        if not self.dxf_extracts:
            log_debug("No DXF extracts configured in updateFromSource")
            return
        
        for extract in self.dxf_extracts:
            source_layer = extract.get('sourceLayer')
            output_file = extract.get('outputShapeFile')
            source_dxf = extract.get('sourceDxf')
            preprocessors = extract.get('preprocessors', [])
            
            if not source_layer or not output_file:
                log_warning(f"Skipping invalid DXF extract configuration: {extract}")
                continue
            
            # Load alternative DXF if specified
            doc = default_doc
            if source_dxf:
                try:
                    full_source_path = resolve_path(source_dxf, self.project_loader.folder_prefix)
                    doc = ezdxf.readfile(full_source_path)
                except Exception as e:
                    log_error(f"Failed to load alternative DXF {source_dxf}: {str(e)}")
                    continue
            
            if source_layer not in doc.layers:
                log_warning(f"Source layer '{source_layer}' not found in DXF document")
                continue
                
            self._process_single_extract(doc, source_layer, output_file, preprocessors)

    def _process_single_extract(self, doc, source_layer, output_file, preprocessors=None):
        """Extract geometries from a single DXF layer and save to shapefile"""
        log_debug(f"Extracting geometries from DXF layer: {source_layer}")
        
        try:
            full_output_path = resolve_path(output_file, self.project_loader.folder_prefix)
            output_dir = str(Path(full_output_path).parent)
            log_debug(f"Output directory: {output_dir}")
            if not ensure_path_exists(output_dir):
                log_error(f"Could not create output directory: {output_dir}")
                return

            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{source_layer}"]')
            log_debug(f"Number of entities found: {len(entities)}")

            if preprocessors:
                # Process through each preprocessor in sequence
                processed_data = entities
                for preprocessor in preprocessors:
                    if preprocessor not in self.preprocessors:
                        log_warning(f"Preprocessor '{preprocessor}' not found, skipping")
                        continue
                    
                    log_debug(f"Applying preprocessor: {preprocessor}")
                    processed_data = self.preprocessors[preprocessor](processed_data, source_layer)
                    log_debug(f"Preprocessor {preprocessor} produced {len(processed_data)} features")
                
                # Convert final processed data to GeoDataFrame
                if isinstance(processed_data[0], dict):  # Check if we have features with attributes
                    points_df = gpd.GeoDataFrame(
                        geometry=[gpd.points_from_xy([p['coords'][0]], [p['coords'][1]])[0] for p in processed_data],
                        data=[p['attributes'] for p in processed_data],
                        crs=self.crs
                    )
                else:  # Backward compatibility for simple coordinate tuples
                    points_df = gpd.GeoDataFrame(
                        geometry=[gpd.points_from_xy([p[0]], [p[1]])[0] for p in processed_data],
                        crs=self.crs
                    )
                
                log_debug(f"GeoDataFrame created with {len(points_df)} features")
                # Store in layer_processor and write shapefile
                layer_name = Path(output_file).stem
                if write_shapefile(points_df, full_output_path):
                    log_debug(f"Successfully saved {len(processed_data)} processed features to {full_output_path}")
                else:
                    log_error(f"Failed to write {len(processed_data)} processed features to {full_output_path}")
            else:
                # Convert DXF entities directly to geometries
                geometries = []
                attributes = []
                unsupported_types = set()  # Keep track of unique unsupported types
                
                for entity in entities:
                    dxftype = entity.dxftype()
                    geom = None
                    attrs = {}

                    try:
                        if dxftype == 'LINE':
                            geom = LineString([(entity.dxf.start[0], entity.dxf.start[1]), 
                                             (entity.dxf.end[0], entity.dxf.end[1])])
                        
                        elif dxftype == 'CIRCLE':
                            geom = Point(entity.dxf.center[0], entity.dxf.center[1])
                            attrs['radius'] = entity.dxf.radius
                        
                        elif dxftype == 'POINT':
                            geom = Point(entity.dxf.location[0], entity.dxf.location[1])
                        
                        elif dxftype == 'LWPOLYLINE':
                            points = [(vertex[0], vertex[1]) for vertex in entity.get_points()]
                            if len(points) > 1:
                                if entity.closed:
                                    points.append(points[0])
                                    geom = Polygon(points)
                                else:
                                    geom = LineString(points)
                        
                        elif dxftype == 'POLYLINE':
                            points = [(vertex.dxf.location[0], vertex.dxf.location[1]) 
                                    for vertex in entity.vertices]
                            if len(points) > 1:
                                if entity.is_closed:
                                    points.append(points[0])
                                    geom = Polygon(points)
                                else:
                                    geom = LineString(points)
                        
                        elif dxftype == 'ARC':
                            # Convert arc to line segments
                            start_angle = math.degrees(entity.dxf.start_angle)
                            end_angle = math.degrees(entity.dxf.end_angle)
                            radius = entity.dxf.radius
                            center = entity.dxf.center
                            
                            # Generate points along the arc
                            num_segments = 32  # Adjust for smoothness
                            if end_angle < start_angle:
                                end_angle += 360
                            angles = np.linspace(start_angle, end_angle, num_segments)
                            points = []
                            for angle in angles:
                                rad_angle = math.radians(angle)
                                x = center[0] + radius * math.cos(rad_angle)
                                y = center[1] + radius * math.sin(rad_angle)
                                points.append((x, y))
                            geom = LineString(points)
                        
                        elif dxftype == 'ELLIPSE':
                            # Convert ellipse to line segments
                            center = entity.dxf.center
                            major_axis = entity.dxf.major_axis
                            ratio = entity.dxf.ratio
                            start_param = entity.dxf.start_param
                            end_param = entity.dxf.end_param
                            
                            # Generate points along the ellipse
                            num_segments = 32  # Adjust for smoothness
                            params = np.linspace(start_param, end_param, num_segments)
                            points = []
                            for param in params:
                                x = center[0] + major_axis[0] * math.cos(param)
                                y = center[1] + major_axis[1] * math.cos(param)
                                points.append((x, y))
                            geom = LineString(points)
                        
                        elif dxftype == 'SPLINE':
                            # Convert spline to line segments
                            points = []
                            for point in entity.control_points:
                                points.append((point[0], point[1]))
                            if len(points) > 1:
                                if entity.closed:
                                    points.append(points[0])
                                    geom = Polygon(points)
                                else:
                                    geom = LineString(points)
                        
                        elif dxftype == 'HATCH':
                            # Extract boundary paths
                            boundaries = []
                            for path in entity.paths:
                                points = [(vertex[0], vertex[1]) for vertex in path.vertices]
                                if len(points) > 2:
                                    points.append(points[0])  # Close the polygon
                                    boundaries.append(Polygon(points))
                            if boundaries:
                                geom = MultiPolygon(boundaries)
                        
                        elif dxftype == 'INSERT':
                            # Handle block references
                            block = doc.blocks[entity.dxf.name]
                            # Recursively process block entities
                            block_entities = block.query('*')
                            # TODO: Apply transformation matrix from INSERT entity
                            log_warning(f"Block reference processing not fully implemented for {entity.dxf.name}")
                        
                        if geom:
                            geometries.append(geom)
                            attributes.append(attrs)
                        else:
                            unsupported_types.add(dxftype)  # Add to set of unsupported types
                    
                    except Exception as e:
                        log_warning(f"Error processing entity {dxftype}: {str(e)}")
                        continue
                
                if geometries:
                    gdf = gpd.GeoDataFrame(geometry=geometries, data=attributes, crs=self.crs)
                    log_debug(f"GeoDataFrame created with {len(gdf)} features")
                    if write_shapefile(gdf, full_output_path):
                        log_debug(f"Successfully saved shapefile to {full_output_path}")
                    else:
                        log_error(f"Failed to write shapefile to {full_output_path}")
                else:
                    if unsupported_types:
                        log_warning(f"No supported geometries found in layer {source_layer}. "
                                  f"Unsupported entity types: {', '.join(sorted(unsupported_types))}")
                    else:
                        log_warning(f"No geometries found in layer {source_layer}")
                
        except Exception as e:
            log_error(f"Error processing DXF extract for layer {source_layer}: {str(e)}")