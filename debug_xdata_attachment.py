#!/usr/bin/env python3
"""
Debug XDATA attachment process to see why entities become unnamed.
"""

import sys
sys.path.append('src')
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def debug_xdata_attachment():
    """Debug the XDATA attachment process."""

    print("🔍 DEBUGGING XDATA ATTACHMENT")
    print("=" * 50)

    try:
        # Load the test DXF
        doc = ezdxf.readfile('test_data/sync_auto_test.dxf')
        msp = doc.modelspace()

        # Check if app ID is registered
        from src.dxf_utils import XDATA_APP_ID
        print(f"XDATA App ID: {XDATA_APP_ID}")

        if XDATA_APP_ID not in doc.appids:
            print(f"❌ App ID {XDATA_APP_ID} not registered!")
            doc.appids.new(XDATA_APP_ID)
            print(f"✅ Registered App ID {XDATA_APP_ID}")
        else:
            print(f"✅ App ID {XDATA_APP_ID} already registered")

        # Create a test block reference
        from src.dxf_utils import add_block_reference, attach_custom_data

        block_ref = add_block_reference(
            msp,
            'STANDARD_BLOCK',
            (400, 400),
            'BLOCK_LAYER',
            scale=1.0,
            rotation=0.0
        )

        if not block_ref:
            print(f"❌ Failed to create block reference")
            return

        print(f"✅ Created block reference with handle: {block_ref.dxf.handle}")

        # Test XDATA attachment
        print(f"\n🏷️  Testing XDATA attachment...")

        try:
            attach_custom_data(
                block_ref,
                "TestScript",
                entity_name="TestBlock_Debug",
                entity_type="BLOCK",
                content_hash="test_hash_123",
                entity_handle=str(block_ref.dxf.handle)
            )
            print(f"✅ attach_custom_data completed without error")
        except Exception as e:
            print(f"❌ attach_custom_data failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Check if XDATA was attached
        try:
            xdata = block_ref.get_xdata(XDATA_APP_ID)
            if xdata:
                print(f"✅ XDATA found on entity:")
                for code, value in xdata:
                    print(f"    {code}: {value}")
            else:
                print(f"❌ No XDATA found on entity")
        except Exception as e:
            print(f"❌ Error reading XDATA: {e}")

        # Test name extraction
        print(f"\n📝 Testing name extraction...")

        from src.sync_manager_base import SyncManagerBase
        from src.project_loader import ProjectLoader
        from src.block_insert_manager import BlockInsertManager

        # Create a block manager instance to use its method
        project_loader = ProjectLoader("SyncAutoTest")
        block_manager = BlockInsertManager(
            project_loader,
            {},
            "TestScript"
        )

        extracted_name = block_manager._get_entity_name_from_xdata(block_ref)
        print(f"Extracted name: '{extracted_name}'")

        if extracted_name == "TestBlock_Debug":
            print(f"✅ Name extraction successful")
        else:
            print(f"❌ Name extraction failed - expected 'TestBlock_Debug', got '{extracted_name}'")

        # Test orphan detection
        print(f"\n🗑️  Testing orphan detection...")

        yaml_names = {"TestBlock1"}  # Our real config name

        # Check if our test entity would be considered orphaned
        if extracted_name not in yaml_names:
            print(f"⚠️  Entity '{extracted_name}' would be considered orphaned (not in YAML names: {yaml_names})")
        else:
            print(f"✅ Entity '{extracted_name}' would NOT be considered orphaned")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_xdata_attachment()
