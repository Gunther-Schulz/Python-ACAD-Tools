import os
import shutil
import traceback

import ezdxf
import fiona
import geopandas as gpd
from geopandas import GeoSeries
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point

from src.dxf_utils import read_cad_layer_to_geodataframe
from src.operations.registry import get_operation
from src.project_loader import ProjectLoader
from src.shapefile_utils import write_shapefile
from src.style_manager import StyleManager
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug

class LayerProcessor:
    def __init__(self, project_loader, plot_ops=False):
        self.project_loader = project_loader
        self.project_settings = project_loader.project_settings
        self.crs = project_loader.crs
        self.all_layers = {}
        self.plot_ops = plot_ops
        self.style_manager = StyleManager(project_loader)
        self.processed_layers = set()
        self.dxf_doc = None
        self.pending_dxf_layers = []
        self._external_dxf_cache = {}  # Cache for external DXF documents

    def set_dxf_document(self, doc):
        """Set the DXF document from DXFExporter and process any pending layers"""
        self.dxf_doc = doc
        log_debug("DXF document reference set in LayerProcessor")

    def process_layers(self):
        log_debug("Starting to process layers...")

        self.setup_shapefiles()

        shapefile_output_dir = self.project_loader.shapefile_output_dir

        # Process geometric layers
        for layer in self.project_settings['geomLayers']:
            if not layer.get('enabled', True):
                log_debug(f"Skipping disabled layer: {layer['name']}")
                continue
            layer_name = layer['name']
            self.process_layer(layer, self.processed_layers)
            if shapefile_output_dir:
                self.write_shapefile(layer_name)

        # Save generated label layers (mirror DXF behavior)
        if shapefile_output_dir:
            for layer in self.project_settings['geomLayers']:
                layer_name = layer['name']
                label_layer_name = f"{layer_name}_labels"
                if label_layer_name in self.all_layers:
                    log_debug(f"Saving generated label layer: {label_layer_name}")
                    self.write_shapefile(label_layer_name)

        # Log completion of shapefile generation
        if shapefile_output_dir:
            log_info("Finished writing generated shape files")

        # Process WMTS layers
        for layer in self.project_settings.get('wmtsLayers', []):
            layer_name = layer['name']
            layer['type'] = 'wmts'  # Ensure type is set
            self.process_layer(layer, self.processed_layers)

        # Process WMS layers
        for layer in self.project_settings.get('wmsLayers', []):
            layer_name = layer['name']
            layer['type'] = 'wms'  # Ensure type is set
            self.process_layer(layer, self.processed_layers)

        # Delete residual shapefiles
        self.delete_residual_shapefiles()

        log_debug("Finished processing layers.")

    def process_layer(self, layer, processed_layers, processing_stack=None):
        """
        Process a single layer with sync mode awareness.
        Supports sync modes: skip (default), push, pull
        """
        if processing_stack is None:
            processing_stack = []

        # Handle both layer objects and layer references
        if isinstance(layer, str):
            layer_name = layer
            # Find the actual layer configuration
            layer_obj = None
            for l in self.project_settings['geomLayers']:
                if l['name'] == layer_name:
                    layer_obj = l
                    break
            if layer_obj is None:
                log_warning(f"Layer '{layer_name}' not found in geomLayers configuration")
                return
            if not layer_obj.get('enabled', True):
                log_debug(f"Skipping disabled layer: {layer_name}")
                return
        else:
            layer_name = layer['name']
            layer_obj = layer

        # Check for cycles
        if layer_name in processing_stack:
            cycle = ' -> '.join(processing_stack + [layer_name])
            log_error(f"Circular dependency detected: {cycle}")
            return

        # If already processed, skip
        if layer_name in processed_layers:
            return

        processing_stack.append(layer_name)

        try:
            # Get sync mode (default is 'skip' for backward compatibility)
            sync_mode = layer_obj.get('sync', 'skip')
            log_debug(f"Processing layer '{layer_name}' with sync mode: {sync_mode}")

            # Handle pull mode: read from CAD layer first
            if sync_mode == 'pull':
                self._handle_pull_mode(layer_obj, layer_name)

            # Process layer operations (works for all sync modes)
            self._process_layer_operations(layer_obj, layer_name, processed_layers, processing_stack)

            # Mark as processed
            processed_layers.add(layer_name)
            log_debug(f"Layer {layer_name} processed successfully")

        except Exception as e:
            log_error(f"Error processing layer {layer_name}: {str(e)}")
            raise

        finally:
            processing_stack.remove(layer_name)

    def _handle_pull_mode(self, layer_obj, layer_name):
        """
        Handle pull mode: read geometry from CAD layer.
        Supports filtering by entity types if specified in layer configuration.
        """
        log_debug(f"Pull mode: Reading CAD layer '{layer_name}'")

        if self.dxf_doc is None:
            log_warning(f"No DXF document available for pull mode on layer '{layer_name}'")
            return

        try:
            # Get entity type filter from layer configuration
            entity_types = layer_obj.get('entityTypes', None)

            # Read geometry from the CAD layer
            cad_geometry = read_cad_layer_to_geodataframe(
                self.dxf_doc,
                layer_name,
                self.crs,
                entity_types=entity_types
            )

            if cad_geometry.empty:
                log_warning(f"No geometry found in CAD layer '{layer_name}' for pull mode")
                self.all_layers[layer_name] = cad_geometry
            else:
                self.all_layers[layer_name] = cad_geometry
                log_debug(f"Successfully read {len(cad_geometry)} geometries from CAD layer '{layer_name}'")

        except Exception as e:
            log_error(f"Error reading CAD layer '{layer_name}' in pull mode: {str(e)}")
            # Create empty GeoDataFrame as fallback
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def _load_dxf_source(self, layer_name, dxf_source_config):
        """Load geometry from an external DXF file."""
        try:
            dxf_file = dxf_source_config.get('file')
            source_layer = dxf_source_config.get('layer')
            entity_types = dxf_source_config.get('entityTypes', None)
            preprocessors = dxf_source_config.get('preprocessors', [])

            if not dxf_file or not source_layer:
                log_error(f"dxfSource for layer '{layer_name}' requires 'file' and 'layer' keys")
                self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)
                return

            # Load and cache the DXF document
            doc = self._get_external_dxf(dxf_file, layer_name)
            if doc is None:
                return

            if source_layer not in doc.layers:
                log_warning(f"Layer '{source_layer}' not found in DXF file: {dxf_file}")
                self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)
                return

            # Query, preprocess, and filter entities
            entities = self._query_dxf_entities(doc, source_layer, entity_types, preprocessors)

            # Convert to GeoDataFrame
            gdf = self._entities_to_geodataframe(entities, source_layer, dxf_file, layer_name)
            self.all_layers[layer_name] = gdf

        except Exception as e:
            log_error(f"Error loading DXF source for layer '{layer_name}': {str(e)}")
            log_error(traceback.format_exc())
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def _get_external_dxf(self, dxf_file, layer_name):
        """Load and cache an external DXF document."""
        full_path = resolve_path(dxf_file, self.project_loader.folder_prefix)
        if not os.path.exists(full_path):
            log_error(f"DXF file not found for layer '{layer_name}': {full_path}")
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)
            return None

        if full_path not in self._external_dxf_cache:
            log_debug(f"Opening external DXF file: {full_path}")
            self._external_dxf_cache[full_path] = ezdxf.readfile(full_path)
        return self._external_dxf_cache[full_path]

    def _query_dxf_entities(self, doc, source_layer, entity_types, preprocessors):
        """Query entities from DXF, apply preprocessors and entity type filtering."""
        from src.preprocessors.block_exploder import explode_blocks
        from src.preprocessors.circle_extractor import extract_circle_centers
        from src.preprocessors.basepoint_extractor import extract_entity_basepoints

        msp = doc.modelspace()

        # Query — use broad query if preprocessors will transform entities
        if preprocessors or not entity_types or len(entity_types) != 1:
            query = f'*[layer=="{source_layer}"]'
        else:
            query = f'{entity_types[0]}[layer=="{source_layer}"]'

        entities = list(msp.query(query))

        # Filter by type before preprocessing (only if no preprocessors)
        if entity_types and not preprocessors and len(entity_types) > 1:
            entities = [e for e in entities if e.dxftype() in entity_types]

        log_debug(f"Found {len(entities)} entities in layer '{source_layer}'")

        # Apply preprocessors
        preprocessor_map = {
            'block_exploder': explode_blocks,
            'circle_extractor': extract_circle_centers,
            'basepoint_extractor': extract_entity_basepoints,
        }
        for pp_config in preprocessors:
            if isinstance(pp_config, str):
                pp_name, pp_opts = pp_config, {}
            elif isinstance(pp_config, dict):
                pp_name = pp_config.get('name')
                pp_opts = {k: v for k, v in pp_config.items() if k != 'name'}
            else:
                log_warning(f"Invalid preprocessor configuration: {pp_config}")
                continue
            pp_func = preprocessor_map.get(pp_name)
            if pp_func:
                entities = pp_func(entities, source_layer, **pp_opts)
                log_debug(f"After {pp_name}: {len(entities)} entities")
            else:
                log_warning(f"Unknown preprocessor: {pp_name}")

        # Filter by type after preprocessing
        if entity_types and preprocessors:
            entities = [e for e in entities if e.dxftype() in entity_types]

        return entities

    def _entities_to_geodataframe(self, entities, source_layer, dxf_file, layer_name):
        """Convert DXF entities (or preprocessed dicts) to a GeoDataFrame."""
        from src.dump_to_shape import convert_entity_to_geometry

        geometries = []
        for entity_data in entities:
            if isinstance(entity_data, dict):
                if 'coords' in entity_data:
                    geom = Point(entity_data['coords'])
                    if geom.is_valid and not geom.is_empty:
                        geometries.append(geom)
            else:
                geom = convert_entity_to_geometry(entity_data)
                if geom is not None:
                    geometries.append(geom)

        if geometries:
            gdf = gpd.GeoDataFrame(geometry=geometries, crs=self.crs)
            log_info(f"Loaded {len(gdf)} geometries from external DXF layer '{source_layer}' into '{layer_name}'")
        else:
            log_warning(f"No geometry found in layer '{source_layer}' from {dxf_file}")
            gdf = gpd.GeoDataFrame(geometry=[], crs=self.crs)
        return gdf

    def _process_layer_operations(self, layer_obj, layer_name, processed_layers, processing_stack):
        """
        Process layer operations (extracted from original process_layer logic).
        Works for all sync modes.
        """
        # Check for unrecognized keys
        recognized_keys = {'name', 'sync', 'operations', 'shapeFile', 'dxfSource', 'type', 'sourceLayer',
                          'outputShapeFile', 'style', 'close', 'linetypeScale', 'linetypeGeneration',
                          'viewports', 'attributes', 'bluntAngles', 'label', 'applyHatch', 'plot',
                          'saveToLagefaktor', 'entityTypes', 'preprocessors', 'enabled', 'hatch'}
        unrecognized_keys = set(layer_obj.keys()) - recognized_keys
        if unrecognized_keys:
            log_warning(f"Unrecognized keys in layer {layer_name}: {', '.join(unrecognized_keys)}")

        # Process style
        if 'style' in layer_obj:
            style, warning_generated = self.style_manager.get_style(layer_obj['style'])
            if warning_generated:
                log_warning(f"Issue with style for layer '{layer_name}'")
            if style is not None:
                layer_obj['style'] = style

        # Process operations
        if 'operations' in layer_obj:
            result_geometry = None
            for operation in layer_obj['operations']:
                if layer_obj.get('type') in ['wmts', 'wms']:
                    operation['type'] = layer_obj['type']
                result_geometry = self.process_operation(layer_name, operation, processed_layers, processing_stack)
            if result_geometry is not None:
                self.all_layers[layer_name] = result_geometry
        elif 'shapeFile' in layer_obj:
            if layer_name not in self.all_layers:
                log_warning(f"Shapefile for layer {layer_name} was not loaded properly")
        elif 'dxfSource' in layer_obj:
            if layer_name not in self.all_layers:
                log_warning(f"DXF source for layer {layer_name} was not loaded properly")
        else:
            # Only set to None if not already set (e.g., by pull mode)
            if layer_name not in self.all_layers:
                self.all_layers[layer_name] = None
                log_debug(f"Added layer {layer_name} without data")

        if 'outputShapeFile' in layer_obj:
            self.write_shapefile(layer_name)

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
            blunt_op = {'type': 'bluntAngles', 'layers': [layer_name], **blunt_config}
            op_info = get_operation('bluntAngles')
            if op_info:
                r = op_info.handler(self.all_layers, self.project_settings, self.crs, layer_name, blunt_op)
                if r is not None:
                    self.all_layers[layer_name] = r

        if 'filterGeometry' in layer_obj:
            filter_config = layer_obj['filterGeometry']
            from src.operations.filter_geometry_operation import create_filtered_geometry_layer
            filtered_layer = create_filtered_geometry_layer(self.all_layers, self.project_settings, self.crs, layer_name, filter_config)
            if filtered_layer is not None:
                self.all_layers[layer_name] = filtered_layer
            log_debug(f"Applied geometry filter to layer '{layer_name}'")

    def process_operation(self, layer_name, operation, processed_layers, processing_stack):
        """Process an operation for a layer."""
        op_type = operation['type']

        log_debug(f"Processing operation for layer {layer_name}: {op_type}")
        log_debug(f"Operation details: {operation}")

        # Process sub-operations first if they exist
        if 'operations' in operation:
            for sub_op in operation['operations']:
                # Create a temporary layer for sub-operation results
                temp_layer_name = f"{layer_name}_temp_{op_type}"
                self.process_operation(temp_layer_name, sub_op, processed_layers, processing_stack)
                # Add the result to the operation's layers
                if 'layers' not in operation:
                    operation['layers'] = []
                operation['layers'].append(temp_layer_name)

        # Process dependent layers if specified
        if 'layers' in operation:
            for dep_layer_info in operation['layers']:
                dep_layer_name = dep_layer_info['name'] if isinstance(dep_layer_info, dict) else dep_layer_info
                log_debug(f"Processing dependent layer: {dep_layer_name}")
                self.process_layer(dep_layer_name, processed_layers, processing_stack)
        else:
            # If neither 'layers' nor 'operations' keys exist, use the current layer
            operation['layers'] = [layer_name]

        # Perform the operation via registry
        op_info = get_operation(op_type)
        if op_info is None:
            log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            return None

        if op_info.needs_project_loader:
            result = op_info.handler(self.all_layers, self.project_settings,
                                     self.crs, layer_name, operation,
                                     self.project_loader)
        else:
            result = op_info.handler(self.all_layers, self.project_settings,
                                     self.crs, layer_name, operation)

        # Handle operations that create separate layers (e.g., simpleLabel, pointLabel)
        if op_info.creates_separate_layer:
            sep_layer_name = f"{layer_name}{op_info.separate_layer_suffix}"
            if result is not None:
                self.all_layers[sep_layer_name] = result
                log_debug(f"Created separate layer '{sep_layer_name}' for '{layer_name}'")
            return None

        # Auto-repair after boolean operations
        auto_repair_ops = {'difference', 'intersection', 'dissolve'}
        if result is not None and op_type in auto_repair_ops and operation.get('autoRepair', True):
            auto_repair_config = self.project_settings.get('autoRepair')
            if auto_repair_config:
                self.all_layers[layer_name] = result
                result = self._apply_auto_repair(layer_name, auto_repair_config)

        if result is not None:
            self.all_layers[layer_name] = result

        # Clean up temporary layers
        if 'operations' in operation:
            for temp_layer in [l for l in self.all_layers.keys() if l.startswith(f"{layer_name}_temp_")]:
                del self.all_layers[temp_layer]

        return result

    def _apply_auto_repair(self, layer_name, auto_repair_config):
        """Apply auto-repair operations after boolean ops using project-level settings."""

        result = self.all_layers.get(layer_name)
        if result is None:
            return None

        log_debug(f"Applying auto-repair to layer '{layer_name}'")

        for op_type in ('removeDegenerateSpikes', 'removeProtrusions', 'removeSliversErosion', 'repair'):
            if op_type in auto_repair_config:
                op_info = get_operation(op_type)
                if op_info is None:
                    continue
                repair_op = {'type': op_type, 'layers': [layer_name],
                             **auto_repair_config[op_type]}
                r = op_info.handler(self.all_layers, self.project_settings, self.crs, layer_name, repair_op)
                if r is not None:
                    self.all_layers[layer_name] = r
                    result = r

        return result

    def setup_shapefiles(self):
        for layer in self.project_settings['geomLayers']:
            layer_name = layer['name']

            # Then load the shapefile (whether it was just updated or not)
            if 'shapeFile' in layer:
                shapefile_path = resolve_path(layer['shapeFile'], self.project_loader.folder_prefix)
                try:
                    if not os.path.exists(shapefile_path):
                        log_warning(f"Shapefile not found for layer '{layer_name}' at path: {shapefile_path}")
                        continue

                    # Add debug info about the shapefile being loaded
                    log_debug(f"Loading shapefile for layer '{layer_name}' from path: {shapefile_path}")

                    # Try to get field info directly using fiona
                    try:
                        with fiona.open(shapefile_path, 'r') as src:
                            schema = src.schema
                            fields = schema['properties'].keys()
                            log_debug(f"Shapefile '{layer_name}' fields according to fiona: {list(fields)}")
                    except Exception as e:
                        log_warning(f"Failed to read shapefile fields using fiona: {str(e)}")

                    # Load the GeoDataFrame
                    gdf = gpd.read_file(shapefile_path)

                    # Debug info about the loaded GeoDataFrame
                    log_debug(f"Loaded shapefile '{layer_name}': {len(gdf)} features, columns: {list(gdf.columns)}")
                    log_debug(f"Column dtypes for '{layer_name}': {gdf.dtypes.to_dict()}")

                    # Make sure any label column in the configuration exists
                    if 'label' in layer:
                        label_col = layer['label']
                        if label_col not in gdf.columns:
                            similar_cols = [col for col in gdf.columns if col.lower() == label_col.lower()]
                            if similar_cols:
                                log_debug(f"Label column '{label_col}' not found exactly, but found similar: {similar_cols}")
                            else:
                                log_warning(f"Label column '{label_col}' specified in config not found in shapefile")
                                log_debug(f"Available columns are: {list(gdf.columns)}")

                    self._validate_loaded_geometries(gdf, layer_name, layer)
                    gdf = self.standardize_layer_crs(layer_name, gdf)
                    if gdf is not None:
                        self.all_layers[layer_name] = gdf
                        log_debug(f"Loaded shapefile for layer: {layer_name}")
                    else:
                        log_warning(f"Failed to load shapefile for layer: {layer_name}")
                except fiona.errors.DriverError as e:
                    log_warning(f"Shapefile not found or inaccessible for layer '{layer_name}' at path: {shapefile_path}")
                    log_warning(f"Error details: {str(e)}")
                except Exception as e:
                    log_error(f"Failed to load shapefile for layer '{layer_name}': {str(e)}")
                    log_error(traceback.format_exc())
            
            # Load from external DXF file if dxfSource is specified
            elif 'dxfSource' in layer:
                log_debug(f"Loading layer '{layer_name}' from external DXF source")
                self._load_dxf_source(layer_name, layer['dxfSource'])

        # After loading all layers, log the contents of all_layers
        for layer_name, gdf in self.all_layers.items():
            if isinstance(gdf, gpd.GeoDataFrame):
                log_debug(f"Layer {layer_name} in all_layers: CRS={gdf.crs}, Geometry type={gdf.geometry.type.unique()}, Number of features={len(gdf)}")
            else:
                log_warning(f"Layer {layer_name} in all_layers is not a GeoDataFrame: {type(gdf)}")

    def write_shapefile(self, layer_name):
        """Write a layer to shapefile. Returns True if successful, False otherwise."""
        log_debug(f"Attempting to write shapefile for layer {layer_name}")

        # Skip hatch layers
        layer_info = next((layer for layer in self.project_settings.get('geomLayers', [])
                          if layer.get('name') == layer_name), None)
        if layer_info and 'applyHatch' in layer_info:
            log_debug(f"Skipping export of hatch layer: {layer_name}")
            return True

        if layer_name not in self.all_layers:
            log_warning(f"Cannot write shapefile for layer {layer_name}: layer not found")
            return False

        gdf = self.all_layers[layer_name]
        if gdf is None:
            log_warning(f"Cannot write shapefile for layer {layer_name}: layer data is None")
            return False

        if not isinstance(gdf, gpd.GeoDataFrame):
            log_warning(f"Cannot write shapefile for layer {layer_name}: data is not a GeoDataFrame (type: {type(gdf)})")
            return False

        success = True

        # Write to default output directory
        if self.project_loader.shapefile_output_dir:
            output_dir = resolve_path(self.project_loader.shapefile_output_dir)
            output_path = os.path.join(output_dir, f"{layer_name}.shp")
            success &= write_shapefile(gdf, output_path)

        # Write to Lagefaktor directory if specified
        if layer_info and 'saveToLagefaktor' in layer_info:
            base_dir = resolve_path(layer_info['saveToLagefaktor'], self.project_loader.folder_prefix)
            if os.path.exists(base_dir):
                # Create layer-specific directory path
                layer_dir = os.path.join(base_dir, layer_name)

                # Remove existing layer directory and its contents if it exists
                if os.path.exists(layer_dir):
                    try:
                        shutil.rmtree(layer_dir)
                        log_debug(f"Removed existing directory: {layer_dir}")
                    except Exception as e:
                        log_warning(f"Failed to remove directory {layer_dir}. Reason: {e}")
                        success = False

                # Create new layer directory
                try:
                    os.makedirs(layer_dir)
                    log_debug(f"Created directory: {layer_dir}")

                    # Write shapefile to the layer directory
                    output_path = os.path.join(layer_dir, f"{layer_name}.shp")
                    success &= write_shapefile(gdf, output_path)
                    log_debug(f"Wrote shapefile to Lagefaktor directory: {output_path}")
                except Exception as e:
                    log_warning(f"Failed to create directory or write shapefile at {layer_dir}. Reason: {e}")
                    success = False
            else:
                log_warning(f"Lagefaktor base directory does not exist: {base_dir}")
                success = False

        if success:
            self.processed_layers.add(layer_name)
        return success

    def delete_layer_files(self, directory, layer_name):
        log_debug(f"Deleting existing files for layer: {layer_name}")
        shapefile_extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.fbn', '.fbx', '.ain', '.aih', '.ixs', '.mxs', '.atx', '.xml']
        files_to_delete = [f"{layer_name}{ext}" for ext in shapefile_extensions]

        for filename in files_to_delete:
            file_path = os.path.join(directory, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    log_debug(f"Deleted file: {filename}")
                except Exception as e:
                    log_warning(f"Failed to delete {file_path}. Reason: {e}")

    def _process_hatch_config(self, layer_name, layer_config):
        log_debug(f"Processing hatch configuration for layer: {layer_name}")

        hatch_config = self.style_manager.get_hatch_config(layer_config)

        # Store hatch configuration in the layer properties
        if layer_name not in self.all_layers or self.all_layers[layer_name] is None:
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

        gdf = self.all_layers[layer_name].copy()

        if 'attributes' not in gdf.columns:
            gdf['attributes'] = None

        gdf.loc[:, 'attributes'] = gdf['attributes'].apply(lambda x: {} if x is None else x)
        gdf.loc[:, 'attributes'] = gdf['attributes'].apply(lambda x: {**x, 'hatch_config': hatch_config})

        self.all_layers[layer_name] = gdf

        log_debug(f"Stored hatch configuration for layer: {layer_name}")


    def standardize_layer_crs(self, layer_name, geometry_or_gdf):
        target_crs = self.crs
        log_debug(f"Standardizing CRS for layer: {layer_name}")

        if isinstance(geometry_or_gdf, gpd.GeoDataFrame):
            log_debug(f"Original CRS: {geometry_or_gdf.crs}")
            if geometry_or_gdf.crs is None:
                log_warning(f"Layer {layer_name} has no CRS. Setting to target CRS: {target_crs}")
                geometry_or_gdf.set_crs(target_crs, inplace=True)
            elif geometry_or_gdf.crs != target_crs:
                log_debug(f"Transforming layer {layer_name} from {geometry_or_gdf.crs} to {target_crs}")
                geometry_or_gdf = geometry_or_gdf.to_crs(target_crs)
            log_debug(f"Final CRS for layer {layer_name}: {geometry_or_gdf.crs}")
            return geometry_or_gdf
        elif isinstance(geometry_or_gdf, gpd.GeoSeries):
            return self.standardize_layer_crs(layer_name, gpd.GeoDataFrame(geometry=geometry_or_gdf))
        elif isinstance(geometry_or_gdf, (Polygon, MultiPolygon, LineString, MultiLineString)):
            log_debug(f"Processing individual geometry for layer: {layer_name}")
            gdf = gpd.GeoDataFrame(geometry=[geometry_or_gdf], crs=target_crs)
            log_debug(f"Created GeoDataFrame with CRS: {gdf.crs}")
            return gdf.geometry.iloc[0]
        else:
            log_warning(f"Unsupported type for layer {layer_name}: {type(geometry_or_gdf)}")
            return geometry_or_gdf

    def _process_style(self, layer_name, style_config):
        if isinstance(style_config, str):
            # If style_config is a string, it's a preset name
            style_config = self.project_loader.get_style(style_config)

        if 'layer' in style_config:
            self.style_manager._process_layer_style(layer_name, style_config['layer'])
        if 'hatch' in style_config or 'applyHatch' in style_config:
            self.style_manager._process_hatch_style(layer_name, style_config)
        if 'text' in style_config:
            self.style_manager._process_text_style(layer_name, style_config['text'])

    def is_wmts_or_wms_layer(self, layer_name):
        # Check in all layer types
        layer_info = (
            next((l for l in self.project_settings.get('wmtsLayers', []) if l['name'] == layer_name), None) or
            next((l for l in self.project_settings.get('wmsLayers', []) if l['name'] == layer_name), None) or
            next((l for l in self.project_settings.get('geomLayers', []) if l['name'] == layer_name and
                 any(op.get('type', '').lower() in ['wmts', 'wms'] for op in l.get('operations', []))), None)
        )
        return layer_info is not None

    def delete_residual_shapefiles(self):
        output_dir = self.project_loader.shapefile_output_dir

        # Skip only if this specific setting is not configured
        if not output_dir:
            log_debug("Skipping residual shapefile cleanup - no shapefileOutputDir configured in project settings")
            return

        log_debug(f"Checking for residual shapefiles in {output_dir}")

        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            if os.path.isfile(file_path):
                layer_name = os.path.splitext(filename)[0]
                if layer_name not in self.processed_layers:
                    try:
                        os.remove(file_path)
                        log_debug(f"Deleted residual file: {filename}")
                    except Exception as e:
                        log_warning(f"Failed to delete residual file {file_path}. Reason: {e}")

    def _validate_loaded_geometries(self, gdf, layer_name, layer_config):
        """Validate geometries in a loaded GeoDataFrame, raise if invalid and no repair ops."""
        invalid_geometries = []
        null_geometries = []
        for idx, geom in enumerate(gdf.geometry):
            if geom is None:
                null_geometries.append(idx)
                continue
            if not geom.is_valid:
                invalid_geometries.append((idx, self._get_geometry_error(geom)))
            elif geom.is_empty:
                invalid_geometries.append((idx, "Empty geometry"))
            elif isinstance(geom, (Polygon, MultiPolygon)):
                polys = [geom] if isinstance(geom, Polygon) else geom.geoms
                for poly in polys:
                    if not poly.exterior.is_simple:
                        invalid_geometries.append((idx, "Self-intersecting polygon"))
                        break

        if null_geometries:
            log_warning(f"Null geometries found in layer '{layer_name}' at indices: {null_geometries}")

        if invalid_geometries:
            error_msg = f"Invalid geometries found in layer '{layer_name}':\n"
            for idx, reason in invalid_geometries:
                error_msg += f"  - Feature {idx}: {reason}\n"

            has_repair = any(op.get('type') == 'repair' for op in layer_config.get('operations', []))
            if has_repair:
                log_warning(error_msg)
                log_info(f"Layer '{layer_name}' will be processed with repair operations")
            else:
                log_error(error_msg)
                raise ValueError(error_msg)

    def _get_geometry_error(self, geom):
        """Helper method to get detailed geometry validation error"""
        try:
            from shapely.validation import explain_validity
            explanation = explain_validity(geom)
            if explanation == 'Valid Geometry':
                return None
            return explanation
        except Exception:
            # Fallback if explain_validity is not available
            if not geom.is_valid:
                return "Invalid geometry"
            return None
