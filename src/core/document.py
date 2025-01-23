from pathlib import Path
from typing import Optional, Dict, Any, List
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace

from ..utils.logging import get_logger

logger = get_logger(__name__)

class DocumentManager:
    """Manages DXF document operations."""
    
    def __init__(self):
        """Initialize document manager."""
        self.doc: Optional[Drawing] = None
        self.msp: Optional[Modelspace] = None
    
    def create_new(self) -> Drawing:
        """Create a new DXF document.
        
        Returns:
            New DXF document
        """
        try:
            self.doc = ezdxf.new('R2018')  # Using R2018 for better compatibility
            self.msp = self.doc.modelspace()
            logger.info("Created new DXF document")
            return self.doc
        except Exception as e:
            raise ValueError(f"Error creating new DXF document: {e}") from e
    
    def load(self, filepath: Path) -> Drawing:
        """Load an existing DXF document.
        
        Args:
            filepath: Path to DXF file
            
        Returns:
            Loaded DXF document
            
        Raises:
            ValueError: If file doesn't exist or has invalid format
        """
        if not filepath.exists():
            raise ValueError(f"DXF file not found: {filepath}")
        
        try:
            self.doc = ezdxf.readfile(str(filepath))
            self.msp = self.doc.modelspace()
            logger.info(f"Loaded DXF document: {filepath}")
            return self.doc
        except ezdxf.DXFError as e:
            raise ValueError(f"Error loading DXF file: {e}") from e
        except Exception as e:
            raise ValueError(f"Unexpected error loading DXF file: {e}") from e
    
    def load_or_create(self, filepath: Path) -> Drawing:
        """Load existing DXF document or create new one if it doesn't exist.
        
        Args:
            filepath: Path to DXF file
            
        Returns:
            Loaded or new DXF document
        """
        try:
            return self.load(filepath)
        except ValueError:
            logger.info(f"DXF file not found, creating new: {filepath}")
            return self.create_new()
    
    def save(self, filepath: Path) -> None:
        """Save the current document.
        
        Args:
            filepath: Path to save DXF file
            
        Raises:
            ValueError: If no document is loaded or save fails
        """
        if not self.doc:
            raise ValueError("No document loaded")
        
        try:
            # Ensure directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Save document
            self.doc.saveas(str(filepath))
            logger.info(f"Saved DXF document: {filepath}")
        except Exception as e:
            raise ValueError(f"Error saving DXF file: {e}") from e
    
    def cleanup(self) -> None:
        """Perform cleanup operations on the document.
        
        This includes:
        - Purging unused blocks, layers, linetypes, etc.
        - Validating references
        - Optimizing storage
        
        Raises:
            ValueError: If no document is loaded
        """
        if not self.doc:
            raise ValueError("No document loaded")
        
        try:
            # Purge unused elements
            self.doc.purge()
            
            # Audit and fix issues
            auditor = self.doc.audit()
            if len(auditor.errors) > 0:
                logger.warning(f"Found and fixed {len(auditor.errors)} issues in document")
            
            logger.info("Completed document cleanup")
        except Exception as e:
            raise ValueError(f"Error during document cleanup: {e}") from e
    
    def get_document(self) -> Drawing:
        """Get the current document.
        
        Returns:
            Current DXF document
            
        Raises:
            ValueError: If no document is loaded
        """
        if not self.doc:
            raise ValueError("No document loaded")
        return self.doc
    
    def get_modelspace(self) -> Modelspace:
        """Get the modelspace of the current document.
        
        Returns:
            Modelspace of current document
            
        Raises:
            ValueError: If no document is loaded
        """
        if not self.msp:
            raise ValueError("No document loaded")
        return self.msp 