import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
import os
import shutil
from src.project_loader import project_loader
import ezdxf
from src.operations.common_operations import *

from src.operations import *

class LayerProcessor:
    def __init__(self, project_loader, plot_ops=False):
            self.project_loader = project_loader
            self.all_layers = {}
            self.project_settings = project_loader.project_settings
            self.crs = project_loader.crs
            self.plot_ops = plot_ops  # New flag for plotting operations
    

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
                result = self.create_copy_layer(layer_name, operation)
            elif op_type == 'buffer':
                result = self.create_buffer_layer(layer_name, operation)
            elif op_type == 'difference':
                result = self.create_difference_layer(layer_name, operation)
            elif op_type == 'intersection':
                result = self.create_intersection_layer(layer_name, operation)
            elif op_type == 'filter':
                result = self.create_filtered_layer(layer_name, operation)
            elif op_type == 'wmts' or op_type == 'wms':
                result = self.process_wmts_or_wms_layer(layer_name, operation)
            elif op_type == 'merge':
                result = self.create_merged_layer(layer_name, operation)
            elif op_type == 'smooth':
                result = self.create_smooth_layer(layer_name, operation)
            elif op_type == 'contour':
                result = self._handle_contour_operation(layer_name, operation)
            else:
                log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
    
            if result is not None:
                self.all_layers[layer_name] = result
                if self.plot_ops:
                    self.plot_operation_result(layer_name, op_type, result)
    
            return result
    

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
                log_warning(f"Failed to load DXF layer '{dxf_layer_name}' for layer '{layer_name}': {str(e)}")
                import traceback
                log_warning(traceback.format_exc())
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
    

