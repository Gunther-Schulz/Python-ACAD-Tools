#!/usr/bin/env python3
"""
Analyze the test DXF file to see what entities were created by sync auto.
"""

import sys
sys.path.append('ezdxf_local_bkp/src')
import ezdxf

def analyze_dxf():
    """Analyze the DXF file to see what entities exist."""
    
    try:
        doc = ezdxf.readfile('test_data/sync_auto_test.dxf')
        
        print("🔍 ANALYZING TEST DXF FILE")
        print("=" * 50)
        
        # Analyze modelspace
        msp = doc.modelspace()
        print(f"\n📐 MODELSPACE ENTITIES:")
        modelspace_entities = list(msp)
        print(f"  Total entities: {len(modelspace_entities)}")
        
        for entity in modelspace_entities:
            entity_type = entity.dxftype()
            layer = getattr(entity.dxf, 'layer', 'N/A')
            
            if entity_type == 'INSERT':
                block_name = getattr(entity.dxf, 'name', 'N/A') 
                insert_point = getattr(entity.dxf, 'insert', (0, 0, 0))
                print(f"    🧱 {entity_type}: block='{block_name}', layer='{layer}', pos={insert_point[:2]}")
            elif entity_type in ['TEXT', 'MTEXT']:
                text_content = getattr(entity.dxf, 'text', getattr(entity, 'plain_text', lambda: 'N/A')())
                insert_point = getattr(entity.dxf, 'insert', (0, 0, 0))
                print(f"    📝 {entity_type}: text='{text_content}', layer='{layer}', pos={insert_point[:2]}")
            else:
                print(f"    ⚪ {entity_type}: layer='{layer}'")
        
        # Analyze paperspace
        psp = doc.paperspace()
        print(f"\n📄 PAPERSPACE ENTITIES:")
        paperspace_entities = list(psp)
        print(f"  Total entities: {len(paperspace_entities)}")
        
        for entity in paperspace_entities:
            entity_type = entity.dxftype()
            layer = getattr(entity.dxf, 'layer', 'N/A')
            
            if entity_type == 'INSERT':
                block_name = getattr(entity.dxf, 'name', 'N/A')
                insert_point = getattr(entity.dxf, 'insert', (0, 0, 0))
                print(f"    🧱 {entity_type}: block='{block_name}', layer='{layer}', pos={insert_point[:2]}")
            elif entity_type in ['TEXT', 'MTEXT']:
                text_content = getattr(entity.dxf, 'text', getattr(entity, 'plain_text', lambda: 'N/A')())
                insert_point = getattr(entity.dxf, 'insert', (0, 0, 0))
                print(f"    📝 {entity_type}: text='{text_content}', layer='{layer}', pos={insert_point[:2]}")
            elif entity_type == 'VIEWPORT':
                center = getattr(entity.dxf, 'center', (0, 0, 0))
                size = (getattr(entity.dxf, 'width', 0), getattr(entity.dxf, 'height', 0))
                print(f"    🪟 {entity_type}: layer='{layer}', center={center[:2]}, size={size}")
            else:
                print(f"    ⚪ {entity_type}: layer='{layer}'")
        
        # Check if our test entities were created
        print(f"\n🎯 EXPECTED ENTITIES CHECK:")
        
        # Look for test text
        found_test_text = False
        for entity in paperspace_entities:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_content = getattr(entity.dxf, 'text', getattr(entity, 'plain_text', lambda: '')())
                if 'Hello Sync Auto' in text_content:
                    found_test_text = True
                    print(f"  ✅ Found test text: '{text_content}'")
                    break
        if not found_test_text:
            print(f"  ❌ Test text 'Hello Sync Auto' not found")
        
        # Look for test block
        found_test_block = False
        for entity in modelspace_entities:
            if entity.dxftype() == 'INSERT':
                block_name = getattr(entity.dxf, 'name', '')
                if block_name == 'STANDARD_BLOCK':
                    found_test_block = True
                    print(f"  ✅ Found test block: '{block_name}'")
                    break
        if not found_test_block:
            print(f"  ❌ Test block 'STANDARD_BLOCK' not found")
        
        # Look for test viewport
        found_test_viewport = False
        for entity in paperspace_entities:
            if entity.dxftype() == 'VIEWPORT':
                viewport_id = getattr(entity.dxf, 'id', None)
                if viewport_id != 1:  # Skip main viewport
                    found_test_viewport = True
                    print(f"  ✅ Found test viewport (ID: {viewport_id})")
                    break
        if not found_test_viewport:
            print(f"  ❌ Test viewport not found")
        
    except Exception as e:
        print(f"❌ Error analyzing DXF: {e}")

if __name__ == "__main__":
    analyze_dxf() 