"""Main layer processor module."""

from src.core.utils import log_debug, log_warning, log_error
from src.dxf_exporter.style_manager import StyleManager
from src.dxf_exporter.layer_manager import LayerManager
from .shapefile_handler import ShapefileHandler
from .geometry_handler import GeometryHandler
from .style_handler import StyleHandler
from .layer_utils import is_wmts_or_wms_layer

class LayerProcessor:
    """Main class for processing layers and their operations."""

    def __init__(self, project_loader, plot_ops=False, service_container=None):
        """Initialize the layer processor.
        
        Args:
            project_loader: ProjectLoader instance
            plot_ops: Whether to plot operations (default: False)
            service_container: Optional ServiceContainer instance
        """
        self.project_loader = project_loader
        self.project_settings = project_loader.project_settings
        self.crs = project_loader.crs
        self.all_layers = {}
        self.plot_ops = plot_ops
        self.processed_layers = set()
        self.dxf_doc = None
        
        # Get services from container if provided, otherwise create new instances
        if service_container:
            self.style_manager = service_container.get('style_manager')
            self.layer_manager = service_container.get('layer_manager')
            if not self.style_manager:
                log_warning("StyleManager not found in service container, creating new instance")
                self.style_manager = StyleManager(project_loader)
            if not self.layer_manager:
                log_warning("LayerManager not found in service container, creating new instance")
                self.layer_manager = LayerManager(project_loader, self.style_manager)
        else:
            self.style_manager = StyleManager(project_loader)
            self.layer_manager = LayerManager(project_loader, self.style_manager)
        
        # Initialize handlers
        self._init_handlers()
        
    def _init_handlers(self):
        """Initialize all handlers with dependencies."""
        self.shapefile_handler = ShapefileHandler(self)
        self.geometry_handler = GeometryHandler(self)
        self.style_handler = StyleHandler(self)
        
    def set_dxf_document(self, doc):
        """Set the DXF document reference."""
        self.dxf_doc = doc
        
    def process_layers(self):
        """Process all layers in the project."""
        try:
            self._setup_processing()
            self._process_all_layers()
            self._cleanup_processing()
        except Exception as e:
            log_error(f"Error processing layers: {str(e)}")
            raise
            
    def _setup_processing(self):
        """Setup initial processing state."""
        self.shapefile_handler.setup_shapefiles()
        self.processed_layers = set()
        
    def _process_all_layers(self):
        """Process all layers from project settings."""
        for layer in self.project_settings.get('geomLayers', []):
            self.process_layer(layer, self.processed_layers)
            
    def _cleanup_processing(self):
        """Cleanup after processing is complete."""
        self.shapefile_handler.delete_residual_shapefiles()

    def process_layer(self, layer, processed_layers, processing_stack=None):
        """Process a single layer and its dependencies.
        
        Args:
            layer: Layer configuration dictionary
            processed_layers: Set of already processed layer names
            processing_stack: List tracking the processing stack for cycle detection
        """
        layer_name = layer.get('name')
        if not layer_name:
            return
            
        if layer_name in processed_layers:
            return
            
        if processing_stack is None:
            processing_stack = []
            
        if layer_name in processing_stack:
            raise ValueError(f"Circular dependency detected: {' -> '.join(processing_stack + [layer_name])}")
            
        processing_stack.append(layer_name)
        
        try:
            self._process_layer_operations(layer_name, layer, processed_layers, processing_stack)
            self._handle_shapefile_output(layer_name, layer)
            processed_layers.add(layer_name)
            
        finally:
            processing_stack.remove(layer_name)
            
    def _process_layer_operations(self, layer_name, layer, processed_layers, processing_stack):
        """Process operations for a single layer."""
        if 'operations' in layer:
            for operation in layer['operations']:
                self.process_operation(layer_name, operation, processed_layers, processing_stack)
                
    def _handle_shapefile_output(self, layer_name, layer):
        """Handle shapefile output for a processed layer."""
        should_write_shapefile = (
            layer_name in self.all_layers and
            (
                layer.get('outputShapeFile') or
                self.project_settings.get('shapefileOutputDir')
            )
        )
        
        if should_write_shapefile:
            log_debug(f"Writing shapefile for processed layer: {layer_name}")
            self.shapefile_handler.write_shapefile(layer_name)

    def process_operation(self, layer_name, operation, processed_layers, processing_stack):
        """Process a single operation for a layer."""
        operation_type = operation.get('type', '').lower()
        
        # Import operations as needed
        if operation_type == 'copy':
            from src.operations import create_copy_layer
            self.all_layers[layer_name] = create_copy_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'buffer':
            from src.operations import create_buffer_layer
            self.all_layers[layer_name] = create_buffer_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'difference':
            from src.operations import create_difference_layer
            self.all_layers[layer_name] = create_difference_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'intersection':
            from src.operations import create_intersection_layer
            self.all_layers[layer_name] = create_intersection_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'filter':
            from src.operations import create_filtered_by_intersection_layer
            self.all_layers[layer_name] = create_filtered_by_intersection_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type in ('wmts', 'wms'):
            from src.operations import process_wmts_or_wms_layer
            self.all_layers[layer_name] = process_wmts_or_wms_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'merge':
            from src.operations import create_merged_layer
            self.all_layers[layer_name] = create_merged_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'smooth':
            from src.operations import create_smooth_layer
            self.all_layers[layer_name] = create_smooth_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'contour':
            from src.operations import _handle_contour_operation
            self.all_layers[layer_name] = _handle_contour_operation(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'dissolve':
            from src.operations import create_dissolved_layer
            self.all_layers[layer_name] = create_dissolved_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'calculate':
            from src.operations import create_calculate_layer
            self.all_layers[layer_name] = create_calculate_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'directional_line':
            from src.operations import create_directional_line_layer
            self.all_layers[layer_name] = create_directional_line_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'circle':
            from src.operations import create_circle_layer
            self.all_layers[layer_name] = create_circle_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'connect_points':
            from src.operations import create_connect_points_layer
            self.all_layers[layer_name] = create_connect_points_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'envelope':
            from src.operations import create_envelope_layer
            self.all_layers[layer_name] = create_envelope_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'label_association':
            from src.operations import create_label_association_layer
            self.all_layers[layer_name] = create_label_association_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation, self.project_loader)
        elif operation_type == 'filter_by_column':
            from src.operations import create_filtered_by_column_layer
            self.all_layers[layer_name] = create_filtered_by_column_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'filter_geometry':
            from src.operations.filter_geometry_operation import create_filtered_geometry_layer
            self.all_layers[layer_name] = create_filtered_geometry_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'report':
            from src.operations.report_operation import create_report_layer
            self.all_layers[layer_name] = create_report_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        elif operation_type == 'lagefaktor':
            from src.operations.lagefaktor_operation import create_lagefaktor_layer
            self.all_layers[layer_name] = create_lagefaktor_layer(self.all_layers, self.project_settings, self.crs, layer_name, operation)
        else:
            raise ValueError(f"Unknown operation type: {operation_type}") 