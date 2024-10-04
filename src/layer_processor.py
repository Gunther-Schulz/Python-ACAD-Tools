import geopandas as gpd
from matplotlib import pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint, GeometryCollection
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles, download_wms_tiles, process_and_stitch_tiles
from shapely.ops import unary_union, linemerge
from shapely.validation import make_valid
from shapely.geometry import LinearRing
import shutil
from src.contour_processor import process_contour
from owslib.wmts import WebMapTileService
import ezdxf
from shapely.geometry import Polygon, LineString
from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import make_valid
import pandas as pd
import math
from geopandas import GeoSeries
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, GeometryCollection

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

        for layer in self.project_settings['dxfLayers']:
            layer_name = layer['name']

            self.process_layer(layer, processed_layers)

        log_info("Finished processing layers.")

    def process_layer(self, layer, processed_layers):
        if isinstance(layer, str):
            layer_name = layer
            layer_obj = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
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
        recognized_keys = {'name', 'update', 'operations', 'shapeFile', 'dxfLayer', 'outputShapeFile', 'style', 'labelStyle', 'label', 'close', 'linetypeScale', 'linetypeGeneration', 'viewports', 'attributes'}
        unrecognized_keys = set(layer_obj.keys()) - recognized_keys
        if unrecognized_keys:
            log_warning(f"Unrecognized keys in layer {layer_name}: {', '.join(unrecognized_keys)}")

        # Check for known style keys
        known_style_keys = {'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'vp_freeze', 'transparency'}
        if 'style' in layer_obj:
            unknown_style_keys = set(layer_obj['style'].keys()) - known_style_keys
            if unknown_style_keys:
                log_warning(f"Unknown style keys in layer {layer_name}: {', '.join(unknown_style_keys)}")
            
            # Check for typos in style keys
            for key in layer_obj['style'].keys():
                closest_match = min(known_style_keys, key=lambda x: self.levenshtein_distance(key, x))
                if key != closest_match and self.levenshtein_distance(key, closest_match) <= 2:
                    log_warning(f"Possible typo in style key for layer {layer_name}: '{key}'. Did you mean '{closest_match}'?")

            # Ensure transparency is between 0 and 1
            if 'transparency' in layer_obj['style']:
                layer_obj['style']['transparency'] = max(0, min(layer_obj['style']['transparency'], 1))

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

    def _process_hatch_config(self, layer_name, hatch_config):
        log_info(f"Processing hatch configuration for layer: {layer_name}")
        
        # Validate hatch configuration
        if 'layers' not in hatch_config:
            log_warning(f"No boundary layers specified for hatch in layer: {layer_name}")
            return
        
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

    def plot_operation_result(self, layer_name, op_type, result):
        plt.figure(figsize=(10, 10))
        if isinstance(result, gpd.GeoDataFrame):
            result.plot(ax=plt.gca())
        elif isinstance(result, list):  # For WMTS tiles
            log_info(f"WMTS layer {layer_name} cannot be plotted directly.")
            return
        else:
            gpd.GeoSeries([result]).plot(ax=plt.gca())
        plt.title(f"{op_type.capitalize()} Operation Result for {layer_name}")
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def _process_layer_info(self, layer_info):
        if isinstance(layer_info, str):
            return layer_info, []
        elif isinstance(layer_info, dict):
            return layer_info['name'], layer_info.get('values', [])
        else:
            log_warning(f"Invalid layer info type: {type(layer_info)}")
            return None, []

    def _get_filtered_geometry(self, layer_name, values):
        if layer_name not in self.all_layers:
            log_warning(f"Layer '{layer_name}' not found")
            return None

        source_gdf = self.all_layers[layer_name]

        if values:
            label_column = next((l['label'] for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
            if label_column and label_column in source_gdf.columns:
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(values)]
                return filtered_gdf.geometry.unary_union
            else:
                log_warning(f"Label column '{label_column}' not found in layer '{layer_name}'")
                return None
        else:
            return source_gdf.geometry.unary_union

    def create_copy_layer(self, layer_name, operation):
        source_layers = operation.get('layers', [])
        combined_geometry = None

        for layer_info in source_layers:
            source_layer_name, values = self._process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = self._get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, gpd.GeoDataFrame(geometry=[combined_geometry], crs=self.crs))
            log_info(f"Copied layer(s) to {layer_name}")
            
        else:
            log_warning(f"No valid source layers found for copy operation on {layer_name}")

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

    def setup_shapefiles(self):
        for layer in self.project_settings['dxfLayers']:
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

    def ensure_geodataframe(self, layer_name, geometry):
        if not isinstance(geometry, gpd.GeoDataFrame):
            if isinstance(geometry, gpd.GeoSeries):
                return gpd.GeoDataFrame(geometry=geometry, crs=self.crs)
            elif isinstance(geometry, (Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection)):
                return gpd.GeoDataFrame(geometry=[geometry], crs=self.crs)
            else:
                log_warning(f"Unsupported type for layer {layer_name}: {type(geometry)}")
                return None
        return geometry                       

    def create_filtered_layer(self, layer_name, operation):
        log_info(f"Creating filtered layer: {layer_name}")
        
        if layer_name not in self.all_layers:
            log_warning(f"Layer '{layer_name}' not found for filtering")
            return

        source_gdf = self.all_layers[layer_name]
        filtered_gdf = source_gdf.copy()

        log_info(f"Initial number of geometries in {layer_name}: {len(filtered_gdf)}")
        log_info(f"Initial geometries: {filtered_gdf.geometry.tolist()}")
        log_info(f"Initial attributes: {filtered_gdf}")

        for layer_info in operation['layers']:
            source_layer_name, values = self._process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            log_info(f"Processing filter layer: {source_layer_name}")

            filter_geometry = self._get_filtered_geometry(source_layer_name, values)
            if filter_geometry is None:
                continue

            log_info(f"Filter geometry type for {source_layer_name}: {type(filter_geometry)}")

            # Explode MultiPolygon into individual Polygons
            filtered_gdf = filtered_gdf.explode(index_parts=False)

            # Apply a small buffer to handle edge-on-edge proximity
            small_buffer = -1
            buffered_filter_geometry = filter_geometry.buffer(small_buffer)

            # Filter the geometries based on intersection with the buffered filter geometry
            filtered_gdf = filtered_gdf[filtered_gdf.geometry.intersects(buffered_filter_geometry)]

            log_info(f"Number of geometries after filtering with {source_layer_name}: {len(filtered_gdf)}")
            log_info(f"Geometries after filtering with {source_layer_name}: {filtered_gdf.geometry.tolist()}")
            log_info(f"Attributes after filtering with {source_layer_name}: {filtered_gdf}")

            # If no geometries are left after filtering, break early
            if filtered_gdf.empty:
                break

        if not filtered_gdf.empty:
            self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, filtered_gdf)
            log_info(f"Filtered layer: {layer_name} with {len(filtered_gdf)} geometries")
            log_info(f"Final geometries: {filtered_gdf.geometry.tolist()}")
            log_info(f"Final attributes: {filtered_gdf}")
        else:
            log_warning(f"No geometries left after filtering for layer: {layer_name}")
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def create_difference_layer(self, layer_name, operation):
        self._create_overlay_layer(layer_name, operation, 'difference')

    def create_intersection_layer(self, layer_name, operation):
        self._create_overlay_layer(layer_name, operation, 'intersection')


    def _create_overlay_layer(self, layer_name, operation, overlay_type):
        log_info(f"Creating {overlay_type} layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        overlay_layers = operation.get('layers', [])
        
        if not overlay_layers:
            log_warning(f"No overlay layers specified for {layer_name}")
            return
        
        base_geometry = self.all_layers.get(layer_name)
        if base_geometry is None:
            log_warning(f"Base layer '{layer_name}' not found for {overlay_type} operation")
            return
        
        combined_overlay_geometry = None
        for layer_info in overlay_layers:
            overlay_layer_name, values = self._process_layer_info(layer_info)
            if overlay_layer_name is None:
                continue

            overlay_geometry = self._get_filtered_geometry(overlay_layer_name, values)
            if overlay_geometry is None:
                continue

            if combined_overlay_geometry is None:
                combined_overlay_geometry = overlay_geometry
            else:
                combined_overlay_geometry = combined_overlay_geometry.union(overlay_geometry)

        if combined_overlay_geometry is None:
            log_warning(f"No valid overlay geometries found for layer '{layer_name}'")
            return

        try:
            if overlay_type == 'difference':
                result_geometry = base_geometry.geometry.difference(combined_overlay_geometry)
            elif overlay_type == 'intersection':
                result_geometry = base_geometry.geometry.intersection(combined_overlay_geometry)
            
            # Apply a series of cleaning operations
            result_geometry = self._clean_geometry(result_geometry)
            
            log_info(f"Applied {overlay_type} operation and cleaned up results")
        except Exception as e:
            log_error(f"Error during {overlay_type} operation: {str(e)}")
            import traceback
            log_error(f"Traceback:\n{traceback.format_exc()}")
            return

        # Check if result_geometry is empty
        if result_geometry.empty:
            log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=base_geometry.crs)
        else:
            # Create a new GeoDataFrame with the resulting geometries
            result_gdf = gpd.GeoDataFrame(geometry=result_geometry, crs=base_geometry.crs)
            self.all_layers[layer_name] = result_gdf
            log_info(f"Created {overlay_type} layer: {layer_name} with {len(result_geometry)} geometries")





    def _clean_geometry(self, geometry):
        if isinstance(geometry, (gpd.GeoSeries, pd.Series)):
            return geometry.apply(self._clean_single_geometry)
        else:
            return self._clean_single_geometry(geometry)

    def _clean_single_geometry(self, geometry):
        # Ensure the geometry is valid
        geometry = make_valid(geometry)
        
        # Simplify the geometry
        simplify_tolerance = 0.1
        geometry = geometry.simplify(simplify_tolerance, preserve_topology=True)
        
        # Remove small polygons and attempt to remove slivers
        min_area = 1
        sliver_removal_distance = 0.05

        if isinstance(geometry, Polygon):
            return self._clean_polygon(geometry, sliver_removal_distance, min_area)
        elif isinstance(geometry, MultiPolygon):
            cleaned_polygons = [self._clean_polygon(poly, sliver_removal_distance, min_area) 
                                for poly in geometry.geoms]
            cleaned_polygons = [poly for poly in cleaned_polygons if poly is not None]
            if not cleaned_polygons:
                return None
            return MultiPolygon(cleaned_polygons)
        elif isinstance(geometry, GeometryCollection):
            cleaned_geoms = [self._clean_single_geometry(geom) for geom in geometry.geoms]
            cleaned_geoms = [geom for geom in cleaned_geoms if geom is not None]
            if not cleaned_geoms:
                return None
            return GeometryCollection(cleaned_geoms)
        else:
            # For non-polygon geometries, just return the simplified version
            return geometry

    def _clean_polygon(self, polygon, sliver_removal_distance, min_area):
        # Clean the exterior
        cleaned_exterior = self._clean_linear_ring(polygon.exterior, sliver_removal_distance)
        if cleaned_exterior is None:
            return None
        
        # Clean the interiors
        cleaned_interiors = [self._clean_linear_ring(interior, sliver_removal_distance) 
                             for interior in polygon.interiors]
        cleaned_interiors = [interior for interior in cleaned_interiors if interior is not None]
        
        # Reconstruct the polygon
        cleaned_polygon = Polygon(cleaned_exterior, cleaned_interiors)
        
        # Remove small polygons
        if cleaned_polygon.area < min_area:
            return None
        
        return cleaned_polygon

    def _clean_linear_ring(self, ring, tolerance):
        # Convert to LineString to use linemerge
        line = LineString(ring.coords)
        
        # Merge any nearly coincident line segments
        merged = linemerge([line])

        # Remove any points that are too close together
        cleaned_coords = []
        for coord in merged.coords:
            if not cleaned_coords or Point(coord).distance(Point(cleaned_coords[-1])) > tolerance:
                cleaned_coords.append(coord)
        
        # Ensure the ring is closed
        if cleaned_coords[0] != cleaned_coords[-1]:
            cleaned_coords.append(cleaned_coords[0])
        
        # Check if we have enough coordinates to form a valid LinearRing
        if len(cleaned_coords) < 4:
            return None
        
        return LinearRing(cleaned_coords)

    def _remove_small_polygons(self, geometry, min_area):
        if isinstance(geometry, Polygon):
            if geometry.area >= min_area:
                return geometry
            else:
                return Polygon()
        elif isinstance(geometry, MultiPolygon):
            return MultiPolygon([poly for poly in geometry.geoms if poly.area >= min_area])
        else:
            return geometry
            
    def create_buffer_layer(self, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layers = operation.get('layers', [])
        buffer_distance = operation['distance']
        buffer_mode = operation.get('mode', 'off')  # Changed default to 'off'
        join_style = operation.get('joinStyle', 'mitre')  # Default to 'round'

        # Map join style names to shapely constants
        join_style_map = {
            'round': 1,
            'mitre': 2,
            'bevel': 3
        }
        join_style_value = join_style_map.get(join_style, 1)  # Default to 'round' if invalid

        combined_geometry = None
        for layer_info in source_layers:
            source_layer_name, values = self._process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = self._get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            if buffer_mode == 'outer':
                buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                result = buffered.difference(combined_geometry)
            elif buffer_mode == 'inner':
                result = combined_geometry.buffer(-buffer_distance, cap_style=2, join_style=join_style_value)
            elif buffer_mode == 'keep':
                buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                result = [combined_geometry, buffered]
            else:  # 'off' or any other value
                result = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)

            # Ensure the result is a valid geometry type for shapefiles
            if buffer_mode == 'keep':
                result_geom = []
                for geom in result:
                    if isinstance(geom, (Polygon, MultiPolygon)):
                        result_geom.append(geom)
                    elif isinstance(geom, GeometryCollection):
                        result_geom.extend([g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))])
            else:
                if isinstance(result, (Polygon, MultiPolygon)):
                    result_geom = [result]
                elif isinstance(result, GeometryCollection):
                    result_geom = [geom for geom in result.geoms if isinstance(geom, (Polygon, MultiPolygon))]
                else:
                    result_geom = []

            result_gdf = gpd.GeoDataFrame(geometry=result_geom, crs=self.crs)
            self.all_layers[layer_name] = result_gdf
            log_info(f"Created buffer layer: {layer_name} with {len(result_geom)} geometries")
        else:
            log_warning(f"No valid source geometry found for buffer layer '{layer_name}'")
            result_gdf = gpd.GeoDataFrame(geometry=[], crs=self.crs)
            self.all_layers[layer_name] = result_gdf

        return self.all_layers[layer_name]

    def process_wmts_or_wms_layer(self, layer_name, operation):
        log_info(f"Processing WMTS/WMS layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        target_folder = self.project_loader.resolve_full_path(operation['targetFolder'])
        zoom_level = operation.get('zoom')
        
        zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}") if zoom_level else target_folder
        
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
        update_flag = layer_info.get('update', False) if layer_info else False
        overwrite_flag = operation.get('overwrite', False)
        
        os.makedirs(zoom_folder, exist_ok=True)
        
        log_info(f"Target folder path: {zoom_folder}")
        log_info(f"Update flag: {update_flag}, Overwrite flag: {overwrite_flag}")

        layers = operation.get('layers', [])
        buffer_distance = operation.get('buffer', 100)
        service_info = {
            'url': operation['url'],
            'layer': operation['layer'],
            'proj': operation.get('proj'),
            'srs': operation.get('srs'),
            'format': operation.get('format', 'image/png'),
            'sleep': operation.get('sleep', 0),
            'limit': operation.get('limit', 0),
            'postProcess': operation.get('postProcess', {}),
            'overwrite': overwrite_flag,
            'zoom': zoom_level
        }

        service_info['postProcess']['removeText'] = operation.get('postProcess', {}).get('removeText', False)
        service_info['postProcess']['textRemovalMethod'] = operation.get('postProcess', {}).get('textRemovalMethod', 'tesseract')

        stitch_tiles = operation.get('stitchTiles', False)
        service_info['stitchTiles'] = stitch_tiles

        log_info(f"Service info: {service_info}")
        log_info(f"Layers to process: {layers}")

        wmts = WebMapTileService(service_info['url'])
        tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
        available_zooms = sorted(tile_matrix.keys(), key=int)
        
        requested_zoom = service_info.get('zoom')
        
        if requested_zoom is None:
            # Use the highest available zoom level if not specified
            chosen_zoom = available_zooms[-1]
            log_info(f"No zoom level specified. Using highest available zoom: {chosen_zoom}")
        else:
            # Try to use the manually specified zoom level
            if str(requested_zoom) in available_zooms:
                chosen_zoom = str(requested_zoom)
            else:
                error_message = (
                    f"Error: Zoom level {requested_zoom} not available for projection {service_info['proj']}.\n"
                    f"Available zoom levels: {', '.join(available_zooms)}.\n"
                    f"Please choose a zoom level from the available options or remove the 'zoom' key to use the highest available zoom."
                )
                raise ValueError(error_message)
        
        service_info['zoom'] = chosen_zoom
        log_info(f"Using zoom level: {chosen_zoom}")
        
        all_tiles = []
        for layer in layers:
            if layer in self.all_layers:
                layer_geometry = self.all_layers[layer]
                if isinstance(layer_geometry, gpd.GeoDataFrame):
                    layer_geometry = layer_geometry.geometry.unary_union

                log_info(f"Downloading tiles for layer: {layer}")
                log_info(f"Layer geometry type: {type(layer_geometry)}")
                log_info(f"Layer geometry bounds: {layer_geometry.bounds}")

                if 'wmts' in operation['type'].lower():
                    downloaded_tiles = download_wmts_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                    wmts = WebMapTileService(service_info['url'])
                    tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
                    try:
                        tile_matrix_zoom = tile_matrix[str(service_info['zoom'])]
                    except KeyError:
                        available_zooms = sorted(tile_matrix.keys())
                        error_message = (
                            f"Error: Zoom level {service_info['zoom']} not available for projection {service_info['proj']}.\n"
                            f"Available zoom levels: {', '.join(available_zooms)}.\n"
                            f"Please choose a zoom level from the available options."
                        )
                        raise ValueError(error_message)
                else:
                    downloaded_tiles = download_wms_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                    tile_matrix_zoom = None

                if stitch_tiles:
                    processed_tiles = process_and_stitch_tiles(service_info, downloaded_tiles, tile_matrix_zoom, zoom_folder, layer)
                    all_tiles.extend(processed_tiles)
                else:
                    all_tiles.extend(downloaded_tiles)
            else:
                log_warning(f"Layer {layer} not found for WMTS/WMS download of {layer_name}")

        self.all_layers[layer_name] = all_tiles
        log_info(f"Total tiles for {layer_name}: {len(all_tiles)}")

        return self.all_layers[layer_name]

    def get_existing_tiles(self, zoom_folder):
        existing_tiles = []
        image_extensions = ('.png', '.jpg', '.jpeg', '.tif', '.tiff')
        world_file_extensions = {
            '.png': '.pgw',
            '.jpg': '.jgw',
            '.jpeg': '.jgw',
            '.tif': '.tfw',
            '.tiff': '.tfw'
        }
        
        for root, dirs, files in os.walk(zoom_folder):
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith(image_extensions):
                    image_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file_lower)[1]
                    world_file_ext = world_file_extensions[file_ext]
                    world_file_path = os.path.splitext(image_path)[0] + world_file_ext
                    
                    if os.path.exists(world_file_path):
                        existing_tiles.append((image_path, world_file_path))
        
        log_info(f"Found {len(existing_tiles)} existing tiles in {zoom_folder}")
        return existing_tiles

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

    def create_merged_layer(self, layer_name, operation):
        log_info(f"Creating merged layer: {layer_name}")
        source_layers = operation.get('layers', [])
        
        combined_geometries = []
        for layer_info in source_layers:
            source_layer_name, values = self._process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = self._get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            log_info(f"Adding geometry from layer '{source_layer_name}': {layer_geometry.geom_type}")
            combined_geometries.append(layer_geometry)

        log_info(f"Total geometries collected: {len(combined_geometries)}")

        if combined_geometries:
            # Apply buffer trick
            buffer_distance = 0.01  # Adjust this value as needed
            log_info(f"Applying buffer trick with distance: {buffer_distance}")
            
            buffered_geometries = [geom.buffer(buffer_distance) for geom in combined_geometries]
            log_info("Merging buffered geometries")
            merged_geometry = unary_union(buffered_geometries)
            log_info(f"Merged buffered geometry type: {merged_geometry.geom_type}")
            
            # Unbuffer to get back to original size
            log_info("Unbuffering merged geometry")
            unbuffered_geometry = merged_geometry.buffer(-buffer_distance)
            log_info(f"Unbuffered geometry type: {unbuffered_geometry.geom_type}")
            
            # Simplify the unbuffered geometry
            log_info("Simplifying unbuffered geometry")
            simplified_geometry = unbuffered_geometry.simplify(0.1)
            log_info(f"Simplified geometry type: {simplified_geometry.geom_type}")
            
            # If the result is a MultiPolygon, convert it to separate Polygons
            if isinstance(simplified_geometry, MultiPolygon):
                log_info("Result is a MultiPolygon, separating into individual Polygons")
                result_geometries = list(simplified_geometry.geoms)
            elif isinstance(simplified_geometry, Polygon):
                log_info("Result is a single Polygon")
                result_geometries = [simplified_geometry]
            else:
                log_info(f"Result is of type {type(simplified_geometry)}")
                result_geometries = [simplified_geometry]
            
            log_info(f"Number of resulting geometries: {len(result_geometries)}")
            
            # Create a GeoDataFrame with the resulting geometries
            result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=self.crs)
            self.all_layers[layer_name] = result_gdf
            log_info(f"Created merged layer '{layer_name}' with {len(result_gdf)} geometries")
            
            # Log details of each resulting geometry
            for i, geom in enumerate(result_gdf.geometry):
                log_info(f"Geometry {i+1}: {geom.geom_type}, Area: {geom.area}, Length: {geom.length}")
        else:
            log_warning(f"No valid source geometries found for merged layer '{layer_name}'")
            # Return an empty GeoDataFrame to maintain consistency
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

        return self.all_layers[layer_name]

    def create_smooth_layer(self, layer_name, operation):
        log_info(f"Creating smooth layer: {layer_name}")
        source_layers = operation.get('layers', [])
        strength = operation.get('strength', 1.0)  # Default strength to 1.0

        combined_geometry = None
        for layer_info in source_layers:
            source_layer_name, values = self._process_layer_info(layer_info)
            if source_layer_name is None:
                continue

            layer_geometry = self._get_filtered_geometry(source_layer_name, values)
            if layer_geometry is None:
                continue

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.union(layer_geometry)

        if combined_geometry is not None:
            smoothed_geometry = self.smooth_geometry(combined_geometry, strength)
            self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, gpd.GeoDataFrame(geometry=[smoothed_geometry], crs=self.crs))
            log_info(f"Created smooth layer: {layer_name}")
        else:
            log_warning(f"No valid source geometry found for smooth layer '{layer_name}'")
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def smooth_geometry(self, geometry, strength):
        # Simplify the geometry
        smoothed = geometry.simplify(strength, preserve_topology=True)
        
        # Ensure the smoothed geometry does not expand beyond the original geometry
        if not geometry.contains(smoothed):
            smoothed = geometry.intersection(smoothed)
        
        # Increase vertex count for smoother curves
        if isinstance(smoothed, (Polygon, MultiPolygon)):
            smoothed = smoothed.buffer(0.01).buffer(-0.01)
        
        # Ensure the smoothed geometry does not expand beyond the original geometry after vertex increase
        if not geometry.contains(smoothed):
            smoothed = geometry.intersection(smoothed)
        
        return smoothed

    def _handle_contour_operation(self, layer_name, operation):
        log_info(f"Starting contour operation for layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        geltungsbereich = self._get_filtered_geometry(operation['layers'][0], [])
        if geltungsbereich is None:
            log_warning(f"Geltungsbereich not found for contour operation on layer '{layer_name}'")
            return None

        buffer_distance = operation.get('buffer', 0)
        contour_gdf = process_contour(operation, geltungsbereich, buffer_distance, self.crs)

        if layer_name in self.all_layers:
            log_warning(f"Layer '{layer_name}' already exists. Overwriting with new contour data.")
        
        self.all_layers[layer_name] = contour_gdf
        log_info(f"Finished contour operation for layer: {layer_name}")
        log_info(f"Number of contour features: {len(contour_gdf)}")
        return contour_gdf

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

    def _merge_close_vertices(self, geometry, tolerance=0.1):
        def merge_points(geom):
            if isinstance(geom, LineString):
                coords = list(geom.coords)
                merged_coords = [coords[0]]
                for coord in coords[1:]:
                    if Point(coord).distance(Point(merged_coords[-1])) > tolerance:
                        merged_coords.append(coord)
                return LineString(merged_coords)
            elif isinstance(geom, Polygon):
                exterior_coords = merge_points(LineString(geom.exterior.coords)).coords
                interiors = [merge_points(LineString(interior.coords)).coords for interior in geom.interiors]
                return Polygon(exterior_coords, interiors)
            elif isinstance(geom, MultiPolygon):
                return MultiPolygon([merge_points(part) for part in geom.geoms])
            elif isinstance(geom, MultiLineString):
                return MultiLineString([merge_points(part) for part in geom.geoms])
            else:
                return geom

        if isinstance(geometry, GeometryCollection):
            return GeometryCollection([merge_points(geom) for geom in geometry.geoms])
        else:
            return merge_points(geometry)

    def blunt_sharp_angles(self, geometry, angle_threshold, blunt_distance):
        if isinstance(geometry, GeoSeries):
            return geometry.apply(lambda geom: self.blunt_sharp_angles(geom, angle_threshold, blunt_distance))
        
        log_info(f"Blunting angles for geometry: {geometry.wkt[:100]}...")
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return self._blunt_polygon_angles(geometry, angle_threshold, blunt_distance)
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
        if isinstance(polygon, MultiPolygon):
            new_polygons = [self._blunt_polygon_angles(p, angle_threshold, blunt_distance) for p in polygon.geoms]
            return MultiPolygon(new_polygons)
        
        exterior_blunted = self._blunt_linestring_angles(LineString(polygon.exterior.coords), angle_threshold, blunt_distance)
        interiors_blunted = [self._blunt_linestring_angles(LineString(interior.coords), angle_threshold, blunt_distance) for interior in polygon.interiors]
        
        return Polygon(exterior_blunted, interiors_blunted)

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
            log_info(f"Angle at point {i}: {angle} degrees")
            
            if angle < angle_threshold:
                log_info(f"Blunting angle at point {i}")
                blunted_points = self._create_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])
        
        new_coords.append(coords[-1])
        result = LineString(new_coords)
        log_info(f"Blunted linestring result: {result.wkt[:100]}...")
        return result

    def _calculate_angle(self, p1, p2, p3):
        v1 = [p1.x - p2.x, p1.y - p2.y]
        v2 = [p3.x - p2.x, p3.y - p2.y]
        
        dot_product = v1[0] * v2[0] + v1[1] * v2[1]
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        
        cos_angle = dot_product / (v1_mag * v2_mag)
        angle_rad = math.acos(min(1, max(-1, cos_angle)))
        return math.degrees(angle_rad)

    def _create_blunt_segment(self, p1, p2, p3, blunt_distance):
        log_info(f"Creating blunt segment for points: {p1}, {p2}, {p3}")
        v1 = [(p1.x - p2.x), (p1.y - p2.y)]
        v2 = [(p3.x - p2.x), (p3.y - p2.y)]
        
        # Normalize vectors
        v1_mag = math.sqrt(v1[0]**2 + v1[1]**2)
        v2_mag = math.sqrt(v2[0]**2 + v2[1]**2)
        v1_norm = [v1[0] / v1_mag, v1[1] / v1_mag]
        v2_norm = [v2[0] / v2_mag, v2[1] / v2_mag]
        
        # Calculate points for the new segment
        point1 = (p2.x + v1_norm[0] * blunt_distance, p2.y + v1_norm[1] * blunt_distance)
        point2 = (p2.x + v2_norm[0] * blunt_distance, p2.y + v2_norm[1] * blunt_distance)
        
        log_info(f"Blunt segment created: {point1}, {point2}")
        return [point1, point2]