#!/usr/bin/env python3
"""
Check what block definitions exist in the test DXF file.
"""

import sys
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def check_blocks():
    """Check what blocks are available in the DXF."""

    try:
        doc = ezdxf.readfile('test_data/sync_auto_test.dxf')

        print("🔍 CHECKING BLOCK DEFINITIONS")
        print("=" * 50)

        # List all blocks
        blocks = list(doc.blocks)
        print(f"Total blocks: {len(blocks)}")

        print(f"\nBlock definitions:")
        for block in blocks:
            block_name = block.name
            entities_count = len(list(block))
            print(f"  📦 {block_name}: {entities_count} entities")

            # Check if this is our STANDARD_BLOCK
            if block_name == 'STANDARD_BLOCK':
                print(f"    ✅ Found STANDARD_BLOCK!")
                for entity in block:
                    print(f"      - {entity.dxftype()}: layer={getattr(entity.dxf, 'layer', 'N/A')}")

        # Check if STANDARD_BLOCK exists
        if 'STANDARD_BLOCK' in doc.blocks:
            print(f"\n✅ STANDARD_BLOCK is available for block references")
        else:
            print(f"\n❌ STANDARD_BLOCK is NOT available!")
            print(f"Available blocks: {[b.name for b in blocks]}")

    except Exception as e:
        print(f"❌ Error checking blocks: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_blocks()
