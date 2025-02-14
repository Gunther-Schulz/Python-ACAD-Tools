"""Operation management system."""
from typing import Any, Dict, Optional, Type
from src.core.utils import log_debug, log_error

class OperationContext:
    """Context for operation execution."""
    
    def __init__(self, layer_processor, all_layers, project_settings, crs):
        self.layer_processor = layer_processor
        self.all_layers = all_layers
        self.project_settings = project_settings
        self.crs = crs

class OperationRegistry:
    """Registry for operation handlers."""
    
    def __init__(self):
        self._handlers: Dict[str, Type['OperationHandler']] = {}
        
    def register(self, operation_type: str, handler_class: Type['OperationHandler']) -> None:
        """Register an operation handler."""
        self._handlers[operation_type.lower()] = handler_class
        
    def get_handler(self, operation_type: str) -> Optional[Type['OperationHandler']]:
        """Get the handler for an operation type."""
        return self._handlers.get(operation_type.lower())

class OperationHandler:
    """Base class for operation handlers."""
    
    def __init__(self, context: OperationContext):
        self.context = context
    
    def handle(self, layer_name: str, operation: Dict[str, Any]) -> Any:
        """Handle the operation."""
        raise NotImplementedError

class LazyOperationHandler(OperationHandler):
    """Operation handler that lazily imports its dependencies."""
    
    def __init__(self, context: OperationContext):
        super().__init__(context)
        self._module = None
        self._function = None
    
    @property
    def module_path(self) -> str:
        """Path to the module containing the operation function."""
        raise NotImplementedError
    
    @property
    def function_name(self) -> str:
        """Name of the operation function."""
        raise NotImplementedError
    
    def _ensure_imported(self):
        """Ensure the operation function is imported."""
        if self._module is None:
            module_parts = self.module_path.split('.')
            if len(module_parts) > 1:
                from importlib import import_module
                self._module = import_module(self.module_path)
                self._function = getattr(self._module, self.function_name)
            else:
                # Direct import for simple cases
                exec(f"from {self.module_path} import {self.function_name}")
                self._function = locals()[self.function_name]
    
    def handle(self, layer_name: str, operation: Dict[str, Any]) -> Any:
        """Handle the operation by calling the imported function."""
        self._ensure_imported()
        return self._function(
            self.context.all_layers,
            self.context.project_settings,
            self.context.crs,
            layer_name,
            operation
        )

# Operation Handler Implementations
class CopyOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_copy_layer"

class BufferOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_buffer_layer"

class DifferenceOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_difference_layer"

class IntersectionOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_intersection_layer"

class FilterOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_filtered_by_intersection_layer"

class WMTSOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "process_wmts_or_wms_layer"

class WMSOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "process_wmts_or_wms_layer"

class MergeOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_merged_layer"

class SmoothOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_smooth_layer"

class ContourOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "_handle_contour_operation"

class DissolveOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_dissolved_layer"

class CalculateOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_calculate_layer"

class DirectionalLineOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_directional_line_layer"

class CircleOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_circle_layer"

class ConnectPointsOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_connect_points_layer"

class EnvelopeOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_envelope_layer"

class LabelAssociationOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_label_association_layer"

class FilterByColumnOperationHandler(LazyOperationHandler):
    module_path = "src.operations"
    function_name = "create_filtered_by_column_layer"

class FilterGeometryOperationHandler(LazyOperationHandler):
    module_path = "src.operations.filter_geometry_operation"
    function_name = "create_filtered_geometry_layer"

class ReportOperationHandler(LazyOperationHandler):
    module_path = "src.operations.report_operation"
    function_name = "create_report_layer"

class LagefaktorOperationHandler(LazyOperationHandler):
    module_path = "src.operations.lagefaktor_operation"
    function_name = "create_lagefaktor_layer"

def create_default_registry() -> OperationRegistry:
    """Create a registry with all default operation handlers."""
    registry = OperationRegistry()
    
    # Register all handlers
    registry.register('copy', CopyOperationHandler)
    registry.register('buffer', BufferOperationHandler)
    registry.register('difference', DifferenceOperationHandler)
    registry.register('intersection', IntersectionOperationHandler)
    registry.register('filter', FilterOperationHandler)
    registry.register('wmts', WMTSOperationHandler)
    registry.register('wms', WMSOperationHandler)
    registry.register('merge', MergeOperationHandler)
    registry.register('smooth', SmoothOperationHandler)
    registry.register('contour', ContourOperationHandler)
    registry.register('dissolve', DissolveOperationHandler)
    registry.register('calculate', CalculateOperationHandler)
    registry.register('directional_line', DirectionalLineOperationHandler)
    registry.register('circle', CircleOperationHandler)
    registry.register('connect_points', ConnectPointsOperationHandler)
    registry.register('envelope', EnvelopeOperationHandler)
    registry.register('label_association', LabelAssociationOperationHandler)
    registry.register('filter_by_column', FilterByColumnOperationHandler)
    registry.register('filter_geometry', FilterGeometryOperationHandler)
    registry.register('report', ReportOperationHandler)
    registry.register('lagefaktor', LagefaktorOperationHandler)
    
    return registry 