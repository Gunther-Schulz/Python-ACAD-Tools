"""Style management module."""

from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
from src.config.style_config import StyleConfig
from src.core.utils import setup_logger

class StyleValidator(Protocol):
    """Protocol for style validation."""
    def validate_text_height(self, height: float) -> bool: ...
    def validate_line_weight(self, weight: float) -> bool: ...
    def validate_transparency(self, value: float) -> bool: ...

@dataclass
class DefaultStyleValidator:
    """Default implementation of style validation."""
    def validate_text_height(self, height: float) -> bool:
        """Validate text height."""
        return 0.1 <= height <= 1000.0
    
    def validate_line_weight(self, weight: float) -> bool:
        """Validate line weight."""
        return -100 <= weight <= 1000.0
    
    def validate_transparency(self, value: float) -> bool:
        """Validate transparency value."""
        return 0 <= value <= 1.0

class StyleManager:
    """Manages styles for the project.
    
    This class handles style management without knowledge of specific
    export formats or implementations. It provides a clean interface
    for style operations and validation.
    """
    
    def __init__(
        self,
        styles: Dict[str, StyleConfig],
        validator: Optional[StyleValidator] = None
    ):
        """Initialize with style configurations.
        
        Args:
            styles: Dictionary of style configurations
            validator: Optional style validator implementation
        """
        self.styles = styles
        self.logger = setup_logger("style_manager")
        self.validator = validator or DefaultStyleValidator()
    
    def get_style(self, style_id: str) -> Optional[StyleConfig]:
        """Get style by ID.
        
        Args:
            style_id: Style identifier
            
        Returns:
            StyleConfig if found, None otherwise
        """
        return self.styles.get(style_id)
    
    def has_style(self, style_id: str) -> bool:
        """Check if style exists.
        
        Args:
            style_id: Style identifier
            
        Returns:
            True if style exists, False otherwise
        """
        return style_id in self.styles
    
    def get_style_names(self) -> list:
        """Get list of available style names.
        
        Returns:
            List of style names
        """
        return list(self.styles.keys())
    
    def validate_style(self, style: StyleConfig) -> bool:
        """Validate style configuration.
        
        Args:
            style: Style configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Validate text properties
            if style.text_properties:
                if not self.validator.validate_text_height(style.text_properties.height):
                    self.logger.warning(f"Invalid text height: {style.text_properties.height}")
                    return False
            
            # Validate layer properties
            if style.layer_properties:
                if style.layer_properties.lineweight is not None:
                    if not self.validator.validate_line_weight(style.layer_properties.lineweight):
                        self.logger.warning(f"Invalid lineweight: {style.layer_properties.lineweight}")
                        return False
                
                if style.layer_properties.transparency is not None:
                    if not self.validator.validate_transparency(style.layer_properties.transparency):
                        self.logger.warning(f"Invalid transparency: {style.layer_properties.transparency}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Style validation error: {str(e)}")
            return False
    
    def merge_styles(self, base: StyleConfig, override: StyleConfig) -> StyleConfig:
        """Merge two styles, with override taking precedence.
        
        Args:
            base: Base style configuration
            override: Override style configuration
            
        Returns:
            Merged style configuration
        """
        # Convert to dictionaries for merging
        base_dict = base.to_dict() if base else {}
        override_dict = override.to_dict() if override else {}
        
        # Deep merge
        merged = {}
        for key in set(base_dict) | set(override_dict):
            if key in base_dict and key in override_dict:
                if isinstance(base_dict[key], dict) and isinstance(override_dict[key], dict):
                    merged[key] = self.merge_styles(base_dict[key], override_dict[key])
                else:
                    merged[key] = override_dict[key]
            elif key in base_dict:
                merged[key] = base_dict[key]
            else:
                merged[key] = override_dict[key]
        
        return StyleConfig.from_dict(merged)
    
    def validate_and_get_style(self, style_id: str) -> StyleConfig:
        """Get and validate a style.
        
        Args:
            style_id: Style identifier
            
        Returns:
            Validated StyleConfig
            
        Raises:
            ValueError: If style is not found or invalid
        """
        style = self.get_style(style_id)
        if not style:
            raise ValueError(f"Style not found: {style_id}")
        
        if not self.validate_style(style):
            raise ValueError(f"Invalid style configuration: {style_id}")
        
        return style 