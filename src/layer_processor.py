import geopandas as gpd
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

        for layer in self.project_settings['dxfLayers']:
            layer_name = layer['name']
            if self.update_layers_list and layer_name not in self.update_layers_list:
                continue

            log_info(f"Processing layer: {layer_name}")
            if 'operations' in layer:
                for operation in layer['operations']:
                    self.process_operation(layer_name, operation)

            elif 'shapeFile' in layer:
                pass
            else:
                self.all_layers[layer_name] = None
                log_info(f"Added layer {layer_name} without data")

            if 'shapeFileOutput' in layer:
                self.write_shapefile(layer_name, layer['shapeFileOutput'])

        log_info("Finished processing layers.")

    def process_operation(self, layer_name, operation):
        op_type = operation['type']

        if op_type == 'buffer':
            self.create_buffer_layer(layer_name, operation)
        elif op_type == 'clip':
            self.create_clip_distance_layer(layer_name, operation)
        elif op_type == 'geltungsbereich':
            self.create_geltungsbereich_layer(layer_name, operation)
        elif op_type == 'exclusion':
            self.create_exclusion_layer(layer_name, operation)
        elif op_type == 'wmts':
            self.process_wmts_layer(layer_name, operation)
        else:
            log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")

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

    def create_geltungsbereich_layer(self, layer_name, operation):
        log_info(f"Creating Geltungsbereich layer: {layer_name}")
        combined_geometry = None

        for layer in operation['layers']:
            source_layer_name = layer['name']
            value_list = [str(v) for v in layer['valueList']]  # Ensure all values are strings
            log_info(f"Processing source layer: {source_layer_name}")

            if source_layer_name not in self.all_layers:
                log_warning(f"Source layer '{source_layer_name}' not found for Geltungsbereich")
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

            if combined_geometry is None:
                combined_geometry = filtered_gdf.geometry.unary_union
            else:
                combined_geometry = combined_geometry.intersection(filtered_gdf.geometry.unary_union)

        if combined_geometry:
            if 'clipToLayers' in operation:
                for clip_layer_name in operation['clipToLayers']:
                    if clip_layer_name in self.all_layers:
                        clip_geometry = self.all_layers[clip_layer_name].geometry.unary_union
                        combined_geometry = combined_geometry.difference(clip_geometry)
                        log_info(f"Applied clipping with layer: {clip_layer_name}")
                    else:
                        log_warning(f"Clip layer '{clip_layer_name}' not found for Geltungsbereich")

            # Ensure the result is a Polygon or MultiPolygon
            if isinstance(combined_geometry, (Polygon, MultiPolygon)):
                self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[combined_geometry], crs=self.crs)
            else:
                log_warning(f"Resulting geometry is not a Polygon or MultiPolygon for layer: {layer_name}")
        else:
            log_warning(f"No geometry created for Geltungsbereich layer: {layer_name}")



    def create_clip_distance_layer(self, layer_name, operation):
        log_info(f"Creating clip distance layer: {layer_name}")
        buffer_distance = operation['distance']
        source_layer = operation['sourceLayer']
        if source_layer in self.all_layers:
            original_geometry = self.all_layers[source_layer]
            if buffer_distance > 0:
                clipped = original_geometry.buffer(buffer_distance, join_style=2)
            else:
                clipped = original_geometry
            self.all_layers[layer_name] = clipped
            log_info(f"Created clip distance layer: {layer_name}")
        else:
            log_warning(f"Warning: Source layer '{source_layer}' not found in all_layers for clip distance layer '{layer_name}'")
            
    def create_buffer_layer(self, layer_name, operation):
        log_info(f"Creating buffer layer: {layer_name}")
        source_layer = operation['sourceLayer']
        buffer_distance = operation['distance']
        buffer_mode = operation.get('mode', 'both')
        clip_to_layers = operation.get('clipToLayers', [])

        if source_layer in self.all_layers:
            original_geometry = self.all_layers[source_layer]
            
            if buffer_mode == 'outer':
                buffered = original_geometry.buffer(buffer_distance, join_style=2)
                result = buffered.difference(original_geometry)
            elif buffer_mode == 'inner':
                result = original_geometry.buffer(-buffer_distance, join_style=2)
            else:  # 'both'
                result = original_geometry.buffer(buffer_distance, join_style=2)

            # Clip the buffer to the specified layers
            if clip_to_layers:
                clip_geometry = None
                for clip_layer in clip_to_layers:
                    if clip_layer in self.all_layers:
                        if clip_geometry is None:
                            clip_geometry = self.all_layers[clip_layer]
                        else:
                            clip_geometry = clip_geometry.union(self.all_layers[clip_layer])
                    else:
                        log_warning(f"Warning: Clip layer '{clip_layer}' not found for buffer layer '{layer_name}'")
                
                if clip_geometry is not None:
                    result = result.intersection(clip_geometry)

            self.all_layers[layer_name] = result
            log_info(f"Created buffer layer: {layer_name}")
        else:
            log_warning(f"Warning: Source layer '{source_layer}' not found for buffer layer '{layer_name}'")

    def create_exclusion_layer(self, layer_name, operation):
        log_info(f"Creating exclusion layer: {layer_name}")
        scope_layer = operation['scopeLayer']
        exclude_layers = operation['excludeLayers']

        log_info(f"  Scope layer: {scope_layer}")
        log_info(f"  Exclude layers: {exclude_layers}")

        if scope_layer in self.all_layers:
            scope_geometry = self.all_layers[scope_layer]
            excluded_geometry = scope_geometry

            for exclude_layer in exclude_layers:
                if exclude_layer in self.all_layers:
                    log_info(f"  Excluding {exclude_layer}")
                    excluded_geometry = excluded_geometry.difference(self.all_layers[exclude_layer])
                else:
                    log_warning(f"Warning: Exclude layer '{exclude_layer}' not found for exclusion layer '{layer_name}'")

            self.all_layers[layer_name] = excluded_geometry
            log_info(f"Created exclusion layer: {layer_name}")
        else:
            log_warning(f"Warning: Scope layer '{scope_layer}' not found for exclusion layer '{layer_name}'")

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