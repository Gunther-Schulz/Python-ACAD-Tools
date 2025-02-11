"""Processor for handling geometry labeling in DXF files."""

from typing import Dict, Any, List, Optional
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPolygon

from ..labeling.placement import LabelPlacer, LabelPlacementOptions
from ..utils.logging import log_debug, log_warning

class LabelProcessor:
    """Processor for handling geometry labeling in DXF files."""

    def __init__(self, layout, style_manager):
        self.layout = layout
        self.style_manager = style_manager
        self.label_placer = LabelPlacer(layout, style_manager)

    def process_labels(self, config: Dict[str, Any], geometries: gpd.GeoDataFrame) -> None:
        """Process and add labels for geometries based on configuration.
        
        Args:
            config: Label configuration dictionary
            geometries: GeoDataFrame containing geometries to label
        """
        # Get basic configuration
        layer_name = config.get('targetLayer', 'Labels')
        style_name = config.get('style')
        
        if not style_name:
            log_warning("No style specified for labels")
            return

        # Get style configuration
        style = self.style_manager.get_style(style_name)
        if not style:
            log_warning(f"Style '{style_name}' not found")
            return

        # Get label placement options
        options = self._create_placement_options(config)

        # Process each geometry
        for idx, row in geometries.iterrows():
            if not row.geometry:
                continue

            # Get label text
            text = self._get_label_text(row, config)
            if not text:
                continue

            # Add label
            success = self.label_placer.add_label(
                text=text,
                geom=row.geometry,
                layer=layer_name,
                style=style.get('text', {}),
                options=options
            )

            if not success:
                log_warning(f"Failed to add label for geometry {idx}")

    def _create_placement_options(self, config: Dict[str, Any]) -> LabelPlacementOptions:
        """Create label placement options from configuration."""
        placement_config = config.get('placement', {})
        
        return LabelPlacementOptions(
            position=placement_config.get('position', 'centroid'),
            offset_x=placement_config.get('offset', {}).get('x', 0),
            offset_y=placement_config.get('offset', {}).get('y', 0),
            rotation=placement_config.get('rotation', 0),
            avoid_collisions=placement_config.get('avoidCollisions', True),
            min_distance=placement_config.get('minDistance', 1.0),
            label_spacing=placement_config.get('labelSpacing', 100),
            leader_line=placement_config.get('leaderLine', False),
            leader_style=placement_config.get('leaderStyle')
        )

    def _get_label_text(self, row: gpd.GeoSeries, config: Dict[str, Any]) -> Optional[str]:
        """Get label text from geometry attributes based on configuration."""
        # Check for static text
        if 'text' in config:
            return config['text']

        # Check for attribute-based text
        if 'attribute' in config:
            attr = config['attribute']
            if attr in row:
                return str(row[attr])
            else:
                log_warning(f"Attribute '{attr}' not found in geometry")
                return None

        # Check for template
        if 'template' in config:
            try:
                return config['template'].format(**row)
            except KeyError as e:
                log_warning(f"Template attribute not found in geometry: {e}")
                return None
            except Exception as e:
                log_warning(f"Error formatting label template: {e}")
                return None

        return None 