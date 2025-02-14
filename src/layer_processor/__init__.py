"""Main layer processor module."""

from src.core.utils import log_debug, log_warning, log_error
from src.dxf_exporter.style_manager import StyleManager
from .shapefile_handler import ShapefileHandler
from .geometry_handler import GeometryHandler
from .style_handler import StyleHandler
from .layer_utils import is_wmts_or_wms_layer

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
        
        # Initialize handlers
        try:
            self.shapefile_handler = ShapefileHandler(self)
            self.geometry_handler = GeometryHandler(self)
            self.style_handler = StyleHandler(self)
            log_debug("Layer processor initialized successfully")
        except Exception as e:
            log_error(f"Error initializing layer processor: {str(e)}")
            raise

    def set_dxf_document(self, doc):
        """Set the DXF document reference."""
        try:
            self.dxf_doc = doc
            log_debug("DXF document reference set successfully")
        except Exception as e:
            log_error(f"Error setting DXF document reference: {str(e)}")
            raise

    def process_layers(self):
        """Process all layers in the project."""
        try:
            log_debug("Starting layer processing")
            self.shapefile_handler.setup_shapefiles()
            processed_layers = set()
            
            geom_layers = self.project_settings.get('geomLayers', [])
            total_layers = len(geom_layers)
            processed_count = 0
            
            for layer in geom_layers:
                try:
                    layer_name = layer.get('name', 'unnamed')
                    log_debug(f"Processing layer {processed_count + 1}/{total_layers}: {layer_name}")
                    self.process_layer(layer, processed_layers)
                    processed_count += 1
                except Exception as e:
                    log_error(f"Error processing layer {layer_name}: {str(e)}")
                    continue
            
            self.shapefile_handler.delete_residual_shapefiles()
            log_debug(f"Layer processing complete. Successfully processed {processed_count}/{total_layers} layers")
            
        except Exception as e:
            log_error(f"Error during layer processing: {str(e)}")
            raise

    def process_layer(self, layer, processed_layers, processing_stack=None):
        """Process a single layer and its dependencies."""
        layer_name = layer.get('name')
        if not layer_name:
            log_warning("Skipping layer with no name")
            return
            
        if layer_name in processed_layers:
            log_debug(f"Layer {layer_name} already processed, skipping")
            return
            
        if processing_stack is None:
            processing_stack = []
            
        if layer_name in processing_stack:
            error_msg = f"Circular dependency detected: {' -> '.join(processing_stack + [layer_name])}"
            log_error(error_msg)
            raise ValueError(error_msg)
            
        processing_stack.append(layer_name)
        log_debug(f"Processing layer: {layer_name}")
        
        try:
            # Process operations if any
            if 'operations' in layer:
                for operation in layer['operations']:
                    self.process_operation(layer_name, operation, processed_layers, processing_stack)
                    
            # Write shapefile if needed
            should_write_shapefile = (
                layer_name in self.all_layers and  # Layer exists in memory
                (
                    layer.get('outputShapeFile') or  # Explicit output path specified
                    self.project_settings.get('shapefileOutputDir')  # Global output directory specified
                )
            )
            
            if should_write_shapefile:
                log_debug(f"Writing shapefile for processed layer: {layer_name}")
                self.shapefile_handler.write_shapefile(layer_name)
                
            processed_layers.add(layer_name)
            log_debug(f"Layer {layer_name} processed successfully")
            
        except Exception as e:
            log_error(f"Error processing layer {layer_name}: {str(e)}")
            raise
        finally:
            processing_stack.remove(layer_name)

    def process_operation(self, layer_name, operation, processed_layers, processing_stack):
        """Process a single operation for a layer."""
        try:
            operation_type = operation.get('type', '').lower()
            log_debug(f"Processing operation {operation_type} for layer {layer_name}")
            
            # Map operation types to their module paths
            OPERATION_MAP = {
                'copy': ('src.operations', 'create_copy_layer'),
                'buffer': ('src.operations', 'create_buffer_layer'),
                'difference': ('src.operations', 'create_difference_layer'),
                'intersection': ('src.operations', 'create_intersection_layer'),
                'filter': ('src.operations', 'create_filtered_by_intersection_layer'),
                'wmts': ('src.operations', 'process_wmts_or_wms_layer'),
                'wms': ('src.operations', 'process_wmts_or_wms_layer'),
                'merge': ('src.operations', 'create_merged_layer'),
                'smooth': ('src.operations', 'create_smooth_layer'),
                'contour': ('src.operations', '_handle_contour_operation'),
                'dissolve': ('src.operations', 'create_dissolved_layer'),
                'calculate': ('src.operations', 'create_calculate_layer'),
                'directional_line': ('src.operations', 'create_directional_line_layer'),
                'circle': ('src.operations', 'create_circle_layer'),
                'connect_points': ('src.operations', 'create_connect_points_layer'),
                'envelope': ('src.operations', 'create_envelope_layer'),
                'label_association': ('src.operations', 'create_label_association_layer'),
                'filter_by_column': ('src.operations', 'create_filtered_by_column_layer'),
                'filter_geometry': ('src.operations.filter_geometry_operation', 'create_filtered_geometry_layer'),
                'report': ('src.operations.report_operation', 'create_report_layer'),
                'lagefaktor': ('src.operations.lagefaktor_operation', 'create_lagefaktor_layer')
            }
            
            if operation_type in OPERATION_MAP:
                module_path, function_name = OPERATION_MAP[operation_type]
                try:
                    module = __import__(module_path, fromlist=[function_name])
                    operation_function = getattr(module, function_name)
                    
                    # Special handling for label_association operation
                    if operation_type == 'label_association':
                        self.all_layers[layer_name] = operation_function(
                            self.all_layers,
                            self.project_settings,
                            self.crs,
                            layer_name,
                            operation,
                            self.project_loader
                        )
                    else:
                        self.all_layers[layer_name] = operation_function(
                            self.all_layers,
                            self.project_settings,
                            self.crs,
                            layer_name,
                            operation
                        )
                    
                    log_debug(f"Operation {operation_type} completed successfully for layer {layer_name}")
                    
                except ImportError as e:
                    log_error(f"Could not import operation module {module_path}: {str(e)}")
                    raise
                except Exception as e:
                    log_error(f"Error executing operation {operation_type}: {str(e)}")
                    raise
            else:
                error_msg = f"Unknown operation type: {operation_type}"
                log_error(error_msg)
                raise ValueError(error_msg)
                
        except Exception as e:
            log_error(f"Error processing operation for layer {layer_name}: {str(e)}")
            raise 