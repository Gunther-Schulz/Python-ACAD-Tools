#!/usr/bin/env python3
"""
Debug block creation process step by step.
"""

import sys
sys.path.append('src')
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def debug_block_creation():
    """Debug the block creation process step by step."""

    print("🔍 DEBUGGING BLOCK CREATION PROCESS")
    print("=" * 60)

    try:
        # Load the test DXF
        doc = ezdxf.readfile('test_data/sync_auto_test.dxf')
        msp = doc.modelspace()

        print(f"✅ Loaded DXF file")
        print(f"   Modelspace entities before: {len(list(msp))}")

        # Check if STANDARD_BLOCK exists
        if 'STANDARD_BLOCK' not in doc.blocks:
            print(f"❌ STANDARD_BLOCK not found!")
            return
        else:
            print(f"✅ STANDARD_BLOCK found")

        # Try to create a block reference manually
        from src.dxf_utils import add_block_reference

        print(f"\n🧱 Testing manual block creation...")

        block_ref = add_block_reference(
            msp,
            'STANDARD_BLOCK',
            (300, 300),  # Different position from test config
            'BLOCK_LAYER',
            scale=1.0,
            rotation=0.0
        )

        if block_ref:
            print(f"✅ Block reference created successfully!")
            print(f"   Handle: {block_ref.dxf.handle}")
            print(f"   Layer: {block_ref.dxf.layer}")
            print(f"   Position: {block_ref.dxf.insert}")
            print(f"   Block name: {block_ref.dxf.name}")

            # Check if it's in modelspace
            msp_entities_after = list(msp)
            print(f"   Modelspace entities after: {len(msp_entities_after)}")

            # Look for our block reference
            found = False
            for entity in msp_entities_after:
                if entity.dxftype() == 'INSERT' and entity.dxf.name == 'STANDARD_BLOCK':
                    print(f"   ✅ Found our block reference in modelspace!")
                    print(f"      Handle: {entity.dxf.handle}")
                    found = True
                    break

            if not found:
                print(f"   ❌ Block reference NOT found in modelspace entities")
        else:
            print(f"❌ Block reference creation FAILED!")

        # Now test with the actual sync system
        print(f"\n🔄 Testing with sync system...")

        from src.project_loader import ProjectLoader
        from src.block_insert_manager import BlockInsertManager

        project_loader = ProjectLoader("SyncAutoTest")
        block_manager = BlockInsertManager(
            project_loader,
            {},  # all_layers
            "TestScript"
        )

        # Get the block config
        block_configs = block_manager._get_entity_configs()
        if block_configs:
            config = block_configs[0]  # First block config
            print(f"   Using config: {config['name']}")

            # Test the sync push directly
            result = block_manager._sync_push(doc, msp, config)

            if result:
                print(f"   ✅ Sync push succeeded!")
                print(f"   Handle: {result.dxf.handle}")
                print(f"   Layer: {result.dxf.layer}")

                # Check if it's still in the document
                try:
                    found_entity = doc.entitydb.get(result.dxf.handle)
                    if found_entity:
                        print(f"   ✅ Entity found in document entitydb")
                    else:
                        print(f"   ❌ Entity NOT found in document entitydb")
                except Exception as e:
                    print(f"   ❌ Error checking entitydb: {e}")

            else:
                print(f"   ❌ Sync push FAILED!")
        else:
            print(f"   ❌ No block configs found")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_block_creation()
