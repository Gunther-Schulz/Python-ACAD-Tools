#!/usr/bin/env python3
"""
Final test to verify sync auto is working.
"""

import sys
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def test_final_result():
    """Test if sync auto entities are now properly created."""

    try:
        doc = ezdxf.readfile('test_data/sync_auto_test.dxf')

        print("🎯 FINAL SYNC AUTO TEST RESULTS")
        print("=" * 50)

        # Current handles from latest run
        text_handle = '4B'  # From earlier - may still exist
        block_handle = '51'  # From latest run
        viewport_handle = '54'  # From latest run

        # Test text entity (should still work)
        try:
            text_entity = doc.entitydb.get(text_handle)
            if text_entity and text_entity.dxftype() in ['TEXT', 'MTEXT']:
                print(f"✅ TEXT: Found text entity (handle {text_handle})")
                if text_entity.dxftype() == 'MTEXT':
                    print(f"   Content: '{text_entity.plain_text()}'")
                else:
                    print(f"   Content: '{text_entity.dxf.text}'")
            else:
                print(f"❌ TEXT: Text entity not found (handle {text_handle})")
        except:
            print(f"❌ TEXT: Error checking text entity")

        # Test block entity
        try:
            block_entity = doc.entitydb.get(block_handle)
            if block_entity and block_entity.dxftype() == 'INSERT':
                print(f"✅ BLOCK: Found block entity (handle {block_handle})")
                print(f"   Block name: '{block_entity.dxf.name}'")
                print(f"   Position: {block_entity.dxf.insert[:2]}")
                print(f"   Layer: '{block_entity.dxf.layer}'")
            else:
                print(f"❌ BLOCK: Block entity not found (handle {block_handle})")
        except Exception as e:
            print(f"❌ BLOCK: Error checking block entity: {e}")

        # Test viewport entity
        try:
            viewport_entity = doc.entitydb.get(viewport_handle)
            if viewport_entity and viewport_entity.dxftype() == 'VIEWPORT':
                print(f"✅ VIEWPORT: Found viewport entity (handle {viewport_handle})")
                print(f"   Center: {viewport_entity.dxf.center[:2]}")
                print(f"   Size: {viewport_entity.dxf.width}x{viewport_entity.dxf.height}")
                print(f"   Layer: '{viewport_entity.dxf.layer}'")
            else:
                print(f"❌ VIEWPORT: Viewport entity not found (handle {viewport_handle})")
        except Exception as e:
            print(f"❌ VIEWPORT: Error checking viewport entity: {e}")

        print(f"\n📊 SUMMARY:")
        print(f"  Modelspace entities: {len(list(doc.modelspace()))}")
        print(f"  Paperspace entities: {len(list(doc.paperspace()))}")

        # Count our entity types
        insert_count = 0
        text_count = 0
        viewport_count = 0

        for entity in doc.modelspace():
            if entity.dxftype() == 'INSERT':
                insert_count += 1

        for entity in doc.paperspace():
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_count += 1
            elif entity.dxftype() == 'VIEWPORT':
                viewport_count += 1

        print(f"  Block inserts (modelspace): {insert_count}")
        print(f"  Text entities (paperspace): {text_count}")
        print(f"  Viewports (paperspace): {viewport_count}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_final_result()
