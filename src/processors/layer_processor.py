from typing import Dict, Any, List, Optional, Union, Tuple
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon, MultiPolygon, MultiLineString
import ezdxf
from pathlib import Path
import numpy as np

from ..core.processor import BaseProcessor
from ..core.config import ConfigManager
from ..utils.logging import log_debug, log_info, log_warning, log_error
from .label_processor import LabelProcessor
from ..core.operations import (
    create_buffer_layer, create_intersection_layer, create_union_layer,
    create_difference_layer, create_dissolve_layer, create_copy_layer,
    create_filtered_geometry_layer, create_label_association_layer,
    create_lagefaktor_layer, create_filtered_by_column_layer
)

class LayerProcessor(BaseProcessor):
    """Processor for handling layer operations."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the layer processor.
        
        Args:
            config_manager: Configuration manager instance
        """
        super().__init__(config_manager)
        self.processed_layers: Dict[str, gpd.GeoDataFrame] = {}
        self.label_processor = None  # Will be initialized when needed
        self._initialize()

    def _initialize(self) -> None:
        """Initialize layer processor resources."""
        # Create output directory if specified
        if self.config.project_config.shapefile_output_dir:
            Path(self.config.project_config.shapefile_output_dir).mkdir(
                parents=True, exist_ok=True
            )

    def process_layers(self) -> None:
        """Process all configured layers."""
        if not self.validate_document():
            return

        for layer_config in self.config.project_config.geom_layers:
            try:
                self._process_layer(layer_config)
            except Exception as e:
                log_error(f"Error processing layer {layer_config.get('name', 'unknown')}: {str(e)}")
                raise

    def _process_layer(self, layer_config: Dict[str, Any]) -> None:
        """Process a single layer configuration.
        
        Args:
            layer_config: Layer configuration dictionary
        """
        layer_name = layer_config.get('name')
        if not layer_name:
            log_error("Layer configuration missing required 'name' field")
            return

        log_info(f"Processing layer: {layer_name}")
        log_debug(f"Layer config: {layer_config}")

        # Load source data
        gdf = self._load_source_data(layer_config)
        if gdf is None or len(gdf) == 0:
            log_warning(f"No data loaded for layer {layer_name}")
            return
        
        log_debug(f"Loaded {len(gdf)} features for layer {layer_name}")

        # Apply operations
        if 'operations' in layer_config:
            log_debug(f"Applying operations for layer {layer_name}")
            gdf = self._apply_operations(gdf, layer_config['operations'])

        # Apply style
        if 'style' in layer_config:
            log_debug(f"Applying style for layer {layer_name}")
            style = self.get_style(layer_config['style'])
            self._apply_layer_style(layer_name, style)

        # Store processed layer
        self.processed_layers[layer_name] = gdf
        log_debug(f"Stored processed layer {layer_name} with {len(gdf)} features")

        # Process labels if configured
        if 'labels' in layer_config:
            log_debug(f"Found labels configuration for layer {layer_name}")
            self._process_layer_labels(layer_config['labels'], gdf)
        else:
            log_debug(f"No labels configuration found for layer {layer_name}")

        # Export to shapefile if configured
        if 'outputShapeFile' in layer_config:
            output_path = self.resolve_path(layer_config['outputShapeFile'])
            gdf.to_file(output_path)
            log_info(f"Exported layer {layer_name} to {output_path}")

    def _load_source_data(self, layer_config: Dict[str, Any]) -> Optional[gpd.GeoDataFrame]:
        """Load source data for a layer.
        
        Args:
            layer_config: Layer configuration dictionary
            
        Returns:
            GeoDataFrame with source data or None if loading fails
        """
        if 'shapeFile' in layer_config:
            shapefile_path = self.resolve_path(layer_config['shapeFile'])
            log_debug(f"Loading shapefile from: {shapefile_path}")
            try:
                gdf = gpd.read_file(shapefile_path)
                log_debug(f"Successfully loaded shapefile with {len(gdf)} features")
                
                # Transform CRS if needed
                if gdf.crs is None:
                    log_warning(f"Shapefile has no CRS defined, assuming {self.config.project_config.crs}")
                    gdf.set_crs(self.config.project_config.crs, inplace=True)
                elif gdf.crs != self.config.project_config.crs:
                    log_debug(f"Transforming CRS from {gdf.crs} to {self.config.project_config.crs}")
                    gdf = gdf.to_crs(self.config.project_config.crs)
                
                return gdf
            except Exception as e:
                log_error(f"Failed to load shapefile: {str(e)}")
                return None
        elif 'dxfLayer' in layer_config:
            return self._load_from_dxf(layer_config['dxfLayer'])
        else:
            log_warning(f"No source data specified for layer {layer_config.get('name')}")
            return None

    def _load_from_dxf(self, layer_name: str) -> gpd.GeoDataFrame:
        """Load geometries from a DXF layer.
        
        Args:
            layer_name: Name of the DXF layer
            
        Returns:
            GeoDataFrame with layer geometries
        """
        if not self.doc:
            raise ValueError("No DXF document set")

        geometries = []
        for entity in self.doc.modelspace().query(f'*[layer=="{layer_name}"]'):
            try:
                geom = self._entity_to_geometry(entity)
                if geom is not None:
                    geometries.append(geom)
            except Exception as e:
                log_warning(f"Error converting entity in layer {layer_name}: {str(e)}")

        return gpd.GeoDataFrame(geometry=geometries)

    def _entity_to_geometry(self, entity: ezdxf.entities.DXFGraphic) -> Optional[Union[Point, LineString, Polygon]]:
        """Convert a DXF entity to a Shapely geometry.
        
        Args:
            entity: DXF entity to convert
            
        Returns:
            Shapely geometry or None if conversion fails
        """
        dxftype = entity.dxftype()
        
        try:
            if dxftype == 'POINT':
                return Point(entity.dxf.location[:2])
            elif dxftype == 'LINE':
                return LineString([entity.dxf.start[:2], entity.dxf.end[:2]])
            elif dxftype == 'LWPOLYLINE':
                points = list(entity.get_points())
                if entity.closed:
                    points.append(points[0])
                return LineString(points) if len(points) >= 2 else None
            elif dxftype == 'POLYLINE':
                points = [vertex.dxf.location[:2] for vertex in entity.vertices]
                if entity.is_closed:
                    points.append(points[0])
                return LineString(points) if len(points) >= 2 else None
            elif dxftype == 'CIRCLE':
                center = Point(entity.dxf.center[:2])
                return center.buffer(entity.dxf.radius)
            else:
                log_debug(f"Unsupported entity type: {dxftype}")
                return None
        except Exception as e:
            log_warning(f"Error converting {dxftype} entity: {str(e)}")
            return None

    def _apply_operations(self, gdf: gpd.GeoDataFrame, operation: Dict[str, Any]) -> Optional[gpd.GeoDataFrame]:
        """Apply operations to a GeoDataFrame.
        
        Args:
            gdf: Input GeoDataFrame
            operation: Operation configuration
            
        Returns:
            Processed GeoDataFrame or None if operation fails
        """
        op_type = operation.get('type', '').lower()
        
        try:
            if op_type == 'buffer':
                return create_buffer_layer(gdf, operation)
            elif op_type == 'intersection':
                return create_intersection_layer(gdf, operation)
            elif op_type == 'union':
                return create_union_layer(gdf, operation)
            elif op_type == 'difference':
                return create_difference_layer(gdf, operation)
            elif op_type == 'dissolve':
                return create_dissolve_layer(gdf, operation)
            elif op_type == 'copy':
                return create_copy_layer(gdf, operation)
            elif op_type == 'filter':
                return create_filtered_geometry_layer(gdf, operation)
            elif op_type == 'labelassociation':
                return create_label_association_layer(gdf, operation)
            elif op_type == 'lagefaktor':
                return create_lagefaktor_layer(gdf, operation)
            elif op_type == 'filterbycolumn':
                return create_filtered_by_column_layer(gdf, operation)
            else:
                log_warning(f"Unknown operation type: {op_type}")
                return None
        except Exception as e:
            log_error(f"Error applying {op_type} operation: {str(e)}")
            return None

    def _apply_layer_style(self, layer_name: str, style: Dict[str, Any]) -> None:
        """Apply style properties to a DXF layer.
        
        Args:
            layer_name: Name of the layer
            style: Style properties to apply
        """
        self.apply_layer_properties(layer_name, style)

    def process_layer(self, layer, processed_layers, processing_stack=None):
        """
        Process a layer and its dependencies.
        
        Args:
            layer: Layer name or configuration dictionary
            processed_layers: Set of already processed layer names
            processing_stack: List of layers currently being processed (for cycle detection)
        """
        if processing_stack is None:
            processing_stack = []

        if isinstance(layer, str):
            layer_name = layer
            layer_obj = (
                next((l for l in self.config.project_config.geom_layers if l['name'] == layer_name), None) or
                next((l for l in self.config.project_config.wmts_layers if l['name'] == layer_name), None) or
                next((l for l in self.config.project_config.wms_layers if l['name'] == layer_name), None)
            )
        else:
            layer_name = layer['name']
            layer_obj = layer

        # Check for cycles
        if layer_name in processing_stack:
            cycle = ' -> '.join(processing_stack + [layer_name])
            log_error(f"Circular dependency detected: {cycle}")
            return

        # If already processed, skip
        if layer_name in processed_layers:
            return

        processing_stack.append(layer_name)
        log_debug(f"Processing layer: {layer_name}")
        
        try:
            # Early return for temp layers that don't exist in settings
            if layer_obj is None:
                if "_temp_" in layer_name:
                    return
                log_warning(f"Layer {layer_name} not found in project settings")
                return

            # Check for unrecognized keys
            recognized_keys = {'name', 'updateDxf', 'operations', 'shapeFile', 'type', 'sourceLayer', 
                              'outputShapeFile', 'style', 'close', 'linetypeScale', 'linetypeGeneration', 
                              'viewports', 'attributes', 'label', 'labels', 'applyHatch', 
                              'plot', 'saveToLagefaktor'}
            unrecognized_keys = set(layer_obj.keys()) - recognized_keys
            if unrecognized_keys:
                log_warning(f"Unrecognized keys in layer {layer_name}: {', '.join(unrecognized_keys)}")

            # Process style
            if 'style' in layer_obj:
                style, warning_generated = self.get_style(layer_obj['style'])
                if warning_generated:
                    log_warning(f"Issue with style for layer '{layer_name}'")
                if style is not None:
                    layer_obj['style'] = style

            # Process operations
            if 'operations' in layer_obj:
                result_geometry = None
                for operation in layer_obj['operations']:
                    if layer_obj.get('type') in ['wmts', 'wms']:
                        operation['type'] = layer_obj['type']
                    result_geometry = self._apply_operations(self.processed_layers[layer_name], operation)
                if result_geometry is not None:
                    self.processed_layers[layer_name] = result_geometry
            elif 'shapeFile' in layer_obj:
                if layer_name not in self.processed_layers:
                    log_warning(f"Shapefile for layer {layer_name} was not loaded properly")
            elif 'dxfLayer' not in layer_obj:
                self.processed_layers[layer_name] = None
                log_debug(f"Added layer {layer_name} without data")

            # Process labels if configured
            if 'labels' in layer_obj and layer_name in self.processed_layers:
                self._process_layer_labels(layer_obj['labels'], self.processed_layers[layer_name])

            if 'outputShapeFile' in layer_obj:
                self.write_shapefile(layer_name)

            if 'attributes' in layer_obj:
                if layer_name not in self.processed_layers or self.processed_layers[layer_name] is None:
                    self.processed_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=self.config.project_config.crs)
                
                gdf = self.processed_layers[layer_name]
                if 'attributes' not in gdf.columns:
                    gdf['attributes'] = None
                
                gdf['attributes'] = gdf['attributes'].apply(lambda x: {} if x is None else x)
                for key, value in layer_obj['attributes'].items():
                    gdf['attributes'] = gdf['attributes'].apply(lambda x: {**x, key: value})
                
                self.processed_layers[layer_name] = gdf

            if 'filterGeometry' in layer_obj:
                filter_config = layer_obj['filterGeometry']
                filtered_layer = create_filtered_geometry_layer(self.processed_layers, self.config.project_config, self.config.project_config.crs, layer_name, filter_config)
                if filtered_layer is not None:
                    self.processed_layers[layer_name] = filtered_layer
                log_debug(f"Applied geometry filter to layer '{layer_name}'")

        finally:
            processing_stack.remove(layer_name)
            processed_layers.add(layer_name)

    def _process_layer_labels(self, label_config: Dict[str, Any], geometries: gpd.GeoDataFrame) -> None:
        """Process labels for a layer."""
        log_debug(f"Processing labels with config: {label_config}")
        
        if not label_config.get('updateDxf', True):
            log_debug("Label processing skipped due to updateDxf=False")
            return

        if not self.doc:
            log_warning("No DXF document available for label processing")
            return

        if self.label_processor is None:
            log_debug("Initializing label processor")
            # Pass config_manager as the style manager since it has the color mapping
            self.label_processor = LabelProcessor(self.doc.modelspace(), self.config)

        try:
            log_debug(f"Attempting to process labels for {len(geometries)} geometries")
            self.label_processor.process_labels(label_config, geometries)
            log_debug("Label processing completed successfully")
        except Exception as e:
            log_error(f"Error processing labels: {str(e)}")

    def write_shapefile(self, layer_name: str) -> None:
        """Export processed layer to shapefile."""
        if layer_name not in self.processed_layers or self.processed_layers[layer_name] is None:
            log_warning(f"Layer {layer_name} not found in processed layers")
            return

        output_path = self.resolve_path(f"{layer_name}.shp")
        self.processed_layers[layer_name].to_file(output_path)
        log_info(f"Exported layer {layer_name} to {output_path}") 