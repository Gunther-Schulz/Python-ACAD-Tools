"""Main layer processor module."""

from typing import Dict, Optional, Set, Any, List
from src.core.utils import log_debug, log_warning, log_error
from src.dxf_exporter.style_manager import StyleManager
from src.dxf_exporter.layer_manager import LayerManager
from .shapefile_handler import ShapefileHandler
from .geometry_handler import GeometryHandler
from .style_handler import StyleHandler
from .layer_utils import is_wmts_or_wms_layer
from .operation_management import (
    OperationContext,
    OperationRegistry,
    create_default_registry
)

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
        self.processed_layers: Set[str] = set()
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
        
        # Initialize handlers and operation registry
        self._init_handlers()
        
    def _init_handlers(self):
        """Initialize all handlers with dependencies."""
        self.shapefile_handler = ShapefileHandler(self)
        self.geometry_handler = GeometryHandler(self)
        self.style_handler = StyleHandler(self)
        
        # Initialize operation management
        self.operation_registry = create_default_registry()
        self.operation_context = OperationContext(
            self,
            self.all_layers,
            self.project_settings,
            self.crs
        )
        
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
        
    def _get_layer_dependencies(self, layer: Dict) -> Set[str]:
        """Get all layer names that this layer depends on through its operations."""
        dependencies = set()
        
        if 'operations' not in layer:
            return dependencies
            
        for operation in layer['operations']:
            # Get layers from the operation
            op_layers = operation.get('layers', [])
            for op_layer in op_layers:
                if isinstance(op_layer, str):
                    dependencies.add(op_layer)
                elif isinstance(op_layer, dict):
                    dependencies.add(op_layer['name'])
                    
        return dependencies

    def _build_dependency_graph(self, layers: List[Dict]) -> Dict[str, Set[str]]:
        """Build a graph of layer dependencies."""
        dependency_graph = {}
        
        for layer in layers:
            layer_name = layer.get('name')
            if not layer_name:
                continue
                
            dependencies = self._get_layer_dependencies(layer)
            dependency_graph[layer_name] = dependencies
            
        return dependency_graph

    def _get_processing_order(self, layers: List[Dict]) -> List[str]:
        """Determine the order in which layers should be processed based on their dependencies."""
        dependency_graph = self._build_dependency_graph(layers)
        processing_order = []
        processed = set()
        
        def process_layer(layer_name: str, path: Set[str]):
            if layer_name in path:
                cycle = ' -> '.join(list(path) + [layer_name])
                raise ValueError(f"Circular dependency detected: {cycle}")
                
            if layer_name in processed:
                return
                
            path.add(layer_name)
            
            # Process dependencies first
            for dep in dependency_graph.get(layer_name, set()):
                if dep not in processed:
                    process_layer(dep, path)
                    
            path.remove(layer_name)
            processed.add(layer_name)
            processing_order.append(layer_name)
            
        # Process each layer
        for layer in layers:
            layer_name = layer.get('name')
            if layer_name and layer_name not in processed:
                process_layer(layer_name, set())
                
        return processing_order
        
    def _process_all_layers(self):
        """Process all layers from project settings in dependency order."""
        layers = self.project_settings.get('geomLayers', [])
        
        # Get the processing order based on dependencies
        try:
            processing_order = self._get_processing_order(layers)
            log_debug(f"Layer processing order: {processing_order}")
            
            # Create a map of layer configs by name for easy lookup
            layer_configs = {layer.get('name'): layer for layer in layers if layer.get('name')}
            
            # Process layers in the determined order
            for layer_name in processing_order:
                layer_config = layer_configs.get(layer_name)
                if layer_config:
                    self.process_layer(layer_config, self.processed_layers)
                    
        except ValueError as e:
            log_error(f"Error determining layer processing order: {str(e)}")
            raise
            
    def _cleanup_processing(self):
        """Cleanup after processing is complete."""
        self.shapefile_handler.delete_residual_shapefiles()

    def process_layer(self, layer: Dict, processed_layers: Set[str], processing_stack: Optional[list] = None):
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
            
    def _process_layer_operations(self, layer_name: str, layer: Dict, processed_layers: Set[str], processing_stack: list):
        """Process operations for a single layer."""
        if 'operations' in layer:
            for operation in layer['operations']:
                self.process_operation(layer_name, operation, processed_layers, processing_stack)
                
    def _handle_shapefile_output(self, layer_name: str, layer: Dict):
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

    def process_operation(self, layer_name: str, operation: Dict, processed_layers: Set[str], processing_stack: list) -> Any:
        """Process a single operation for a layer."""
        operation_type = operation.get('type', '').lower()
        
        # Get the appropriate handler
        handler_class = self.operation_registry.get_handler(operation_type)
        if not handler_class:
            raise ValueError(f"Unknown operation type: {operation_type}")
            
        # Create and use the handler
        handler = handler_class(self.operation_context)
        result = handler.handle(layer_name, operation)
        
        # Store the result
        self.all_layers[layer_name] = result
        
        return result 