#!/usr/bin/env python3
"""
Create a minimal DXF file for testing sync auto functionality.
"""

import sys
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def create_minimal_dxf():
    """Create a minimal DXF file with basic setup."""
    
    # Create new DXF document
    doc = ezdxf.new('R2013')
    
    # Get model and paper spaces
    msp = doc.modelspace()
    psp = doc.paperspace()
    
    # Create basic layers
    doc.layers.new('TEXT_LAYER', dxfattribs={'color': 7})  # white
    doc.layers.new('BLOCK_LAYER', dxfattribs={'color': 2})  # yellow
    doc.layers.new('VIEWPORT_LAYER', dxfattribs={'color': 4})  # cyan
    
    # Create a simple block definition for testing
    block_def = doc.blocks.new('STANDARD_BLOCK')
    block_def.add_circle(center=(0, 0), radius=5, dxfattribs={'layer': 'BLOCK_LAYER'})
    
    # Add some basic geometry to model space for viewport content
    msp.add_line((0, 0), (100, 100), dxfattribs={'layer': '0'})
    msp.add_circle((50, 50), 25, dxfattribs={'layer': '0'})
    
    # Save the DXF file
    doc.saveas('test_data/sync_auto_test.dxf')
    print("✅ Created minimal test DXF: test_data/sync_auto_test.dxf")

if __name__ == "__main__":
    create_minimal_dxf() 