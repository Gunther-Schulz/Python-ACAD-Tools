"""Operation registry with decorator-based auto-discovery."""
import importlib
import pkgutil
from pathlib import Path
from src.utils import log_warning, log_debug


_registry = {}


class OperationInfo:
    __slots__ = ('handler', 'needs_project_loader', 'creates_separate_layer',
                 'separate_layer_suffix', 'description')

    def __init__(self, handler, needs_project_loader=False,
                 creates_separate_layer=False, separate_layer_suffix='_labels',
                 description=''):
        self.handler = handler
        self.needs_project_loader = needs_project_loader
        self.creates_separate_layer = creates_separate_layer
        self.separate_layer_suffix = separate_layer_suffix
        self.description = description


def register_operation(op_type, needs_project_loader=False,
                       creates_separate_layer=False,
                       separate_layer_suffix='_labels',
                       description=''):
    """Decorator to register an operation handler."""
    def decorator(func):
        _registry[op_type] = OperationInfo(
            handler=func,
            needs_project_loader=needs_project_loader,
            creates_separate_layer=creates_separate_layer,
            separate_layer_suffix=separate_layer_suffix,
            description=description,
        )
        return func
    return decorator


def get_operation(op_type):
    """Look up a registered operation. Returns OperationInfo or None."""
    _ensure_discovered()
    return _registry.get(op_type)


def get_all_operations():
    """Return all registered operations."""
    _ensure_discovered()
    return dict(_registry)


_discovered = False


def _ensure_discovered():
    """Auto-discover all operation modules on first access."""
    global _discovered
    if _discovered:
        return
    _discovered = True
    package_dir = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.endswith('_operation') or module_info.name.endswith('_operations'):
            try:
                importlib.import_module(f'src.operations.{module_info.name}')
            except Exception as e:
                log_warning(f"Failed to load operation module {module_info.name}: {e}")
