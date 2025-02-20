"""Geometry layer configuration module."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Union
from src.core.utils import resolve_path
from src.core.types import StyleName, LayerName
from pathlib import Path

@dataclass
class GeometryOperation:
    """Configuration for a geometry operation."""
    type: str
    layers: Optional[Union[str, List[Union[str, Dict[str, List[str]]]]]] = None
    distance: Optional[float] = None
    reverse_difference: Optional[Union[bool, str]] = None
    use_buffer_trick: Optional[bool] = None
    buffer_distance: Optional[float] = None
    use_asymmetric_buffer: Optional[bool] = None
    min_area: Optional[float] = None
    params: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeometryOperation':
        """Create GeometryOperation from dictionary."""
        return cls(
            type=data['type'],
            layers=data.get('layers'),
            distance=data.get('distance'),
            reverse_difference=data.get('reverseDifference'),
            use_buffer_trick=data.get('useBufferTrick'),
            buffer_distance=data.get('bufferDistance'),
            use_asymmetric_buffer=data.get('useAsymmetricBuffer'),
            min_area=data.get('minArea'),
            params=data.get('params')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {'type': self.type}
        if self.layers is not None:
            result['layers'] = self.layers
        if self.distance is not None:
            result['distance'] = self.distance
        if self.reverse_difference is not None:
            result['reverseDifference'] = self.reverse_difference
        if self.use_buffer_trick is not None:
            result['useBufferTrick'] = self.use_buffer_trick
        if self.buffer_distance is not None:
            result['bufferDistance'] = self.buffer_distance
        if self.use_asymmetric_buffer is not None:
            result['useAsymmetricBuffer'] = self.use_asymmetric_buffer
        if self.min_area is not None:
            result['minArea'] = self.min_area
        if self.params is not None:
            result['params'] = self.params
        return result

@dataclass
class StyleConfig:
    """Configuration for layer styling."""
    layer: Optional[Dict[str, Any]] = None
    polygon: Optional[Dict[str, Any]] = None  # Renamed from 'entity' to 'polygon' - for polygon-level styling
    text: Optional[Dict[str, Any]] = None
    hatch: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StyleConfig':
        """Create StyleConfig from dictionary."""
        return cls(
            layer=data.get('layer'),
            polygon=data.get('polygon'),  # Renamed from 'entity' to 'polygon'
            text=data.get('text'),
            hatch=data.get('hatch')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        if self.layer is not None:
            result['layer'] = self.layer
        if self.polygon is not None:  # Renamed from 'entity' to 'polygon'
            result['polygon'] = self.polygon
        if self.text is not None:
            result['text'] = self.text
        if self.hatch is not None:
            result['hatch'] = self.hatch
        return result

@dataclass
class GeometryLayerConfig:
    """Configuration for a geometry layer."""
    name: LayerName
    update_dxf: bool = True
    close: bool = False
    shape_file: Optional[str] = None
    simple_label_column: Optional[str] = None
    style: Optional[StyleName] = None  # Reference to a preset style
    inline_style: Optional[StyleConfig] = None  # Inline style configuration
    operations: List[GeometryOperation] = None
    viewports: Optional[List[Dict[str, str]]] = None
    hatch_layers: Optional[List[Dict[str, Any]]] = None  # Renamed from hatches to hatch_layers

    @classmethod
    def from_dict(cls, data: Dict[str, Any], folder_prefix: Optional[str] = None) -> 'GeometryLayerConfig':
        """Create GeometryLayerConfig from dictionary."""
        # Handle paths with folder prefix
        shape_file = data.get('shapeFile')
        if shape_file and folder_prefix:
            # Expand user directory if needed
            if folder_prefix.startswith('~'):
                folder_prefix = str(Path(folder_prefix).expanduser())
            shape_file = str(Path(folder_prefix) / shape_file)
        
        operations = []
        if 'operations' in data:
            operations = [GeometryOperation.from_dict(op) for op in data['operations']]

        # Handle both style types
        style = data.get('style')  # This should now be a string (preset name)
        inline_style = None
        if 'inlineStyle' in data:
            inline_style = StyleConfig.from_dict(data['inlineStyle'])

        return cls(
            name=data['name'],
            update_dxf=data.get('updateDxf', True),
            close=data.get('close', False),
            shape_file=shape_file,
            simple_label_column=data.get('simpleLabelColumn'),
            style=style,
            inline_style=inline_style,
            operations=operations,
            viewports=data.get('viewports'),
            hatch_layers=data.get('hatchLayers')  # Updated to match YAML key
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'name': self.name,
            'updateDxf': self.update_dxf
        }
        if self.close:
            result['close'] = self.close
        if self.shape_file:
            result['shapeFile'] = self.shape_file
        if self.simple_label_column:
            result['simpleLabelColumn'] = self.simple_label_column
        if self.style:
            result['style'] = self.style
        if self.inline_style:
            result['inlineStyle'] = self.inline_style.to_dict()
        if self.operations:
            result['operations'] = [op.to_dict() for op in self.operations]
        if self.viewports:
            result['viewports'] = self.viewports
        if self.hatch_layers:
            result['hatchLayers'] = self.hatch_layers  # Updated to match YAML key
        return result 