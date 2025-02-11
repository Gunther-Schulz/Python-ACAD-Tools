from typing import Dict, Any, List, Optional, Union, Tuple
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from pathlib import Path

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from ..utils.dxf import get_layout, create_text

class LegendCreator(BaseProcessor):
    """Processor for creating legends in DXF documents."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the legend creator.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self._initialize()

    def create_legends(self) -> None:
        """Create all configured legends."""
        if not self.validate_document():
            return

        for legend_config in self.config.project_config.legends:
            try:
                self._create_legend(legend_config)
            except Exception as e:
                log_error(f"Error creating legend {legend_config.get('name', 'unknown')}: {str(e)}")
                raise

    def _create_legend(self, legend_config: Dict[str, Any]) -> None:
        """Create a single legend.
        
        Args:
            legend_config: Legend configuration dictionary
        """
        name = legend_config.get('name')
        if not name:
            log_error("Legend configuration missing required 'name' field")
            return

        log_info(f"Creating legend: {name}")

        # Get target layout
        layout_name = legend_config.get('layout', 'Model')
        layout = get_layout(self.doc, layout_name)

        # Get legend position and style
        position = self._get_position(legend_config)
        style = self.get_style(legend_config.get('style', {}))

        # Create legend container
        self._create_container(layout, position, legend_config)

        # Create legend items
        items = legend_config.get('items', [])
        if not items:
            log_warning(f"No items defined for legend {name}")
            return

        current_y = position[1]
        for item in items:
            try:
                height = self._create_legend_item(
                    layout, (position[0], current_y), item, style
                )
                current_y -= height + style.get('itemSpacing', 10)
            except Exception as e:
                log_warning(f"Error creating legend item: {str(e)}")

    def _get_position(self, config: Dict[str, Any]) -> Tuple[float, float]:
        """Get the legend position from configuration.
        
        Args:
            config: Legend configuration
            
        Returns:
            (x, y) position tuple
        """
        position = config.get('position', {})
        return (
            float(position.get('x', 0)),
            float(position.get('y', 0))
        )

    def _create_container(self, layout: Layout,
                         position: Tuple[float, float],
                         config: Dict[str, Any]) -> None:
        """Create the legend container (box and title).
        
        Args:
            layout: Target layout
            position: Legend position
            config: Legend configuration
        """
        # Get container style
        style = self.get_style(config.get('style', {}))
        container = style.get('container', {})
        
        if container.get('visible', True):
            # Create container box if specified
            width = float(container.get('width', 200))
            height = float(container.get('height', 400))
            
            points = [
                position,
                (position[0] + width, position[1]),
                (position[0] + width, position[1] - height),
                (position[0], position[1] - height),
                position  # Close the box
            ]
            
            layout.add_lwpolyline(
                points=points,
                dxfattribs={
                    'layer': config.get('layer', 'LEGEND'),
                    'color': self.get_color_code(container.get('color', 'white')),
                    'lineweight': container.get('lineweight', 25)
                }
            )

        # Add title if specified
        title = config.get('title')
        if title:
            title_style = style.get('title', {})
            text_height = float(title_style.get('height', 5))
            
            create_text(
                layout,
                title,
                (
                    position[0] + float(title_style.get('offsetX', 10)),
                    position[1] - float(title_style.get('offsetY', 10))
                ),
                {
                    'layer': config.get('layer', 'LEGEND'),
                    'height': text_height,
                    'color': self.get_color_code(title_style.get('color', 'white')),
                    'style': title_style.get('font', 'Standard')
                }
            )

    def _create_legend_item(self, layout: Layout,
                           position: Tuple[float, float],
                           item: Dict[str, Any],
                           style: Dict[str, Any]) -> float:
        """Create a single legend item.
        
        Args:
            layout: Target layout
            position: Item position
            item: Item configuration
            style: Legend style settings
            
        Returns:
            Height of the created item
        """
        item_style = style.get('items', {})
        symbol_style = item_style.get('symbol', {})
        text_style = item_style.get('text', {})

        # Create symbol
        symbol_type = item.get('type', 'line')
        symbol_width = float(symbol_style.get('width', 10))
        symbol_height = float(symbol_style.get('height', 5))
        
        if symbol_type == 'line':
            self._create_line_symbol(
                layout, position, symbol_width, item
            )
        elif symbol_type == 'point':
            self._create_point_symbol(
                layout, position, symbol_width, item
            )
        elif symbol_type == 'polygon':
            self._create_polygon_symbol(
                layout, position, symbol_width, symbol_height, item
            )

        # Create label
        label = item.get('label', '')
        if label:
            text_height = float(text_style.get('height', 3.5))
            create_text(
                layout,
                label,
                (
                    position[0] + symbol_width + float(text_style.get('offsetX', 5)),
                    position[1] + float(text_style.get('offsetY', -text_height/2))
                ),
                {
                    'layer': item.get('layer', 'LEGEND'),
                    'height': text_height,
                    'color': self.get_color_code(text_style.get('color', 'white')),
                    'style': text_style.get('font', 'Standard')
                }
            )

        return max(symbol_height, float(text_style.get('height', 3.5)))

    def _create_line_symbol(self, layout: Layout,
                           position: Tuple[float, float],
                           width: float,
                           item: Dict[str, Any]) -> None:
        """Create a line symbol.
        
        Args:
            layout: Target layout
            position: Symbol position
            width: Symbol width
            item: Item configuration
        """
        layout.add_line(
            start=position,
            end=(position[0] + width, position[1]),
            dxfattribs={
                'layer': item.get('layer', 'LEGEND'),
                'color': self.get_color_code(item.get('color', 'white')),
                'linetype': item.get('linetype', 'CONTINUOUS'),
                'lineweight': item.get('lineweight', 25)
            }
        )

    def _create_point_symbol(self, layout: Layout,
                           position: Tuple[float, float],
                           size: float,
                           item: Dict[str, Any]) -> None:
        """Create a point symbol.
        
        Args:
            layout: Target layout
            position: Symbol position
            size: Symbol size
            item: Item configuration
        """
        center = (
            position[0] + size/2,
            position[1]
        )
        
        layout.add_point(
            center,
            dxfattribs={
                'layer': item.get('layer', 'LEGEND'),
                'color': self.get_color_code(item.get('color', 'white'))
            }
        )

    def _create_polygon_symbol(self, layout: Layout,
                             position: Tuple[float, float],
                             width: float,
                             height: float,
                             item: Dict[str, Any]) -> None:
        """Create a polygon symbol.
        
        Args:
            layout: Target layout
            position: Symbol position
            width: Symbol width
            height: Symbol height
            item: Item configuration
        """
        points = [
            position,
            (position[0] + width, position[1]),
            (position[0] + width, position[1] - height),
            (position[0], position[1] - height),
            position  # Close the polygon
        ]
        
        layout.add_lwpolyline(
            points=points,
            dxfattribs={
                'layer': item.get('layer', 'LEGEND'),
                'color': self.get_color_code(item.get('color', 'white')),
                'lineweight': item.get('lineweight', 25)
            }
        ) 