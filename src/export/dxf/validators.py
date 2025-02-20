"""DXF-specific validation."""

from src.core.style_manager import StyleValidator

class DXFStyleValidator(StyleValidator):
    """DXF-specific style validation implementation."""
    
    def validate_text_height(self, height: float) -> bool:
        """Validate text height for DXF.
        
        Args:
            height: Text height value
            
        Returns:
            True if valid for DXF
        """
        # DXF text height constraints
        return 0.1 <= height <= 1000.0
    
    def validate_line_weight(self, weight: float) -> bool:
        """Validate line weight for DXF.
        
        Args:
            weight: Line weight value
            
        Returns:
            True if valid for DXF
        """
        # DXF specific line weight values (-3 to 211)
        return -3 <= weight <= 211
    
    def validate_transparency(self, value: float) -> bool:
        """Validate transparency for DXF.
        
        Args:
            value: Transparency value
            
        Returns:
            True if valid for DXF
        """
        # DXF transparency is 0-255
        return 0 <= value <= 255 