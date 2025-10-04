import traceback
# from src.dump_to_shape import merge_dxf_layer_to_shapefile
from src.project_loader import ProjectLoader
from src.utils import log_info, log_warning, log_error, resolve_path, ensure_path_exists, log_debug
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, LinearRing
import ezdxf
import math
from geopandas import GeoSeries
import os
import shutil
import fiona
from src.style_manager import StyleManager

# Import operations individually
from src.operations import (
    create_copy_layer,
    create_buffer_layer,
    create_difference_layer,
    create_intersection_layer,
    create_filtered_by_intersection_layer,
    process_wmts_or_wms_layer,
    create_merged_layer,
    create_smooth_layer,
    _handle_contour_operation,
    create_dissolved_layer,
    create_calculate_layer,
    create_directional_line_layer,
    create_circle_layer,
    create_connect_points_layer,
    create_envelope_layer,
    create_label_association_layer,
    create_filtered_by_column_layer,
    create_repair_layer,
    create_remove_interior_rings_layer
)
from src.style_manager import StyleManager
from src.operations.filter_geometry_operation import create_filtered_geometry_layer
from src.operations.report_operation import create_report_layer
from src.shapefile_utils import write_shapefile
from src.operations.label_association_operation import create_label_association_layer
from src.operations.lagefaktor_operation import create_lagefaktor_layer
from src.operations.simple_label_operation import create_simple_label_layer
from src.operations.point_label_operation import create_point_label_layer
from src.operations.simplify_slivers_operation import create_simplify_slivers_layer
from src.operations.remove_protrusions_operation import create_remove_protrusions_layer
from src.operations.remove_slivers_erosion_operation import create_remove_slivers_erosion_layer
from src.operations.remove_degenerate_spikes_operation import create_remove_degenerate_spikes_layer

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
            from src.dxf_utils import read_cad_layer_to_geodataframe
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
            import geopandas as gpd
            self.all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def _process_layer_operations(self, layer_obj, layer_name, processed_layers, processing_stack):
        """
        Process layer operations (extracted from original process_layer logic).
        Works for all sync modes.
        """
        # Check for unrecognized keys
        recognized_keys = {'name', 'sync', 'operations', 'shapeFile', 'type', 'sourceLayer',
                          'outputShapeFile', 'style', 'close', 'linetypeScale', 'linetypeGeneration',
                          'viewports', 'attributes', 'bluntAngles', 'label', 'applyHatch', 'plot', 'saveToLagefaktor'}
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
        elif 'dxfLayer' not in layer_obj:
            # Only set to None if not already set (e.g., by pull mode)
            if layer_name not in self.all_layers:
                self.all_layers[layer_name] = None
                log_debug(f"Added layer {layer_name} without data")

        if 'outputShapeFile' in layer_obj:
            self.write_shapefile(layer_name)

        if 'attributes' in layer_obj:
            if layer_name not in self.all_layers or self.all_layers[layer_name] is None:
                import geopandas as gpd
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

            log_debug(f"Applying blunt angles to layer '{layer_name}' with threshold {angle_threshold} and distance {blunt_distance}")

            if layer_name in self.all_layers:
                original_geom = self.all_layers[layer_name]
                blunted_geom = original_geom.geometry.apply(
                    lambda geom: self.blunt_sharp_angles(geom, angle_threshold, blunt_distance)
                )
                self.all_layers[layer_name].geometry = blunted_geom

                log_debug(f"Blunting complete for layer '{layer_name}'")
                log_debug(f"Original geometry count: {len(original_geom)}")
                log_debug(f"Blunted geometry count: {len(blunted_geom)}")
            else:
                log_warning(f"Layer '{layer_name}' not found for blunting angles")

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
        elif op_type == 'filterByIntersection':
            result = create_filtered_by_intersection_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'wmts' or op_type == 'wms':
            result = process_wmts_or_wms_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation, self.project_loader)
        elif op_type == 'merge':
            result = create_merged_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'smooth':
            result = create_smooth_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'contour':
            result = _handle_contour_operation(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'filterGeometry':
            result = create_filtered_geometry_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'dissolve':
            result = create_dissolved_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'report':
            result = create_report_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'calculate':
            result = create_calculate_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'directionalLine':
            result = create_directional_line_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'circle':
            result = create_circle_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'connect-points':
            result = create_connect_points_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'envelope':
            result = create_envelope_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'repair':
            result = create_repair_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'removeInteriorRings':
            result = create_remove_interior_rings_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'labelAssociation':
            result = create_label_association_layer(self.all_layers, self.project_settings,
                                                 self.crs, layer_name, operation,
                                                 self.project_loader)
        elif op_type == 'lagefaktor':
            result = create_lagefaktor_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'simpleLabel':
            # Create a separate label layer name
            label_layer_name = f"{layer_name}_labels"
            # Generate the labels
            labels_result = create_simple_label_layer(self.all_layers, self.project_settings,
                                             self.crs, layer_name, operation,
                                             self.project_loader)
            # Store in a separate layer
            if labels_result is not None:
                self.all_layers[label_layer_name] = labels_result
                log_debug(f"Created label layer '{label_layer_name}' for '{layer_name}'")
            # Return None so the original layer is preserved
            return None
        elif op_type == 'pointLabel':
            # Create a separate label layer name
            label_layer_name = f"{layer_name}_labels"
            # Generate the labels using existing point geometries
            labels_result = create_point_label_layer(self.all_layers, self.project_settings,
                                             self.crs, layer_name, operation,
                                             self.project_loader)
            # Store in a separate layer
            if labels_result is not None:
                self.all_layers[label_layer_name] = labels_result
                log_debug(f"Created point label layer '{label_layer_name}' for '{layer_name}'")
            # Return None so the original layer is preserved
            return None
        elif op_type == 'filterByColumn':
            result = create_filtered_by_column_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'simplifySlivers':
            result = create_simplify_slivers_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'removeProtrusions':
            result = create_remove_protrusions_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'removeSliversErosion':
            result = create_remove_slivers_erosion_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif op_type == 'removeDegenerateSpikes':
            result = create_remove_degenerate_spikes_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        else:
            log_warning(f"Unknown operation type: {op_type} for layer {layer_name}")
            return None

        if result is not None:
            self.all_layers[layer_name] = result
            if self.plot_ops:
                self.plot_operation_result(layer_name, op_type, result)

        # Clean up temporary layers
        if 'operations' in operation:
            for temp_layer in [l for l in self.all_layers.keys() if l.startswith(f"{layer_name}_temp_")]:
                del self.all_layers[temp_layer]

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

                    # Validate geometries
                    invalid_geometries = []
                    null_geometries = []
                    for idx, geom in enumerate(gdf.geometry):
                        if geom is None:
                            null_geometries.append(idx)
                            continue

                        if not geom.is_valid:
                            reason = self._get_geometry_error(geom)
                            invalid_geometries.append((idx, reason))
                        elif geom.is_empty:
                            invalid_geometries.append((idx, "Empty geometry"))
                        elif isinstance(geom, (Polygon, MultiPolygon)):
                            # Check for self-intersection in polygons
                            if isinstance(geom, Polygon):
                                if not geom.exterior.is_simple:
                                    invalid_geometries.append((idx, "Self-intersecting polygon"))
                            else:  # MultiPolygon
                                for poly in geom.geoms:
                                    if not poly.exterior.is_simple:
                                        invalid_geometries.append((idx, "Self-intersecting polygon in MultiPolygon"))
                                        break

                    if null_geometries:
                        log_warning(f"Null geometries found in layer '{layer_name}' at indices: {null_geometries}")

                    # Check if this layer has repair operations that might fix the invalid geometries
                    has_repair_operations = any(
                        op.get('type') == 'repair'
                        for op in layer.get('operations', [])
                    )

                    # Allow loading with warnings if repair operations are present, otherwise fail
                    if invalid_geometries:
                        error_msg = f"Invalid geometries found in layer '{layer_name}':\n"
                        for idx, reason in invalid_geometries:
                            error_msg += f"  - Feature {idx}: {reason}\n"

                        if has_repair_operations:
                            log_warning("Found invalid geometries, but repair operations are configured:")
                            log_warning(error_msg)
                            log_info(f"Layer '{layer_name}' will be processed with repair operations to fix {len(invalid_geometries)} invalid geometries")
                        else:
                            log_error(error_msg)
                            log_error(f"Consider adding a 'repair' operation to layer '{layer_name}' to fix these geometry issues")
                            raise ValueError(error_msg)

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
            elif 'dxfLayer' in layer:
                # gdf = self.load_dxf_layer(layer_name, layer['dxfLayer'])
                self.all_layers[layer_name] = gdf
                if 'outputShapeFile' in layer:
                    output_path = self.project_loader.resolve_full_path(layer['outputShapeFile'])
                    self.write_shapefile(layer_name, output_path)

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

    # def load_dxf_layer(self, layer_name, dxf_layer_name):
    #     return load_dxf_layer(layer_name, dxf_layer_name, self.dxf_doc, self.project_loader, self.crs)

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

        log_debug(f"Blunting angles for geometry: {geometry.wkt[:100]}...")
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
        log_debug(f"Blunting polygon angles: {polygon.wkt[:100]}...")

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
                log_debug(f"Blunting angle at point {i}")
                blunted_points = self._create_radical_blunt_segment(prev_point, current_point, next_point, blunt_distance)
                new_coords.extend(blunted_points)
            else:
                new_coords.append(coords[i])

        new_coords.append(new_coords[0])  # Close the ring
        return LinearRing(new_coords)

    def _blunt_linestring_angles(self, linestring, angle_threshold, blunt_distance):
        log_debug(f"Blunting linestring angles: {linestring.wkt[:100]}...")
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
                log_debug(f"Blunting angle at point {i}")
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
        log_debug(f"Creating radical blunt segment for points: {p1}, {p2}, {p3}")
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

        log_debug(f"Radical blunt segment created: {point1}, {point2}")
        return [point1, point2]

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
