from typing import Dict, Any, List, Optional, Union, Tuple
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from pathlib import Path
import math

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from ..utils.dxf import get_layout, create_text

class TextManager(BaseProcessor):
    """Processor for managing text insertions in DXF documents."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the text manager.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self._initialize()

    def process_text_inserts(self) -> None:
        """Process all configured text insertions."""
        if not self.validate_document():
            return

        for text_config in self.config.project_config.text_inserts:
            try:
                self._process_text_insert(text_config)
            except Exception as e:
                log_error(f"Error processing text insert {text_config.get('name', 'unknown')}: {str(e)}")
                raise

    def _process_text_insert(self, text_config: Dict[str, Any]) -> None:
        """Process a single text insertion configuration.
        
        Args:
            text_config: Text insertion configuration dictionary
        """
        name = text_config.get('name')
        if not name:
            log_error("Text insert configuration missing required 'name' field")
            return

        log_info(f"Processing text insert: {name}")

        # Get text content
        content = text_config.get('text')
        if not content:
            log_error(f"Text insert {name} missing required 'text' field")
            return

        # Get target layout
        layout_name = text_config.get('layout', 'Model')
        layout = get_layout(self.doc, layout_name)

        # Get text style
        style = self.get_style(text_config.get('style', {}))

        # Process insertion points
        points = text_config.get('points', [])
        if not points:
            log_warning(f"No insertion points defined for text {name}")
            return

        # Insert text at each point
        for point in points:
            try:
                self._insert_text(
                    layout,
                    content,
                    self._get_point(point),
                    text_config,
                    style
                )
            except Exception as e:
                log_warning(f"Error inserting text at {point}: {str(e)}")

    def _get_point(self, point_config: Dict[str, Any]) -> Tuple[float, float]:
        """Get insertion point coordinates from configuration.
        
        Args:
            point_config: Point configuration dictionary
            
        Returns:
            (x, y) coordinate tuple
        """
        return (
            float(point_config.get('x', 0)),
            float(point_config.get('y', 0))
        )

    def _insert_text(self, layout: Layout,
                    content: str,
                    position: Tuple[float, float],
                    config: Dict[str, Any],
                    style: Dict[str, Any]) -> None:
        """Insert text at specified position.
        
        Args:
            layout: Target layout
            content: Text content
            position: Insertion point
            config: Text configuration dictionary
            style: Text style dictionary
        """
        # Get text properties
        height = float(style.get('height', 2.5))
        rotation = float(config.get('rotation', 0))
        alignment = self._get_alignment(config)
        
        # Create text entity
        text_entity = create_text(
            layout,
            content,
            position,
            {
                'layer': config.get('layer', '0'),
                'height': height,
                'rotation': rotation,
                'style': style.get('font', 'Standard'),
                'color': self.get_color_code(style.get('color', 'white')),
                'width': float(style.get('width', 1.0)),
                'halign': alignment[0],
                'valign': alignment[1]
            }
        )

        # Apply additional properties
        if 'oblique' in style:
            text_entity.dxf.oblique = float(style['oblique'])
        
        if 'generation' in style:
            flags = 0
            if style['generation'].get('backwards', False):
                flags |= 2
            if style['generation'].get('upside_down', False):
                flags |= 4
            text_entity.dxf.text_generation_flag = flags

    def _get_alignment(self, config: Dict[str, Any]) -> Tuple[str, str]:
        """Get text alignment from configuration.
        
        Args:
            config: Text configuration dictionary
            
        Returns:
            Tuple of (horizontal_alignment, vertical_alignment)
        """
        align = config.get('align', {})
        
        # Get horizontal alignment
        halign = align.get('horizontal', 'left').lower()
        if halign not in ('left', 'center', 'right'):
            log_warning(f"Invalid horizontal alignment: {halign}, using 'left'")
            halign = 'left'

        # Get vertical alignment
        valign = align.get('vertical', 'baseline').lower()
        if valign not in ('top', 'middle', 'baseline', 'bottom'):
            log_warning(f"Invalid vertical alignment: {valign}, using 'baseline'")
            valign = 'baseline'

        return (halign, valign)

    def _create_mtext(self, layout: Layout,
                     content: str,
                     position: Tuple[float, float],
                     config: Dict[str, Any],
                     style: Dict[str, Any]) -> None:
        """Create multi-line text (MText).
        
        Args:
            layout: Target layout
            content: Text content
            position: Insertion point
            config: Text configuration dictionary
            style: Text style dictionary
        """
        # Get text properties
        height = float(style.get('height', 2.5))
        rotation = float(config.get('rotation', 0))
        width = float(style.get('width', 50.0))
        
        # Create MText entity
        mtext = layout.add_mtext(
            content,
            dxfattribs={
                'layer': config.get('layer', '0'),
                'char_height': height,
                'rotation': rotation,
                'style': style.get('font', 'Standard'),
                'color': self.get_color_code(style.get('color', 'white')),
                'width': width
            }
        )
        
        # Set insertion point
        mtext.set_location(position)
        
        # Set alignment
        align = config.get('align', {})
        attachment_point = self._get_mtext_attachment(
            align.get('horizontal', 'left'),
            align.get('vertical', 'top')
        )
        mtext.dxf.attachment_point = attachment_point

    def _get_mtext_attachment(self, halign: str, valign: str) -> int:
        """Get MText attachment point code.
        
        Args:
            halign: Horizontal alignment ('left', 'center', 'right')
            valign: Vertical alignment ('top', 'middle', 'bottom')
            
        Returns:
            Attachment point code (1-9)
        """
        # Attachment point codes:
        # 1 = Top Left        2 = Top Center        3 = Top Right
        # 4 = Middle Left     5 = Middle Center     6 = Middle Right
        # 7 = Bottom Left     8 = Bottom Center     9 = Bottom Right
        
        h_codes = {'left': 0, 'center': 1, 'right': 2}
        v_codes = {'top': 0, 'middle': 1, 'bottom': 2}
        
        h = h_codes.get(halign.lower(), 0)
        v = v_codes.get(valign.lower(), 0)
        
        return v * 3 + h + 1

    def cleanup(self) -> None:
        """Clean up resources."""
        # Purge unused text styles
        if self.doc:
            deleted_styles = self.doc.styles.purge()
            if deleted_styles:
                log_debug(f"Purged {len(deleted_styles)} unused text styles") 