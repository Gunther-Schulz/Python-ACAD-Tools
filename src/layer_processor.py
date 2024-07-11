import geopandas as gpd
from matplotlib import pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles

class LayerProcessor:
    def __init__(self, project_loader):
        self.project_loader = project_loader
        self.all_layers = {}
        self.project_settings = project_loader.project_settings
        self.crs = project_loader.crs
        self.update_layers_list = None

    def process_layers(self, update_layers_list=None):
        self.update_layers_list = update_layers_list
        log_info("Starting to process layers...")
        
        self.setup_shapefiles()

        processed_layers = set()

        for layer in self.project_settings['dxfLayers']:
            layer_name = layer['name']
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

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
        
        if layer_obj is None:
            log_warning(f"Layer {layer_name} not found in project settings")
            return

        if 'operations' in layer_obj:
            for operation in layer_obj['operations']:
                self.process_operation(layer_name, operation, processed_layers)
        elif 'shapeFile' in layer_obj:
            pass  # Shapefiles are already loaded in setup_shapefiles
        else:
            self.all_layers[layer_name] = None
            log_info(f"Added layer {layer_name} without data")

        if 'shapeFileOutput' in layer_obj:
            self.write_shapefile(layer_name, layer_obj['shapeFileOutput'])

        processed_layers.add(layer_name)


    def process_operation(self, layer_name, operation, processed_layers):
        op_type = operation['type']
        
        # Process dependent layers first
        if 'layers' in operation:
            for dep_layer_name in operation['layers']:
                self.process_layer(dep_layer_name, processed_layers)

        if op_type == 'copy':
            self.create_copy_layer(layer_name, operation)
        elif op_type == 'buffer':
            self.create_buffer_layer(layer_name, operation)
        elif op_type == 'difference':
            self.create_difference_layer(layer_name, operation)
        elif op_type == 'intersection':
            self.create_intersection_layer(layer_name, operation)
        elif op_type == 'filter_by_attributes':
            self.create_filtered_layer(layer_name, operation)
        elif op_type == 'wmts':
            self.process_wmts_layer(layer_name, operation)
        else:
            log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")

        # Ensure the result is stored in all_layers
        if layer_name not in self.all_layers:
            log_warning(f"Operation {op_type} did not produce a result for layer {layer_name}")
        else:
            log_info(f"Layer {layer_name} processed successfully")

    def create_copy_layer(self, layer_name, operation):
        source_layers = operation.get('layers', [])
        if source_layers and source_layers[0] in self.all_layers:
            self.all_layers[layer_name] = self.all_layers[source_layers[0]].copy()
            log_info(f"Copied layer {source_layers[0]} to {layer_name}")
        else:
            log_warning(f"Source layer not found for copy operation on {layer_name}")

    def write_shapefile(self, layer_name, output_path):
        if layer_name in self.all_layers:
            gdf = self.all_layers[layer_name]
            if isinstance(gdf, gpd.GeoDataFrame):
                full_path = self.project_loader.resolve_full_path(output_path)
                gdf.to_file(full_path)
                log_info(f"Shapefile written for layer {layer_name}: {full_path}")
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

    def create_filtered_layer(self, layer_name, operation):  # Renamed from create_geltungsbereich_layer
        log_info(f"Creating filtered layer: {layer_name}")
        combined_geometry = None

        for layer in operation['layers']:
            source_layer_name = layer['name']
            value_list = [str(v) for v in layer['valueList']]  # Ensure all values are strings
            log_info(f"Processing source layer: {source_layer_name}")

            if source_layer_name not in self.all_layers:
                log_warning(f"Source layer '{source_layer_name}' not found for filtering")
                continue

            source_gdf = self.all_layers[source_layer_name]
            
            label_column = next((l['label'] for l in self.project_settings['dxfLayers'] if l['name'] == source_layer_name), None)
            
            if label_column is None or label_column not in source_gdf.columns:
                log_warning(f"Label column '{label_column}' not found in layer '{source_layer_name}'")
                continue
            
            # Convert label column to string and filter
            filtered_gdf = source_gdf[source_gdf[label_column].astype(str).isin(value_list)]

            if filtered_gdf.empty:
                log_warning(f"No matching geometries found for {source_layer_name} with values {value_list}")
                continue

            layer_geometry = filtered_gdf.geometry.unary_union

            if combined_geometry is None:
                combined_geometry = layer_geometry
            else:
                combined_geometry = combined_geometry.intersection(layer_geometry)

        if combined_geometry is not None:
            # Ensure the result is a Polygon or MultiPolygon
            if isinstance(combined_geometry, (Polygon, MultiPolygon)):
                self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, gpd.GeoDataFrame(geometry=[combined_geometry], crs=self.crs))
                log_info(f"Created filtered layer: {layer_name}")
            else:
                log_warning(f"Resulting geometry is not a Polygon or MultiPolygon for layer: {layer_name}")
        else:
            log_warning(f"No geometry created for filtered layer: {layer_name}")

    def create_difference_layer(self, layer_name, operation):
        self._create_overlay_layer(layer_name, operation, 'difference')

    def create_intersection_layer(self, layer_name, operation):
        self._create_overlay_layer(layer_name, operation, 'intersection')

    def _create_overlay_layer(self, layer_name, operation, overlay_type):
        log_info(f"Creating {overlay_type} layer: {layer_name}")
        log_info(f"Operation details: {operation}")
        
        overlay_layers = operation.get('layers', [])
        
        log_info(f"Overlay layers: {overlay_layers}")
        
        if not overlay_layers:
            log_warning(f"No overlay layers specified for {layer_name}")
            return
        
        base_geometry = self.all_layers.get(layer_name)
        if base_geometry is None:
            log_warning(f"Base layer '{layer_name}' not found for {overlay_type} operation")
            return
        
        log_info(f"Base geometry type: {type(base_geometry)}")
        log_info(f"Base geometry CRS: {base_geometry.crs if hasattr(base_geometry, 'crs') else 'N/A'}")

        combined_overlay_geometry = None
        for overlay_layer in overlay_layers:
            if overlay_layer in self.all_layers:
                overlay_geometry = self.all_layers[overlay_layer]
                if isinstance(overlay_geometry, gpd.GeoDataFrame):
                    overlay_geometry = overlay_geometry.geometry.unary_union
                if combined_overlay_geometry is None:
                    combined_overlay_geometry = overlay_geometry
                else:
                    combined_overlay_geometry = combined_overlay_geometry.union(overlay_geometry)
                log_info(f"Added overlay geometry from layer: {overlay_layer}")
            else:
                log_warning(f"Overlay layer '{overlay_layer}' not found for layer '{layer_name}'")

        if combined_overlay_geometry is None:
            log_warning(f"No valid overlay geometries found for layer '{layer_name}'")
            return

        try:
            if overlay_type == 'difference':
                result_geometry = base_geometry.geometry.difference(combined_overlay_geometry)
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
            log_info(f"Final geometry type: {type(self.all_layers[layer_name])}")
            log_info(f"Final geometry CRS: {self.all_layers[layer_name].crs}")
        else:
            log_warning(f"No valid geometry created for {overlay_type} layer: {layer_name}")

        # Plot and show (optional, for debugging)
        self.all_layers[layer_name].plot()
        plt.title(f"Layer: {layer_name}")
        plt.show()
            
    def create_buffer_layer(self, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layers = operation.get('layers', [])
        buffer_distance = operation['distance']
        buffer_mode = operation.get('mode', 'both')

        if not source_layers:
            log_warning(f"No source layers specified for buffer layer '{layer_name}'")
            return

        original_geometry = None
        for source_layer in source_layers:
            if source_layer in self.all_layers:
                if original_geometry is None:
                    original_geometry = self.all_layers[source_layer]
                else:
                    original_geometry = original_geometry.overlay(self.all_layers[source_layer], how='union')
            else:
                log_warning(f"Source layer '{source_layer}' not found for buffer layer '{layer_name}'")

        if original_geometry is not None:
            if buffer_mode == 'outer':
                buffered = original_geometry.buffer(buffer_distance, join_style=2)
                result = buffered.difference(original_geometry)
            elif buffer_mode == 'inner':
                result = original_geometry.buffer(-buffer_distance, join_style=2)
            else:  # 'both'
                result = original_geometry.buffer(buffer_distance, join_style=2)

            self.all_layers[layer_name] = self.ensure_geodataframe(layer_name, result)
            log_info(f"Created buffer layer: {layer_name}")
        else:
            log_warning(f"No valid source geometry found for buffer layer '{layer_name}'")

    def process_wmts_layer(self, layer_name, operation):
        log_info(f"Processing WMTS layer: {layer_name}")
        
        target_folder = self.project_loader.resolve_full_path(operation['targetFolder'])
        zoom_level = operation['zoom']
        
        # Create a zoom-specific folder
        zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}")
        
        # Check if the zoom folder already exists
        if os.path.exists(zoom_folder):
            log_info(f"Zoom folder already exists: {zoom_folder}. Using existing tiles.")
            existing_tiles = self.get_existing_tiles(zoom_folder)
            self.all_layers[layer_name] = existing_tiles
            return

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