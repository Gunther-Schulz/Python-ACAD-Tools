from pathlib import Path
from typing import Dict, Any, Optional, List
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from ...core import DocumentManager, ConfigManager
from ...utils.logging import get_logger
from .operations import OperationManager

logger = get_logger(__name__)

class LayerProcessor:
    """Processes layers according to configuration."""
    
    def __init__(self, doc_manager: DocumentManager, config_manager: ConfigManager):
        """Initialize layer processor.
        
        Args:
            doc_manager: Document manager instance
            config_manager: Configuration manager instance
        """
        self.doc_manager = doc_manager
        self.config_manager = config_manager
        self.operation_manager = OperationManager()
        
        # Cache for processed layers
        self._processed_layers: Dict[str, bool] = {}
    
    def process_layer(self, layer_name: str, layer_config: Dict[str, Any]) -> None:
        """Process a single layer according to its configuration.
        
        Args:
            layer_name: Name of the layer
            layer_config: Layer configuration dictionary
            
        Raises:
            ValueError: If layer processing fails
        """
        if layer_name in self._processed_layers:
            logger.debug(f"Layer already processed: {layer_name}")
            return
        
        try:
            doc = self.doc_manager.get_document()
            msp = self.doc_manager.get_modelspace()
            
            # Create layer if it doesn't exist
            if layer_name not in doc.layers:
                logger.info(f"Creating new layer: {layer_name}")
                doc.layers.new(layer_name)
            
            # Apply style if specified
            if 'style' in layer_config:
                style_name = layer_config['style']
                style_config = self.config_manager.get_style(style_name)
                
                if style_config:
                    layer = doc.layers.get(layer_name)
                    
                    # Apply style properties
                    if style_config.color is not None:
                        layer.color = style_config.color
                    if style_config.linetype is not None:
                        layer.linetype = style_config.linetype
                    if style_config.lineweight is not None:
                        layer.lineweight = style_config.lineweight
                    
                    layer.plot = style_config.plot
                    layer.locked = style_config.locked
                    layer.frozen = style_config.frozen
                    layer.on = style_config.is_on
                    
                    # Apply transparency if supported
                    if hasattr(layer, 'transparency'):
                        layer.transparency = style_config.transparency
            
            # Process operations if specified
            if 'operations' in layer_config:
                for operation in layer_config['operations']:
                    op_type = operation.get('type')
                    if not op_type:
                        continue
                    
                    logger.info(f"Processing operation '{op_type}' for layer: {layer_name}")
                    self.operation_manager.execute_operation(
                        op_type,
                        doc,
                        msp,
                        layer_name,
                        operation
                    )
            
            self._processed_layers[layer_name] = True
            logger.info(f"Successfully processed layer: {layer_name}")
            
        except Exception as e:
            raise ValueError(f"Error processing layer '{layer_name}': {e}") from e
    
    def process_layers(self, layer_configs: Dict[str, Dict[str, Any]]) -> None:
        """Process multiple layers according to their configurations.
        
        Args:
            layer_configs: Dictionary of layer configurations
            
        Raises:
            ValueError: If layer processing fails
        """
        for layer_name, layer_config in layer_configs.items():
            try:
                self.process_layer(layer_name, layer_config)
            except ValueError as e:
                logger.error(f"Failed to process layer '{layer_name}': {e}")
                raise
    
    def clear_cache(self) -> None:
        """Clear the processed layers cache."""
        self._processed_layers.clear()
        logger.debug("Cleared layer processing cache") 