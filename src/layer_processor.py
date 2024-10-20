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
from shapely.validation import explain_validity
import re

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
        log_info(f"Initial number of geometries in {layer_name}: {len(source_gdf)}")

        if values:
            label_column = next((l['label'] for l in self.project_settings['geomLayers'] if l['name'] == layer_name), None)
            if label_column and label_column in source_gdf.columns:
                filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(values)].copy()
                log_info(f"Number of geometries after filtering by values: {len(filtered_gdf)}")
            else:
                log_warning(f"Label column '{label_column}' not found in layer '{layer_name}'")
                return None
        else:
            filtered_gdf = source_gdf.copy()

        # Check validity of original geometries
        invalid_geoms = filtered_gdf[~filtered_gdf.geometry.is_valid]
        if not invalid_geoms.empty:
            log_warning(f"Found {len(invalid_geoms)} invalid geometries in layer '{layer_name}'")
            
            # Plot the layer with invalid points marked
            fig, ax = plt.subplots(figsize=(12, 8))
            filtered_gdf.plot(ax=ax, color='blue', alpha=0.5)
            
            for idx, geom in invalid_geoms.geometry.items():
                reason = explain_validity(geom)
                log_warning(f"Invalid geometry at index {idx}: {reason}")
                
                # Extract coordinates of invalid points
                coords = self._extract_coords_from_reason(reason)
                if coords:
                    ax.plot(coords[0], coords[1], 'rx', markersize=10, markeredgewidth=2)
                    ax.annotate(f"Invalid point", (coords[0], coords[1]), xytext=(5, 5), 
                                textcoords='offset points', color='red', fontsize=8)
                else:
                    log_warning(f"Could not extract coordinates from reason: {reason}")
            
            # Add some buffer to the plot extent
            x_min, y_min, x_max, y_max = filtered_gdf.total_bounds
            ax.set_xlim(x_min - 10, x_max + 10)
            ax.set_ylim(y_min - 10, y_max + 10)
            
            plt.title(f"Layer: {layer_name} - Invalid Points Marked")
            plt.axis('equal')
            plt.tight_layout()
            plt.savefig(f"invalid_geometries_{layer_name}.png", dpi=300)
            plt.close()

            log_info(f"Plot saved as invalid_geometries_{layer_name}.png")

        # Attempt to fix invalid geometries
        def fix_geometry(geom):
            if geom.is_valid:
                return geom
            try:
                valid_geom = make_valid(geom)
                if isinstance(valid_geom, (MultiPolygon, Polygon, LineString, MultiLineString)):
                    return valid_geom
                elif isinstance(valid_geom, GeometryCollection):
                    valid_parts = [g for g in valid_geom.geoms if isinstance(g, (Polygon, MultiPolygon, LineString, MultiLineString))]
                    if valid_parts:
                        return GeometryCollection(valid_parts)
                log_warning(f"Unable to fix geometry: {valid_geom.geom_type}")
                return None
            except Exception as e:
                log_warning(f"Error fixing geometry: {e}")
                return None

        filtered_gdf['geometry'] = filtered_gdf['geometry'].apply(fix_geometry)
        filtered_gdf = filtered_gdf[filtered_gdf['geometry'].notna()]
        log_info(f"Number of valid geometries after fixing: {len(filtered_gdf)}")

        if filtered_gdf.empty:
            log_warning(f"No valid geometries found for layer '{layer_name}'")
            return None

        try:
            union_result = unary_union(filtered_gdf.geometry.tolist())
            log_info(f"Unary union result type for {layer_name}: {type(union_result)}")
            return union_result
        except Exception as e:
            log_error(f"Error performing unary_union on filtered geometries: {e}")
            return None

    def _extract_coords_from_reason(self, reason):
        # Try to extract coordinates using regex
        match = re.search(r'\[([-\d.]+)\s+([-\d.]+)\]', reason)
        if match:
            return float(match.group(1)), float(match.group(2))
        return None

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

            # If no geometries are left after filtering, break early
            if filtered_gdf.empty:
                break

        if not filtered_gdf.empty:
            self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, filtered_gdf)
        else:
            log_warning(f"No geometries left after filtering for layer: {layer_name}")
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def create_difference_layer(self, layer_name, operation):
        log_info(f"Creating difference layer: {layer_name}")
        overlay_layers = operation.get('layers', [])
        
        base_geometry = self.all_layers.get(layer_name)
        if base_geometry is None:
            log_warning(f"Base layer {layer_name} not found for difference operation")
            return None

        overlay_geometry = None
        for layer_info in overlay_layers:
            overlay_layer_name, values = self._process_layer_info(layer_info)
            if overlay_layer_name is None:
                continue

            layer_geometry = self._get_filtered_geometry(overlay_layer_name, values)
            if layer_geometry is None:
                continue

            if overlay_geometry is None:
                overlay_geometry = layer_geometry
            else:
                overlay_geometry = overlay_geometry.union(layer_geometry)

        if base_geometry is not None and overlay_geometry is not None:
            result = self._perform_smart_difference(base_geometry, overlay_geometry)
            
            if result is None or result.is_empty:
                log_warning(f"Difference operation resulted in empty geometry for layer {layer_name}")
                return None
            
            result_gdf = gpd.GeoDataFrame(geometry=[result], crs=self.crs)
            
            if isinstance(base_geometry, gpd.GeoDataFrame):
                for col in base_geometry.columns:
                    if col != 'geometry':
                        result_gdf[col] = base_geometry[col].iloc[0]
            
            return result_gdf
        else:
            log_warning(f"Unable to perform difference operation for layer {layer_name}")
            return None

    def _perform_smart_difference(self, base_geometry, overlay_geometry):
        if isinstance(base_geometry, gpd.GeoDataFrame):
            base_geometry = base_geometry.geometry.unary_union
        
        if isinstance(base_geometry, (Polygon, MultiPolygon)) and isinstance(overlay_geometry, (Polygon, MultiPolygon)):
            # Split multipolygons into individual polygons
            base_polygons = [base_geometry] if isinstance(base_geometry, Polygon) else list(base_geometry.geoms)
            overlay_polygons = [overlay_geometry] if isinstance(overlay_geometry, Polygon) else list(overlay_geometry.geoms)
            
            result_polygons = []
            for base_poly in base_polygons:
                for overlay_poly in overlay_polygons:
                    if base_poly.intersects(overlay_poly):
                        intersection = base_poly.intersection(overlay_poly)
                        if intersection.area / base_poly.area > 0.5:
                            # If more than half of the base polygon is covered, subtract it from the overlay
                            diff = overlay_poly.difference(base_poly)
                        else:
                            # Otherwise, subtract the overlay from the base
                            diff = base_poly.difference(overlay_poly)
                        if not diff.is_empty:
                            result_polygons.append(diff)
                    else:
                        # If they don't intersect, keep the base polygon as is
                        result_polygons.append(base_poly)
            
            # Combine all resulting polygons
            return unary_union(result_polygons)
        else:
            # For non-polygon geometries, perform a simple difference
            return base_geometry.difference(overlay_geometry)

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
        simplify_tolerance = 0.01
        geometry = geometry.simplify(simplify_tolerance, preserve_topology=True)
        
        # Remove thin growths
        thin_growth_threshold = 0.0001  # Adjust this value as needed
        geometry = self._remove_thin_growths(geometry, thin_growth_threshold)
        
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

    def _remove_thin_growths(self, geometry, threshold):
        if isinstance(geometry, (Polygon, MultiPolygon)):
            # Apply a negative buffer followed by a positive buffer
            cleaned = geometry.buffer(-threshold).buffer(threshold)
            
            # Ensure the result is valid and of the same type as the input
            cleaned = make_valid(cleaned)
            if isinstance(geometry, Polygon) and isinstance(cleaned, MultiPolygon):
                # If a Polygon became a MultiPolygon, take the largest part
                largest = max(cleaned.geoms, key=lambda g: g.area)
                return largest
            return cleaned
        elif isinstance(geometry, GeometryCollection):
            cleaned_geoms = [self._remove_thin_growths(geom, threshold) for geom in geometry.geoms]
            return GeometryCollection([g for g in cleaned_geoms if g is not None])
        else:
            # For non-polygon geometries, return as is
            return geometry

    def _clean_polygon(self, polygon, sliver_removal_distance, min_area):
        if polygon.is_empty:
            log_warning("Encountered an empty polygon during cleaning. Skipping.")
            return polygon

        cleaned_exterior = self._clean_linear_ring(polygon.exterior, sliver_removal_distance)
        cleaned_interiors = [self._clean_linear_ring(interior, sliver_removal_distance) for interior in polygon.interiors]

        # Filter out any empty interiors
        cleaned_interiors = [interior for interior in cleaned_interiors if not interior.is_empty]

        try:
            cleaned_polygon = Polygon(cleaned_exterior, cleaned_interiors)
        except Exception as e:
            log_warning(f"Error creating cleaned polygon: {str(e)}. Returning original polygon.")
            return polygon

        if cleaned_polygon.area < min_area:
            log_info(f"Polygon area ({cleaned_polygon.area}) is below minimum ({min_area}). Removing.")
            return None

        return cleaned_polygon

    def _clean_linear_ring(self, ring, sliver_removal_distance):
        if ring.is_empty:
            log_warning("Encountered an empty ring during cleaning. Skipping.")
            return ring

        coords = list(ring.coords)
        if len(coords) < 3:
            log_warning(f"Ring has fewer than 3 coordinates. Skipping cleaning. Coords: {coords}")
            return ring

        line = LineString(coords)
        try:
            merged = linemerge([line])
        except Exception as e:
            log_warning(f"Error during linemerge: {str(e)}. Returning original ring.")
            return ring

        if merged.geom_type == 'LineString':
            cleaned = merged.simplify(sliver_removal_distance)
        else:
            log_warning(f"Unexpected geometry type after merge: {merged.geom_type}. Returning original ring.")
            return ring

        if not cleaned.is_ring:
            log_warning("Cleaned geometry is not a ring. Attempting to close it.")
            cleaned = LineString(list(cleaned.coords) + [cleaned.coords[0]])

        return LinearRing(cleaned)

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
        join_style = operation.get('joinStyle', 'round')

        join_style_map = {'round': 1, 'mitre': 2, 'bevel': 3}
        join_style_value = join_style_map.get(join_style, 1)

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
            if isinstance(combined_geometry, gpd.GeoDataFrame):
                buffered = combined_geometry.geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                buffered = buffered[~buffered.is_empty]  # Remove empty geometries
                if buffered.empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = gpd.GeoDataFrame(geometry=buffered, crs=self.crs)
                
                # Copy attributes from the original geometry
                for col in combined_geometry.columns:
                    if col != 'geometry':
                        result[col] = combined_geometry[col].iloc[0]
            else:
                # Handle individual geometry objects
                buffered = combined_geometry.buffer(buffer_distance, cap_style=2, join_style=join_style_value)
                if buffered.is_empty:
                    log_warning(f"Buffer operation resulted in empty geometry for layer {layer_name}")
                    return None
                result = gpd.GeoDataFrame(geometry=[buffered], crs=self.crs)
            
            return result
        else:
            log_warning(f"No valid geometry found for buffer operation on layer {layer_name}")
            return None

    def process_wmts_or_wms_layer(self, layer_name, operation):
        log_info(f"Processing WMTS/WMS layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        target_folder = self.project_loader.resolve_full_path(operation['targetFolder'])
        zoom_level = operation.get('zoom')
        
        zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}") if zoom_level else target_folder
        
        layer_info = next((l for l in self.project_settings['geomLayers'] if l['name'] == layer_name), None)
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