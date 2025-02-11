from typing import Dict, Any, List, Optional, Union, Tuple
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from pathlib import Path

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from ..utils.dxf import get_layout

class BlockManager(BaseProcessor):
    """Processor for managing block insertions in DXF documents."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the block manager.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self._initialize()

    def process_block_inserts(self) -> None:
        """Process all configured block insertions."""
        if not self.validate_document():
            return

        for block_config in self.config.project_config.block_inserts:
            try:
                self._process_block_insert(block_config)
            except Exception as e:
                log_error(f"Error processing block insert {block_config.get('name', 'unknown')}: {str(e)}")
                raise

    def _process_block_insert(self, block_config: Dict[str, Any]) -> None:
        """Process a single block insertion configuration.
        
        Args:
            block_config: Block insertion configuration dictionary
        """
        name = block_config.get('name')
        if not name:
            log_error("Block insert configuration missing required 'name' field")
            return

        log_info(f"Processing block insert: {name}")

        # Get block definition
        block_name = block_config.get('blockName')
        if not block_name:
            log_error(f"Block insert {name} missing required 'blockName' field")
            return

        if block_name not in self.doc.blocks:
            # Try to load from external file
            source_file = block_config.get('sourceFile')
            if source_file:
                self._import_block(block_name, source_file)
            else:
                log_error(f"Block {block_name} not found and no source file specified")
                return

        # Get target layout
        layout_name = block_config.get('layout', 'Model')
        layout = get_layout(self.doc, layout_name)

        # Process insertion points
        points = block_config.get('points', [])
        if not points:
            log_warning(f"No insertion points defined for block {name}")
            return

        # Get block attributes
        attributes = block_config.get('attributes', {})
        
        # Get insertion parameters
        rotation = float(block_config.get('rotation', 0))
        scale = self._get_scale(block_config)

        # Insert blocks
        for point in points:
            try:
                self._insert_block(
                    layout,
                    block_name,
                    self._get_point(point),
                    rotation,
                    scale,
                    attributes,
                    block_config
                )
            except Exception as e:
                log_warning(f"Error inserting block at {point}: {str(e)}")

    def _import_block(self, block_name: str, source_file: str) -> None:
        """Import a block definition from an external DXF file.
        
        Args:
            block_name: Name of the block to import
            source_file: Path to source DXF file
        """
        try:
            source_path = self.resolve_path(source_file)
            source_doc = ezdxf.readfile(source_path)
            
            if block_name in source_doc.blocks:
                # Copy block definition
                self.doc.blocks.new(name=block_name)
                source_block = source_doc.blocks[block_name]
                target_block = self.doc.blocks[block_name]
                
                for entity in source_block:
                    target_block.add_entity(entity.copy())
                
                log_info(f"Imported block {block_name} from {source_file}")
            else:
                log_error(f"Block {block_name} not found in {source_file}")
                
        except Exception as e:
            log_error(f"Error importing block from {source_file}: {str(e)}")
            raise

    def _get_point(self, point_config: Dict[str, Any]) -> Tuple[float, float, float]:
        """Get insertion point coordinates from configuration.
        
        Args:
            point_config: Point configuration dictionary
            
        Returns:
            (x, y, z) coordinate tuple
        """
        return (
            float(point_config.get('x', 0)),
            float(point_config.get('y', 0)),
            float(point_config.get('z', 0))
        )

    def _get_scale(self, config: Dict[str, Any]) -> Tuple[float, float, float]:
        """Get scale factors from configuration.
        
        Args:
            config: Block configuration dictionary
            
        Returns:
            (x_scale, y_scale, z_scale) tuple
        """
        scale = config.get('scale', {})
        return (
            float(scale.get('x', 1.0)),
            float(scale.get('y', 1.0)),
            float(scale.get('z', 1.0))
        )

    def _insert_block(self, layout: Layout,
                     block_name: str,
                     position: Tuple[float, float, float],
                     rotation: float,
                     scale: Tuple[float, float, float],
                     attributes: Dict[str, str],
                     config: Dict[str, Any]) -> None:
        """Insert a block reference.
        
        Args:
            layout: Target layout
            block_name: Name of block to insert
            position: Insertion point
            rotation: Rotation angle in degrees
            scale: Scale factors (x, y, z)
            attributes: Block attribute values
            config: Block configuration dictionary
        """
        # Create block reference
        block_ref = layout.add_blockref(
            block_name,
            position,
            dxfattribs={
                'rotation': rotation,
                'xscale': scale[0],
                'yscale': scale[1],
                'zscale': scale[2],
                'layer': config.get('layer', '0')
            }
        )

        # Set attribute values
        if attributes and block_ref.has_attribs:
            for attrib in block_ref.attribs:
                tag = attrib.dxf.tag
                if tag in attributes:
                    attrib.dxf.text = str(attributes[tag])

    def cleanup(self) -> None:
        """Clean up resources."""
        # Try to purge unused blocks if supported
        if self.doc and hasattr(self.doc.blocks, 'purge'):
            try:
                deleted_blocks = self.doc.blocks.purge()
                if deleted_blocks:
                    log_debug(f"Purged {len(deleted_blocks)} unused blocks")
            except Exception as e:
                log_warning(f"Error purging unused blocks: {str(e)}")
                pass 