import os
from typing import Optional, Dict, Any, List, Tuple, Union
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from ezdxf.entities import DXFGraphic
from pathlib import Path

from .logging import log_debug, log_info, log_warning, log_error

def create_document(dxf_version: str = 'R2010') -> Drawing:
    """Create a new DXF document.
    
    Args:
        dxf_version: DXF version to use
        
    Returns:
        New DXF document
    """
    return ezdxf.new(dxf_version)

def load_document(filepath: Union[str, Path], validate: bool = True) -> Drawing:
    """Load a DXF document from file.
    
    Args:
        filepath: Path to DXF file
        validate: Whether to validate the document after loading
        
    Returns:
        Loaded DXF document
        
    Raises:
        IOError: If file cannot be loaded
        DXFStructureError: If DXF structure is invalid
    """
    doc = ezdxf.readfile(str(filepath))
    if validate:
        auditor = doc.audit()
        if len(auditor.errors) > 0:
            log_warning(f"DXF document has {len(auditor.errors)} validation errors")
            for error in auditor.errors:
                log_warning(f"DXF validation error: {error}")
    return doc

def save_document(doc: Drawing, filepath: Union[str, Path], encoding: str = 'utf-8') -> None:
    """Save a DXF document to file.
    
    Args:
        doc: DXF document to save
        filepath: Path to save to
        encoding: File encoding to use
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(filepath, encoding=encoding)
    log_info(f"Saved DXF document to {filepath}")

def cleanup_document(doc: Drawing) -> None:
    """Clean up unused resources in a DXF document.
    
    Args:
        doc: DXF document to clean
    """
    try:
        # Purge unused blocks
        deleted_blocks = doc.blocks.purge()
        if deleted_blocks:
            log_debug(f"Purged {len(deleted_blocks)} unused blocks")

        # Purge unused linetypes
        deleted_linetypes = doc.linetypes.purge()
        if deleted_linetypes:
            log_debug(f"Purged {len(deleted_linetypes)} unused linetypes")

        # Purge unused text styles
        deleted_styles = doc.styles.purge()
        if deleted_styles:
            log_debug(f"Purged {len(deleted_styles)} unused text styles")

        # Purge unused dimension styles
        deleted_dimstyles = doc.dimstyles.purge()
        if deleted_dimstyles:
            log_debug(f"Purged {len(deleted_dimstyles)} unused dimension styles")

        # Purge unused appids
        deleted_appids = doc.appids.purge()
        if deleted_appids:
            log_debug(f"Purged {len(deleted_appids)} unused appids")

        # Purge unused viewports
        deleted_viewports = doc.viewports.purge()
        if deleted_viewports:
            log_debug(f"Purged {len(deleted_viewports)} unused viewports")

        # Audit the document
        auditor = doc.audit()
        if len(auditor.errors) > 0:
            log_warning(f"DXF document has {len(auditor.errors)} validation errors")
            for error in auditor.errors:
                log_warning(f"DXF validation error: {error}")

    except Exception as e:
        log_warning(f"Error during document cleanup: {str(e)}")

def copy_entity(entity: DXFGraphic, target_layout: Layout, 
                properties: Optional[Dict[str, Any]] = None) -> DXFGraphic:
    """Copy an entity to a target layout with optional property changes.
    
    Args:
        entity: Entity to copy
        target_layout: Layout to copy to
        properties: Properties to apply to the copy
        
    Returns:
        Copied entity
    """
    new_entity = target_layout.add_entity(entity.copy())
    if properties:
        for key, value in properties.items():
            if hasattr(new_entity, key):
                setattr(new_entity, key, value)
    return new_entity

def get_layout(doc: Drawing, name: Optional[str] = None) -> Layout:
    """Get a layout by name or the model space if no name given.
    
    Args:
        doc: DXF document
        name: Layout name (None for model space)
        
    Returns:
        Layout object
        
    Raises:
        KeyError: If named layout doesn't exist
    """
    if name is None or name.lower() == 'model':
        return doc.modelspace()
    return doc.layout(name)

def create_layer(doc: Drawing, name: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Create a new layer with optional properties.
    
    Args:
        doc: DXF document
        name: Layer name
        properties: Layer properties
    """
    if name in doc.layers:
        layer = doc.layers.get(name)
        log_debug(f"Layer {name} already exists")
    else:
        layer = doc.layers.new(name)
        log_debug(f"Created new layer: {name}")

    if properties:
        for key, value in properties.items():
            if hasattr(layer, key):
                setattr(layer, key, value)

def get_all_entities(layout: Layout, layer: Optional[str] = None) -> List[DXFGraphic]:
    """Get all entities from a layout, optionally filtered by layer.
    
    Args:
        layout: Layout to get entities from
        layer: Layer name to filter by
        
    Returns:
        List of entities
    """
    if layer:
        return [entity for entity in layout if entity.dxf.layer == layer]
    return list(layout)

def get_bounding_box(entities: List[DXFGraphic]) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Get the bounding box of a list of entities.
    
    Args:
        entities: List of entities
        
    Returns:
        Tuple of (min_x, min_y), (max_x, max_y) or None if no bounds
    """
    if not entities:
        return None

    bounds = None
    for entity in entities:
        try:
            entity_bounds = entity.get_bbox()
            if entity_bounds:
                if bounds is None:
                    bounds = entity_bounds
                else:
                    min_x = min(bounds[0][0], entity_bounds[0][0])
                    min_y = min(bounds[0][1], entity_bounds[0][1])
                    max_x = max(bounds[1][0], entity_bounds[1][0])
                    max_y = max(bounds[1][1], entity_bounds[1][1])
                    bounds = ((min_x, min_y), (max_x, max_y))
        except (AttributeError, TypeError):
            continue
    return bounds

def set_entity_properties(entity: DXFGraphic, properties: Dict[str, Any]) -> None:
    """Set properties on an entity.
    
    Args:
        entity: Entity to modify
        properties: Properties to set
    """
    for key, value in properties.items():
        try:
            setattr(entity.dxf, key, value)
        except AttributeError:
            log_warning(f"Cannot set property {key} on entity type {type(entity)}")

def create_text(layout: Layout, text: str, position: Tuple[float, float], 
                properties: Optional[Dict[str, Any]] = None) -> DXFGraphic:
    """Create a text entity.
    
    Args:
        layout: Layout to add text to
        text: Text content
        position: Text position (x, y)
        properties: Text properties
        
    Returns:
        Created text entity
    """
    text_entity = layout.add_text(text)
    text_entity.dxf.insert = position
    
    if properties:
        set_entity_properties(text_entity, properties)
    
    return text_entity 