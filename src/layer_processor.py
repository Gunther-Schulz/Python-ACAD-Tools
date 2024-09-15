import geopandas as gpd
from matplotlib import pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint, GeometryCollection
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles
from shapely.ops import unary_union
import shutil
from src.contour_processor import process_contour

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
        recognized_keys = {'name', 'update', 'operations', 'shapeFile', 'outputShapeFile', 'style', 'label', 'close'}
        unrecognized_keys = set(layer_obj.keys()) - recognized_keys
        if unrecognized_keys:
            log_warning(f"Unrecognized keys in layer {layer_name}: {', '.join(unrecognized_keys)}")

        # Check for known style keys
        known_style_keys = {'color', 'labelColor', 'linetype', 'lineweight', 'plot', 'locked', 'frozen', 'is_on', 'vp_freeze', 'transparency'}
        if 'style' in layer_obj:
            unknown_style_keys = set(layer_obj['style'].keys()) - known_style_keys
            if unknown_style_keys:
                log_warning(f"Unknown style keys in layer {layer_name}: {', '.join(unknown_style_keys)}")

        # Check if the layer should be updated
        update_flag = layer_obj.get('update', False)  # Default to False
        log_info(f"Update flag for layer {layer_name}: {update_flag}")
        if not update_flag and layer_name in self.all_layers:
            log_info(f"Skipping update for layer {layer_name} as update is set to false")
            return

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
        else:
            self.all_layers[layer_name] = None
            log_info(f"Added layer {layer_name} without data")

        # # Only write the output shape if update_flag is True
        # if update_flag and 'outputShapeFile' in layer_obj:
        #     self.write_shapefile(layer_name, layer_obj['outputShapeFile'])

        if 'outputShapeFile' in layer_obj:
            self.write_shapefile(layer_name, layer_obj['outputShapeFile'])


        processed_layers.add(layer_name)

    def process_operation(self, layer_name, operation, processed_layers):
        op_type = operation['type']
        
        log_info(f"Processing operation for layer {layer_name}: {op_type}")
        log_info(f"Operation details: {operation}")
        
        # Check if the layer should be updated
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
        update_flag = layer_info.get('update', False) if layer_info else False
        log_info(f"Update flag for layer {layer_name}: {update_flag}")
        
        if not update_flag and layer_name in self.all_layers:
            log_info(f"Skipping update for layer {layer_name} as update is set to false")
            return
        
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
        elif op_type == 'wmts':
            result = self.process_wmts_layer(layer_name, operation)
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
            if isinstance(gdf, gpd.GeoDataFrame):
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
                if 'shapeFile' in layer:
                    layer_name = layer['name']
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
                result_geometry = result_geometry.buffer(-1, join_style=2).buffer(1, join_style=2)
            elif overlay_type == 'intersection':
                result_geometry = base_geometry.geometry.intersection(combined_overlay_geometry)
            
            log_info(f"Applied {overlay_type} operation")
        except Exception as e:
            log_error(f"Error during {overlay_type} operation: {str(e)}")
            return

        if result_geometry is not None:
            result_gdf = gpd.GeoDataFrame(geometry=result_geometry, crs=base_geometry.crs)
            self.all_layers[layer_name] = result_gdf
            log_info(f"Created {overlay_type} layer: {layer_name}")
        else:
            log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")
            
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

    def process_wmts_layer(self, layer_name, operation):
        log_info(f"Processing WMTS layer: {layer_name}")
        
        target_folder = self.project_loader.resolve_full_path(operation['targetFolder'])
        zoom_level = operation['zoom']
        
        # Create a zoom-specific folder
        zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}")
        
        # Check if the layer should be updated
        layer_info = next((l for l in self.project_settings['dxfLayers'] if l['name'] == layer_name), None)
        update_flag = layer_info.get('update', False) if layer_info else False
        
        if update_flag or not os.path.exists(zoom_folder):
            # If update is true or the folder doesn't exist, proceed with downloading
            if os.path.exists(zoom_folder):
                shutil.rmtree(zoom_folder)  # Remove existing folder if updating
            os.makedirs(zoom_folder, exist_ok=True)
            
            log_info(f"Target folder path: {zoom_folder}")

            wmts_layers = operation.get('layers', [])
            buffer_distance = operation.get('buffer', 100)
            wmts_info = {
                'url': operation['url'],
                'layer': operation['layer'],
                'zoom': zoom_level,
                'proj': operation['proj'],
                'format': operation.get('format', 'image/png'),
                'sleep': operation.get('sleep', 0),
                'limit': operation.get('limit', 0)
            }

            log_info(f"WMTS info: {wmts_info}")
            log_info(f"Layers to process: {wmts_layers}")

            all_tiles = []
            for layer in wmts_layers:
                if layer in self.all_layers:
                    layer_geometry = self.all_layers[layer]
                    if isinstance(layer_geometry, gpd.GeoDataFrame):
                        layer_geometry = layer_geometry.geometry.unary_union

                    log_info(f"Downloading tiles for layer: {layer}")
                    log_info(f"Layer geometry type: {type(layer_geometry)}")
                    log_info(f"Layer geometry bounds: {layer_geometry.bounds}")

                    downloaded_tiles = download_wmts_tiles(wmts_info, layer_geometry, buffer_distance, zoom_folder)
                    all_tiles.extend(downloaded_tiles)
                else:
                    log_warning(f"Layer {layer} not found for WMTS download of {layer_name}")

            self.all_layers[layer_name] = all_tiles
            log_info(f"Total tiles for {layer_name}: {len(all_tiles)}")
        else:
            log_info(f"Zoom folder already exists and update is not required: {zoom_folder}. Using existing tiles.")
            existing_tiles = self.get_existing_tiles(zoom_folder)
            self.all_layers[layer_name] = existing_tiles

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
