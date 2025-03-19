"""
Layer processor for handling layer operations and geometry processing.
"""
from typing import Dict, Any, Optional
from pathlib import Path
import geopandas as gpd
from src.core.exceptions import ProcessingError
from src.core.project import Project
from src.style import StyleManager
from src.processing.geometry_processor import GeometryProcessor
from src.processing.operations.base import BaseOperation
from src.processing.operations.buffer import BufferOperation


class LayerProcessor:
    """Handles layer processing and geometry operations."""

    def __init__(self, project: Project):
        """
        Initialize the layer processor.

        Args:
            project: Project instance
        """
        self.project = project
        self.geometry_processor = GeometryProcessor()
        self.style_manager = None
        self.layers = {}
        self.dxf_document = None

    def set_style_manager(self, style_manager: StyleManager) -> None:
        """
        Set the style manager.

        Args:
            style_manager: Style manager instance
        """
        self.style_manager = style_manager

    def set_dxf_document(self, doc: object) -> None:
        """
        Set the DXF document.

        Args:
            doc: DXF document instance
        """
        self.dxf_document = doc

    def get_dxf_document(self) -> Optional[object]:
        """
        Get the DXF document.

        Returns:
            DXF document instance or None
        """
        return self.dxf_document

    def process_layers(self) -> None:
        """Process all layers from project settings."""
        try:
            # Process geometry layers
            for layer_config in self.project.settings.get('geomLayers', []):
                layer_name = layer_config.get('name')
                if not layer_name:
                    raise ProcessingError("Layer name not specified")
                self.process_layer(layer_name, layer_config)

            # Process WMTS layers
            for layer_config in self.project.settings.get('wmtsLayers', []):
                layer_name = layer_config.get('name')
                if not layer_name:
                    raise ProcessingError("Layer name not specified")
                self.process_layer(layer_name, layer_config)

            # Process WMS layers
            for layer_config in self.project.settings.get('wmsLayers', []):
                layer_name = layer_config.get('name')
                if not layer_name:
                    raise ProcessingError("Layer name not specified")
                self.process_layer(layer_name, layer_config)

        except Exception as e:
            raise ProcessingError(f"Error processing layers: {str(e)}")

    def process_layer(self, layer_name: str, layer_config: Dict[str, Any]) -> None:
        """
        Process a layer according to its configuration.

        Args:
            layer_name: Name of the layer to process
            layer_config: Layer configuration
        """
        try:
            # Load layer data
            geometry = self._load_layer_data(layer_name, layer_config)
            if geometry is None:
                raise ProcessingError(f"No geometry found for layer {layer_name}")

            # Store layer data
            self.layers[layer_name] = {
                'config': layer_config,
                'geometry': geometry,
                'style': None
            }

            # Apply layer style
            self._apply_layer_style(layer_name)

            # Process operations
            if 'operations' in layer_config:
                for op_config in layer_config['operations']:
                    self._process_operation(layer_name, op_config)

        except Exception as e:
            raise ProcessingError(f"Error processing layer {layer_name}: {str(e)}")

    def _load_layer_data(self, layer_name: str, layer_config: Dict[str, Any]) -> Optional[object]:
        """
        Load layer data from source.

        Args:
            layer_name: Name of the layer
            layer_config: Layer configuration

        Returns:
            Loaded geometry or None if not found
        """
        # Handle legacy shapeFile format
        if 'shapeFile' in layer_config:
            file_path = layer_config['shapeFile']
            if not Path(file_path).exists():
                raise ProcessingError(f"Shapefile not found: {file_path}")

            try:
                gdf = gpd.read_file(file_path)
                return gdf.geometry.iloc[0] if not gdf.empty else None
            except Exception as e:
                raise ProcessingError(f"Error reading shapefile {file_path}: {str(e)}")

        # Handle new source format
        if 'source' in layer_config:
            source = layer_config['source']
            if source['type'] == 'shapefile':
                file_path = source['path']
                if not Path(file_path).exists():
                    raise ProcessingError(f"Shapefile not found: {file_path}")

                try:
                    gdf = gpd.read_file(file_path)
                    return gdf.geometry.iloc[0] if not gdf.empty else None
                except Exception as e:
                    raise ProcessingError(f"Error reading shapefile {file_path}: {str(e)}")

            raise ProcessingError(f"Unsupported source type: {source['type']}")

        # Handle layers with operations but no source
        if 'operations' in layer_config:
            # These layers will get their geometry from operations
            return None

        raise ProcessingError(f"No source specified for layer {layer_name}")

    def _apply_layer_style(self, layer_name: str) -> None:
        """
        Apply style to a layer.

        Args:
            layer_name: Name of the layer
        """
        if self.style_manager is None:
            return

        layer_data = self.layers.get(layer_name)
        if layer_data is None:
            return

        layer_config = layer_data['config']
        if 'style' in layer_config:
            style = self.style_manager.get_style(layer_config['style'])
            if style:
                layer_data['style'] = style

    def _process_operation(self, layer_name: str, op_config: Dict[str, Any]) -> None:
        """
        Process a layer operation.

        Args:
            layer_name: Name of the layer
            op_config: Operation configuration
        """
        op_type = op_config.get('type')
        if not op_type:
            raise ProcessingError("Operation type not specified")

        operation = self._create_operation(op_type, op_config)
        if operation is None:
            raise ProcessingError(f"Unsupported operation type: {op_type}")

        # Set geometry processor
        operation.set_geometry_processor(self.geometry_processor)

        # Process operation
        layer_data = self.layers.get(layer_name)
        if layer_data is None:
            raise ProcessingError(f"Layer {layer_name} not found")

        geometry = layer_data['geometry']
        if geometry is None:
            raise ProcessingError(f"No geometry found for layer {layer_name}")

        try:
            processed_geometry = operation.process(layer_name, geometry)
            layer_data['geometry'] = processed_geometry
        except Exception as e:
            raise ProcessingError(f"Error processing operation {op_type} for layer {layer_name}: {str(e)}")

    def _create_operation(self, op_type: str, config: Dict[str, Any]) -> Optional[BaseOperation]:
        """
        Create an operation instance.

        Args:
            op_type: Type of operation
            config: Operation configuration

        Returns:
            Operation instance or None if not supported
        """
        if op_type == 'buffer':
            return BufferOperation(config)
        return None

    def get_layer_geometry(self, layer_name: str) -> Optional[object]:
        """
        Get geometry for a layer.

        Args:
            layer_name: Name of the layer

        Returns:
            Layer geometry or None if not found
        """
        layer_data = self.layers.get(layer_name)
        return layer_data['geometry'] if layer_data else None

    def set_layer_geometry(self, layer_name: str, geometry: object) -> None:
        """
        Set geometry for a layer.

        Args:
            layer_name: Name of the layer
            geometry: Geometry to set
        """
        if layer_name not in self.layers:
            self.layers[layer_name] = {
                'config': {},
                'geometry': None,
                'style': None
            }
        self.layers[layer_name]['geometry'] = geometry
