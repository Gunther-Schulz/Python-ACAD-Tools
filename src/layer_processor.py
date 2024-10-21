from src.project_loader import ProjectLoader
from src.utils import log_info, log_warning, log_error
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, LinearRing
import ezdxf
import math
from geopandas import GeoSeries

# Import operations individually
from src.operations import (
    create_copy_layer,
    create_buffer_layer,
    create_difference_layer,
    create_intersection_layer,
    create_filtered_layer,
    process_wmts_or_wms_layer,
    create_merged_layer,
    create_smooth_layer,
    _handle_contour_operation,
    _create_overlay_layer
)

class LayerProcessor:
    def __init__(self, project_loader, plot_ops=False):
        self.project_loader = project_loader
        self.all_layers = {}
        self.project_settings = project_loader.project_settings
        self.crs = project_loader.crs
        self.plot_ops = plot_ops  # New flag for plotting operations
    
    def process_layers(self):
        log_info("Starting to process layers...")
        
        self.setup_shapefiles()

        processed_layers = set()

        for layer in self.project_settings['geomLayers']:
            layer_name = layer['name']

            self.process_layer(layer, processed_layers)

        log_info("Finished processing layers.")

    def process_layer(self, layer, processed_layers):
            if isinstance(layer, str):
                layer_name = layer
                layer_obj = next((l for l in self.project_settings['geomLayers'] if l['name'] == layer_name), None)
            else:
                layer_name = layer['name']
                layer_obj = layer
    
            if layer_name in processed_layers:
                return
    
            log_info(f"Processing layer: {layer_name}")
            log_info(f"Layer object: {layer_obj}")
            
            if layer_obj is None:
                log_warning(f"Layer {layer_name} not found in project settings")
                return
    
            # Check for unrecognized keys
            recognized_keys = {'name', 'update', 'operations', 'shapeFile', 'dxfLayer', 'outputShapeFile', 'layerStyle', 'hatchStyle', 'performHatch','labelStyle', 'label', 'close', 'linetypeScale', 'linetypeGeneration', 'viewports', 'attributes', 'bluntAngles'}
            unrecognized_keys = set(layer_obj.keys()) - recognized_keys
            if unrecognized_keys:
                log_warning(f"Unrecognized keys in layer {layer_name}: {', '.join(unrecognized_keys)}")
    
            # Check for known style keys
            known_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'vp_freeze', 'transparency'}
            if 'layerStyle' in layer_obj:
                if isinstance(layer_obj['layerStyle'], str):
                    # If layerStyle is a string, it's a preset name
                    preset_style = self.project_loader.get_style(layer_obj['layerStyle'])
                    layer_obj['layerStyle'] = preset_style
                else:
                    # If it's a dict, it's a custom style, so we keep it as is
                    pass
    
                unknown_style_keys = set(layer_obj['layerStyle'].keys()) - known_style_keys
                if unknown_style_keys:
                    log_warning(f"Unknown style keys in layer {layer_name}: {', '.join(unknown_style_keys)}")
                
                # Check for typos in style keys
                for key in layer_obj['layerStyle'].keys():
                    closest_match = min(known_style_keys, key=lambda x: self.levenshtein_distance(key, x))
                    if key != closest_match and self.levenshtein_distance(key, closest_match) <= 2:
                        log_warning(f"Possible typo in style key for layer {layer_name}: '{key}'. Did you mean '{closest_match}'?")
    
                # Ensure transparency is between 0 and 1
                if 'transparency' in layer_obj['layerStyle']:
                    layer_obj['layerStyle']['transparency'] = max(0, min(layer_obj['layerStyle']['transparency'], 1))
    
            # Check for known labelStyle keys only if labels are present
            if 'label' in layer_obj or 'labelStyle' in layer_obj:
                if 'labelStyle' in layer_obj:
                    unknown_label_style_keys = set(layer_obj['labelStyle'].keys()) - known_style_keys
                    if unknown_label_style_keys:
                        log_warning(f"Unknown labelStyle keys in layer {layer_name}: {', '.join(unknown_label_style_keys)}")
    
            # Load DXF layer if specified, regardless of operations
            if 'dxfLayer' in layer_obj:
                self.load_dxf_layer(layer_name, layer_obj['dxfLayer'])
    
            if 'operations' in layer_obj:
                result_geometry = None
                for operation in layer_obj['operations']:
                    result_geometry = self.process_operation(layer_name, operation, processed_layers)
                if result_geometry is not None:
                    self.all_layers[layer_name] = result_geometry
            elif 'shapeFile' in layer_obj:
                # The shapefile should have been loaded in setup_shapefiles
                if layer_name not in self.all_layers:
                    log_warning(f"Shapefile for layer {layer_name} was not loaded properly")
            elif 'dxfLayer' not in layer_obj:
                self.all_layers[layer_name] = None
                log_info(f"Added layer {layer_name} without data")
    
            if 'outputShapeFile' in layer_obj:
                self.write_shapefile(layer_name, layer_obj['outputShapeFile'])
    
            if 'attributes' in layer_obj:
                if layer_name not in self.all_layers or self.all_layers[layer_name] is None:
                    self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)
                
                gdf = self.all_layers[layer_name]
                if 'attributes' not in gdf.columns:
                    gdf['attributes'] = None
                
                gdf['attributes'] = gdf['attributes'].apply(lambda x: {} if x is None else x)
                for key, value in layer_obj['attributes'].items():
                    gdf['attributes'] = gdf['attributes'].apply(lambda x: {**x, key: value})
                
                self.all_layers[layer_name] = gdf
    
            if 'bluntAngles' in layer_obj:
                blunt_config = layer_obj['bluntAngles']
                angle_threshold = blunt_config.get('angleThreshold', 45)
                blunt_distance = blunt_config.get('distance', 0.5)
    
                log_info(f"Applying blunt angles to layer '{layer_name}' with threshold {angle_threshold} and distance {blunt_distance}")
    
                if layer_name in self.all_layers:
                    original_geom = self.all_layers[layer_name]
                    blunted_geom = original_geom.geometry.apply(
                        lambda geom: self.blunt_sharp_angles(geom, angle_threshold, blunt_distance)
                    )
                    self.all_layers[layer_name].geometry = blunted_geom
    
                    log_info(f"Blunting complete for layer '{layer_name}'")
                    log_info(f"Original geometry count: {len(original_geom)}")
                    log_info(f"Blunted geometry count: {len(blunted_geom)}")
                else:
                    log_warning(f"Layer '{layer_name}' not found for blunting angles")
    
            processed_layers.add(layer_name)
    

    def process_operation(self, layer_name, operation, processed_layers):
        op_type = operation['type']
        
        log_info(f"Processing operation for layer {layer_name}: {op_type}")
        log_info(f"Operation details: {operation}")
        
        # Process dependent layers first
        if 'layers' in operation:
            for dep_layer_info in operation['layers']:
                dep_layer_name = dep_layer_info['name'] if isinstance(dep_layer_info, dict) else dep_layer_info
                log_info(f"Processing dependent layer: {dep_layer_name}")
                self.process_layer(dep_layer_name, processed_layers)
        else:
            # If 'layers' key is missing, apply the operation on the calling layer
            operation['layers'] = [layer_name]
    
        # Perform the operation
        result = None
        if op_type == 'copy':
            result = create_copy_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'buffer':
            result = create_buffer_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'difference':
            result = create_difference_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'intersection':
            result = create_intersection_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'filter':
            result = create_filtered_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'wmts' or op_type == 'wms':
            result = process_wmts_or_wms_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation, self.project_loader)
        elif op_type == 'merge':
            result = create_merged_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'smooth':
            result = create_smooth_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'contour':
            result = _handle_contour_operation(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        else:
            log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            return None
    
        if result is not None:
            self.all_layers[layer_name] = result
            if self.plot_ops:
                self.plot_operation_result(layer_name, op_type, result)
    
        return result

    def setup_shapefiles(self):
        for layer in self.project_settings['geomLayers']:
            layer_name = layer['name']
            if 'shapeFile' in layer:
                shapefile_path = self.project_loader.resolve_full_path(layer['shapeFile'])
                try:
                    gdf = gpd.read_file(shapefile_path)
                    gdf = self.standardize_layer_crs(layer_name, gdf)
                    if gdf is not None:
                        self.all_layers[layer_name] = gdf
                        log_info(f"Loaded shapefile for layer: {layer_name}")
                    else:
                        log_warning(f"Failed to load shapefile for layer: {layer_name}")
                except Exception as e:
                    log_warning(f"Failed to load shapefile for layer '{layer_name}': {str(e)}")
            elif 'dxfLayer' in layer:
                gdf = self.load_dxf_layer(layer_name, layer['dxfLayer'])
                self.all_layers[layer_name] = gdf
                if 'outputShapeFile' in layer:
                    output_path = self.project_loader.resolve_full_path(layer['outputShapeFile'])
                    self.write_shapefile(layer_name, output_path)

    def write_shapefile(self, layer_name, output_path):
        log_info(f"Writing shapefile for layer {layer_name}: {output_path}")
        if layer_name in self.all_layers:
            gdf = self.all_layers[layer_name]
            log_info(f"Type of data for {layer_name}: {type(gdf)}")
            log_info(f"Columns in the data: {gdf.columns.tolist() if hasattr(gdf, 'columns') else 'No columns'}")
            log_info(f"CRS of the data: {gdf.crs if hasattr(gdf, 'crs') else 'No CRS'}")
            log_info(f"Number of rows: {len(gdf) if hasattr(gdf, '__len__') else 'Unknown'}")
            
            if isinstance(gdf, gpd.GeoDataFrame):
                log_info(f"Geometry column name: {gdf.geometry.name}")
                log_info(f"Geometry types: {gdf.geometry.type.unique().tolist()}")
                
                # Handle GeometryCollection
                def convert_geometry(geom):
                    if isinstance(geom, GeometryCollection):
                        polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
                        if polygons:
                            return MultiPolygon(polygons)
                        return None
                    return geom

                gdf['geometry'] = gdf['geometry'].apply(convert_geometry)
                gdf = gdf[gdf['geometry'].notna()]

                if not gdf.empty:
                    full_path = self.project_loader.resolve_full_path(output_path)
                    gdf.to_file(full_path)
                    log_info(f"Shapefile written for layer {layer_name}: {full_path}")
                else:
                    log_warning(f"No valid geometries found for layer {layer_name} after conversion")
            else:
                log_warning(f"Cannot write shapefile for layer {layer_name}: not a GeoDataFrame")
        else:
            log_warning(f"Cannot write shapefile for layer {layer_name}: layer not found")

    def load_dxf_layer(self, layer_name, dxf_layer_name):
            try:
                log_info(f"Attempting to load DXF layer '{dxf_layer_name}' for layer: {layer_name}")
                doc = ezdxf.readfile(self.project_loader.dxf_filename)
                msp = doc.modelspace()
                
                geometries = []
                for entity in msp.query(f'*[layer=="{dxf_layer_name}"]'):
                    if isinstance(entity, (ezdxf.entities.LWPolyline, ezdxf.entities.Polyline)):
                        points = list(entity.vertices())
                        if len(points) >= 2:
                            if entity.closed or (points[0] == points[-1]):
                                geometries.append(Polygon(points))
                            else:
                                geometries.append(LineString(points))
                    else:
                        log_info(f"Skipping entity of type {type(entity)} in layer '{dxf_layer_name}'")
                
                log_info(f"Found {len(geometries)} geometries in DXF layer '{dxf_layer_name}'")
                
                if geometries:
                    gdf = gpd.GeoDataFrame(geometry=geometries, crs=self.crs)
                    self.all_layers[layer_name] = gdf
                    log_info(f"Loaded DXF layer '{dxf_layer_name}' for layer: {layer_name} with {len(gdf)} features")
                    log_info(f"Type of self.all_layers[{layer_name}]: {type(self.all_layers[layer_name])}")
                else:
                    log_warning(f"No valid geometries found in DXF layer '{dxf_layer_name}' for layer: {layer_name}")
                    gdf = gpd.GeoDataFrame(geometry=[], crs=self.crs)
                    self.all_layers[layer_name] = gdf
                
            except Exception as e:
                log_error(f"Failed to load DXF layer '{dxf_layer_name}' for layer '{layer_name}': {str(e)}")
                import traceback
                log_error(traceback.format_exc())
                gdf = gpd.GeoDataFrame(geometry=[], crs=self.crs)
                self.all_layers[layer_name] = gdf
            
            log_info(f"Final state of self.all_layers[{layer_name}]: {self.all_layers[layer_name]}")
            return gdf
    

    def _process_hatch_config(self, layer_name, hatch_config):
            log_info(f"Processing hatch configuration for layer: {layer_name}")
            
            # If 'layers' is not specified, use the current layer
            if 'layers' not in hatch_config:
                hatch_config['layers'] = [layer_name]
                log_info(f"No boundary layers specified for hatch. Using current layer: {layer_name}")
            
            # Ensure all boundary layers are processed
            for boundary_layer in hatch_config['layers']:
                if boundary_layer not in self.all_layers:
                    self.process_layer(boundary_layer, set())
            
            # Store hatch configuration in the layer properties
            if layer_name not in self.all_layers or self.all_layers[layer_name] is None:
                self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)
            
            # Create a copy of the existing DataFrame
            gdf = self.all_layers[layer_name].copy()
            
            # If 'attributes' column doesn't exist, create it
            if 'attributes' not in gdf.columns:
                gdf['attributes'] = None
            
            # Update the 'attributes' column with the hatch configuration
            gdf.loc[:, 'attributes'] = gdf['attributes'].apply(lambda x: {} if x is None else x)
            gdf.loc[:, 'attributes'] = gdf['attributes'].apply(lambda x: {**x, 'hatch_config': hatch_config})
            
            # Assign the modified DataFrame back to self.all_layers
            self.all_layers[layer_name] = gdf
            
            log_info(f"Stored hatch configuration for layer: {layer_name}")
    

    def levenshtein_distance(self, s1, s2):
            if len(s1) < len(s2):
                return self.levenshtein_distance(s2, s1)
    
            if len(s2) == 0:
                return len(s1)
    
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
    
            return previous_row[-1]
    
    def blunt_sharp_angles(self, geometry, angle_threshold, blunt_distance):
        if isinstance(geometry, GeoSeries):
            return geometry.apply(lambda geom: self.blunt_sharp_angles(geom, angle_threshold, blunt_distance))
        
        log_info(f"Blunting angles for geometry: {geometry.wkt[:100]}...")
        if isinstance(geometry, Polygon):
            return self._blunt_polygon_angles(geometry, angle_threshold, blunt_distance)
        elif isinstance(geometry, MultiPolygon):
            return MultiPolygon([self._blunt_polygon_angles(poly, angle_threshold, blunt_distance) for poly in geometry.geoms])
        elif isinstance(geometry, (LineString, MultiLineString)):
            return self._blunt_linestring_angles(geometry, angle_threshold, blunt_distance)
        elif isinstance(geometry, GeometryCollection):
            new_geoms = [self.blunt_sharp_angles(geom, angle_threshold, blunt_distance) for geom in geometry.geoms]
            return GeometryCollection(new_geoms)
        else:
            log_warning(f"Unsupported geometry type for blunting: {type(geometry)}")
            return geometry

    def _blunt_polygon_angles(self, polygon, angle_threshold, blunt_distance):
        log_info(f"Blunting polygon angles: {polygon.wkt[:100]}...")
        
        exterior_blunted = self._blunt_ring(LinearRing(polygon.exterior.coords), angle_threshold, blunt_distance)
        interiors_blunted = [self._blunt_ring(LinearRing(interior.coords), angle_threshold, blunt_distance) for interior in polygon.interiors]
        
        return Polygon(exterior_blunted, interiors_blunted)

    def _blunt_ring(self, ring, angle_threshold, blunt_distance):
        coords = list(ring.coords)
        new_coords = []
        
        for i in range(len(coords) - 1):  # -1 because the last point is the same as the first for rings
            prev_point = Point(coords[i-1])
            current_point = Point(coords[i])
            next_point = Point(coords[(i+1) % (len(coords)-1)])  # Wrap around for the last point
            
            # Skip processing if current point is identical to previous or next point
            if current_point.equals(prev_point) or current_point.equals(next_point):
                new_coords.append(coords[i])
                continue
            
            angle = self._calculate_angle(prev_point, current_point, next_point)
            
            if angle is not None and angle < angle_threshold:
                log_info(f"Blunting angle at point {i}")
                blunted_points = self._create_radical_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])
        
        new_coords.append(new_coords[0])  # Close the ring
        return LinearRing(new_coords)

    def _blunt_linestring_angles(self, linestring, angle_threshold, blunt_distance):
        log_info(f"Blunting linestring angles: {linestring.wkt[:100]}...")
        if isinstance(linestring, MultiLineString):
            new_linestrings = [self._blunt_linestring_angles(ls, angle_threshold, blunt_distance) for ls in linestring.geoms]
            return MultiLineString(new_linestrings)
        
        coords = list(linestring.coords)
        new_coords = [coords[0]]
        
        for i in range(1, len(coords) - 1):
            prev_point = Point(coords[i-1])
            current_point = Point(coords[i])
            next_point = Point(coords[i+1])
            
            angle = self._calculate_angle(prev_point, current_point, next_point)
            
            if angle is not None and angle < angle_threshold:
                log_info(f"Blunting angle at point {i}")
                blunted_points = self._create_radical_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])
        
        new_coords.append(coords[-1])
        return LineString(new_coords)

    def _calculate_angle(self, p1, p2, p3):
        v1 = [p1.x - p2.x, p1.y - p2.y]
        v2 = [p3.x - p2.x, p3.y - p2.y]
        
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        
        # Check if either vector has zero magnitude
        if v1_mag == 0 or v2_mag == 0:
            log_warning(f"Zero magnitude vector encountered: v1_mag={v1_mag}, v2_mag={v2_mag}")
            return None
        
        dot_product = v1[0] * v2[0] + v1[1] * v2[1]
        
        cos_angle = dot_product / (v1_mag * v2_mag)
        cos_angle = max(-1, min(1, cos_angle))  # Ensure the value is between -1 and 1
        angle_rad = math.acos(cos_angle)
        return math.degrees(angle_rad)

    def _create_radical_blunt_segment(self, p1, p2, p3, blunt_distance):
        log_info(f"Creating radical blunt segment for points: {p1}, {p2}, {p3}")
        v1 = [(p1.x - p2.x), (p1.y - p2.y)]
        v2 = [(p3.x - p2.x), (p3.y - p2.y)]
        
        # Normalize vectors
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        
        # Check if either vector has zero magnitude
        if v1_mag == 0 or v2_mag == 0:
            log_warning(f"Zero magnitude vector encountered in blunt segment: v1_mag={v1_mag}, v2_mag={v2_mag}")
            return [p2.coords[0]]  # Return the original point if we can't create a blunt segment
        
        v1_norm = [v1[0] / v1_mag, v1[1] / v1_mag]
        v2_norm = [v2[0] / v2_mag, v2[1] / v2_mag]
        
        # Calculate points for the new segment
        point1 = (p2.x + v1_norm[0] * blunt_distance, p2.y + v1_norm[1] * blunt_distance)
        point2 = (p2.x + v2_norm[0] * blunt_distance, p2.y + v2_norm[1] * blunt_distance)
        
        log_info(f"Radical blunt segment created: {point1}, {point2}")
        return [point1, point2]

    def standardize_layer_crs(self, layer_name, geometry_or_gdf):
        target_crs = self.crs
        log_info(f"Standardizing CRS for layer: {layer_name}")

        if isinstance(geometry_or_gdf, gpd.GeoDataFrame):
            log_info(f"Original CRS: {geometry_or_gdf.crs}")
            if geometry_or_gdf.crs is None:
                log_warning(f"Layer {layer_name} has no CRS. Setting to target CRS: {target_crs}")
                geometry_or_gdf.set_crs(target_crs, inplace=True)
            elif geometry_or_gdf.crs != target_crs:
                log_info(f"Transforming layer {layer_name} from {geometry_or_gdf.crs} to {target_crs}")
                geometry_or_gdf = geometry_or_gdf.to_crs(target_crs)
            log_info(f"Final CRS for layer {layer_name}: {geometry_or_gdf.crs}")
            return geometry_or_gdf
        elif isinstance(geometry_or_gdf, gpd.GeoSeries):
            return self.standardize_layer_crs(layer_name, gpd.GeoDataFrame(geometry=geometry_or_gdf))
        elif isinstance(geometry_or_gdf, (Polygon, MultiPolygon, LineString, MultiLineString)):
            log_info(f"Processing individual geometry for layer: {layer_name}")
            gdf = gpd.GeoDataFrame(geometry=[geometry_or_gdf], crs=target_crs)
            log_info(f"Created GeoDataFrame with CRS: {gdf.crs}")
            return gdf.geometry.iloc[0]
        else:
            log_warning(f"Unsupported type for layer {layer_name}: {type(geometry_or_gdf)}")
            return geometry_or_gdf















