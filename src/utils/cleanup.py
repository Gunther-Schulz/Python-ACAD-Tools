"""Utility functions for DXF document cleanup."""

import ezdxf
from .base import log_debug

def cleanup_document(doc: ezdxf.document.Drawing) -> None:
    """Clean up a DXF document by removing unused elements.
    
    Args:
        doc: The DXF document to clean up
    """
    log_debug("Cleaning up DXF document...")
    
    # Remove unused layers
    for layer in doc.layers:
        if not layer.has_entities:
            doc.layers.remove(layer.dxf.name)
            log_debug(f"Removed unused layer: {layer.dxf.name}")
    
    # Remove unused linetypes
    for linetype in doc.linetypes:
        if not linetype.is_in_use():
            doc.linetypes.remove(linetype.dxf.name)
            log_debug(f"Removed unused linetype: {linetype.dxf.name}")
    
    # Remove unused text styles
    for style in doc.styles:
        if not style.is_in_use():
            doc.styles.remove(style.dxf.name)
            log_debug(f"Removed unused text style: {style.dxf.name}")
    
    # Remove unused blocks
    for block in doc.blocks:
        if not block.is_in_use():
            doc.blocks.remove(block.name)
            log_debug(f"Removed unused block: {block.name}")
    
    log_debug("Document cleanup completed") 