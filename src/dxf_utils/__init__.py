"""
DXF utilities package.

Re-exports everything from _core.py for backward compatibility.
All existing `from src.dxf_utils import X` statements continue to work.
"""
from src.dxf_utils._core import *
from src.dxf_utils._core import (
    _extract_entity_name_from_xdata,
    _apply_text_style_properties,
    _get_entity_space,
    _extract_sync_mode_from_xdata,
)
