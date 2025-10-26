#!/usr/bin/env python3
"""
Debug script to analyze text entities in a DXF file.
Helps diagnose sync issues with text inserts.
"""

import sys
import ezdxf

XDATA_APP_ID = "DXFEXPORTER"  # Must match src/dxf_utils.py

def analyze_text_entities(dxf_path, handles_to_check=None, layer_filter=None):
    """Analyze text entities in a DXF file."""
    
    print(f"\n{'='*80}")
    print(f"Analyzing DXF file: {dxf_path}")
    print(f"{'='*80}\n")
    
    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        print(f"❌ Error reading DXF file: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Document info
    print(f"\n{'─'*80}")
    print("DOCUMENT INFORMATION")
    print(f"{'─'*80}\n")
    print(f"  DXF Version: {doc.dxfversion}")
    print(f"  File exists: {doc is not None}")
    try:
        print(f"  Header vars: $ACADVER={doc.header.get('$ACADVER', 'N/A')}, $MEASUREMENT={doc.header.get('$MEASUREMENT', 'N/A')}")
    except:
        print(f"  Header vars: Error reading")
    
    # Check XDATA app registration
    print(f"\n{'─'*80}")
    print("XDATA APP REGISTRATION")
    print(f"{'─'*80}\n")
    print(f"  Expected XDATA_APP_ID: {XDATA_APP_ID}")
    print(f"  Is registered in doc.appids: {XDATA_APP_ID in doc.appids}")
    
    all_appids = []
    try:
        all_appids = [appid.dxf.name for appid in doc.appids]
    except:
        try:
            all_appids = list(doc.appids)
        except:
            all_appids = ["Error reading appids"]
    
    print(f"  All registered appids ({len(all_appids)}): {all_appids}")
    
    # Check if there are similar app IDs
    for appid in all_appids:
        if 'PYTHON' in str(appid).upper() or 'DXF' in str(appid).upper() or 'EXPORT' in str(appid).upper():
            print(f"  ⚠️  Found related appid: {appid}")
    print()
    
    # Check specific handles if provided
    if handles_to_check:
        print(f"\n{'─'*80}")
        print("CHECKING SPECIFIC HANDLES")
        print(f"{'─'*80}\n")
        
        for handle in handles_to_check:
            print(f"\n🔍 Looking for handle: {handle}")
            
            # Try to find in modelspace
            try:
                entity = doc.modelspace().get_entity_by_handle(handle)
                print(f"  ✅ Found in MODELSPACE")
                print_entity_details(entity, "  ")
            except:
                print(f"  ❌ Not found in modelspace")
            
            # Try to find in paperspace
            try:
                entity = doc.paperspace().get_entity_by_handle(handle)
                print(f"  ✅ Found in PAPERSPACE")
                print_entity_details(entity, "  ")
            except:
                print(f"  ❌ Not found in paperspace")
            
            # Try to find in all layouts
            found_in_layout = False
            for layout in doc.layouts:
                try:
                    entity = layout.get_entity_by_handle(handle)
                    print(f"  ✅ Found in LAYOUT: {layout.name}")
                    print_entity_details(entity, "  ")
                    found_in_layout = True
                    break
                except:
                    continue
            
            if not found_in_layout:
                print(f"  ❌ Not found in any layout")
    
    # Statistics summary
    print(f"\n{'─'*80}")
    print("STATISTICS SUMMARY")
    print(f"{'─'*80}\n")
    
    stats = collect_statistics(doc, layer_filter)
    print(f"  Total MTEXT entities: {stats['total_mtext']}")
    print(f"    - In modelspace: {stats['mtext_in_msp']}")
    print(f"    - In paperspace: {stats['mtext_in_psp']}")
    if layer_filter:
        print(f"  MTEXT on layer '{layer_filter}': {stats['filtered_count']}")
    print(f"  MTEXT with XDATA ({XDATA_APP_ID}): {stats['mtext_with_xdata']}")
    print(f"  MTEXT with ANY XDATA: {stats['mtext_with_any_xdata']}")
    
    if stats['layers']:
        print(f"\n  Layers containing MTEXT:")
        for layer, count in sorted(stats['layers'].items()):
            print(f"    - {layer}: {count} entities")
    
    if stats['xdata_apps']:
        print(f"\n  XDATA apps found on MTEXT entities:")
        for app, count in sorted(stats['xdata_apps'].items()):
            print(f"    - {app}: {count} entities")
    
    print()
    
    # Analyze all MTEXT entities
    print(f"\n{'─'*80}")
    print("ALL MTEXT ENTITIES")
    print(f"{'─'*80}\n")
    
    spaces = [
        ("MODELSPACE", doc.modelspace()),
        ("PAPERSPACE", doc.paperspace())
    ]
    
    for space_name, space in spaces:
        print(f"\n📍 {space_name}:")
        print(f"{'─'*40}")
        
        mtext_entities = [e for e in space.query('MTEXT')]
        
        if layer_filter:
            mtext_entities = [e for e in mtext_entities if e.dxf.layer == layer_filter]
            print(f"  Filtering by layer: {layer_filter}")
        
        print(f"  Found {len(mtext_entities)} MTEXT entities\n")
        
        for entity in mtext_entities:
            print_entity_summary(entity, "  ")
    
    # Check all layouts
    print(f"\n{'─'*80}")
    print("ALL LAYOUTS")
    print(f"{'─'*80}\n")
    
    for layout in doc.layouts:
        if layout.name in ['Model', '*Paper_Space', '*Paper_Space0']:
            continue  # Skip already checked
        
        print(f"\n📍 LAYOUT: {layout.name}")
        print(f"{'─'*40}")
        
        mtext_entities = [e for e in layout.query('MTEXT')]
        
        if layer_filter:
            mtext_entities = [e for e in mtext_entities if e.dxf.layer == layer_filter]
        
        print(f"  Found {len(mtext_entities)} MTEXT entities\n")
        
        for entity in mtext_entities:
            print_entity_summary(entity, "  ")
    
    # Final validation checks
    print(f"\n{'─'*80}")
    print("VALIDATION CHECKS")
    print(f"{'─'*80}\n")
    
    validation = []
    
    # Check 1: XDATA app registered
    if XDATA_APP_ID in doc.appids:
        validation.append("✅ XDATA app ID is registered in document")
    else:
        validation.append(f"❌ XDATA app ID '{XDATA_APP_ID}' is NOT registered!")
    
    # Check 2: Entities have XDATA
    if stats['mtext_with_xdata'] > 0:
        validation.append(f"✅ Found {stats['mtext_with_xdata']} MTEXT entities with correct XDATA")
    else:
        validation.append(f"❌ NO MTEXT entities have correct XDATA ({XDATA_APP_ID})")
    
    # Check 3: Any XDATA at all
    if stats['mtext_with_any_xdata'] > 0:
        validation.append(f"✅ Found {stats['mtext_with_any_xdata']} MTEXT entities with some XDATA")
    else:
        validation.append(f"⚠️  NO MTEXT entities have ANY XDATA at all")
    
    # Check 4: Handles exist
    if handles_to_check:
        found_handles = sum(1 for h in handles_to_check if check_handle_exists(doc, h))
        if found_handles == len(handles_to_check):
            validation.append(f"✅ All {len(handles_to_check)} specified handles found")
        elif found_handles > 0:
            validation.append(f"⚠️  Only {found_handles}/{len(handles_to_check)} specified handles found")
        else:
            validation.append(f"❌ NONE of the {len(handles_to_check)} specified handles found")
    
    for check in validation:
        print(f"  {check}")
    
    print(f"\n{'='*80}")
    print("Analysis complete!")
    print(f"{'='*80}\n")

def collect_statistics(doc, layer_filter=None):
    """Collect comprehensive statistics about MTEXT entities."""
    stats = {
        'total_mtext': 0,
        'mtext_in_msp': 0,
        'mtext_in_psp': 0,
        'filtered_count': 0,
        'mtext_with_xdata': 0,
        'mtext_with_any_xdata': 0,
        'layers': {},
        'xdata_apps': {}
    }
    
    spaces = [
        ('msp', doc.modelspace()),
        ('psp', doc.paperspace())
    ]
    
    for space_name, space in spaces:
        for entity in space.query('MTEXT'):
            stats['total_mtext'] += 1
            
            if space_name == 'msp':
                stats['mtext_in_msp'] += 1
            else:
                stats['mtext_in_psp'] += 1
            
            # Layer count
            layer = entity.dxf.layer
            stats['layers'][layer] = stats['layers'].get(layer, 0) + 1
            
            # Filter count
            if not layer_filter or layer == layer_filter:
                stats['filtered_count'] += 1
            
            # XDATA count
            if entity.has_xdata(XDATA_APP_ID):
                stats['mtext_with_xdata'] += 1
            
            # Any XDATA
            try:
                if hasattr(entity, 'xdata') and entity.xdata:
                    stats['mtext_with_any_xdata'] += 1
                    for app_id in entity.xdata.keys():
                        stats['xdata_apps'][app_id] = stats['xdata_apps'].get(app_id, 0) + 1
            except:
                pass
    
    return stats

def print_entity_summary(entity, indent=""):
    """Print a summary of an entity."""
    handle = entity.dxf.handle
    layer = entity.dxf.layer
    text = entity.text[:50] + "..." if len(entity.text) > 50 else entity.text
    text = text.replace('\n', '\\n')
    
    print(f"{indent}Handle: {handle} | Layer: {layer}")
    print(f"{indent}Text: {text}")
    
    # Check owner
    try:
        owner = entity.dxf.owner
        print(f"{indent}Owner: {owner}")
    except:
        pass
    
    # Check for ALL XDATA apps
    all_xdata_apps = []
    try:
        if hasattr(entity, 'xdata'):
            all_xdata_apps = list(entity.xdata.keys()) if entity.xdata else []
    except:
        pass
    
    if all_xdata_apps:
        print(f"{indent}All XDATA apps: {all_xdata_apps}")
        # Show XDATA for each app
        for app_id in all_xdata_apps:
            try:
                xdata = entity.get_xdata(app_id)
                print(f"{indent}  {app_id}: {len(xdata)} items")
            except:
                print(f"{indent}  {app_id}: Error reading")
    
    # Check for our specific XDATA
    if entity.has_xdata(XDATA_APP_ID):
        xdata_list = entity.get_xdata(XDATA_APP_ID)
        xdata_name = None
        xdata_values = []
        
        for i, item in enumerate(xdata_list):
            xdata_values.append(f"{item[0]}:{item[1][:30] if len(str(item[1])) > 30 else item[1]}")
            # Look for ENTITY_NAME_KEY pattern
            if item[0] == 1000 and i+1 < len(xdata_list):
                if item[1] == 'ENTITY_NAME':
                    xdata_name = xdata_list[i+1][1]
        
        if xdata_name:
            print(f"{indent}✅ XDATA Name: {xdata_name}")
        else:
            print(f"{indent}⚠️  XDATA: Present but no name - {', '.join(xdata_values[:3])}")
    else:
        print(f"{indent}❌ XDATA ({XDATA_APP_ID}): None")
    
    # Check hyperlink
    try:
        hyperlink = entity.get_hyperlink()
        if hyperlink:
            print(f"{indent}🔗 Hyperlink: {hyperlink}")
    except:
        pass
    
    print()

def print_entity_details(entity, indent=""):
    """Print detailed information about an entity."""
    print(f"{indent}Entity Type: {entity.dxftype()}")
    print(f"{indent}Handle: {entity.dxf.handle}")
    print(f"{indent}Layer: {entity.dxf.layer}")
    
    # Check entity owner/space
    try:
        owner = entity.dxf.owner
        print(f"{indent}Owner handle: {owner}")
    except:
        print(f"{indent}Owner handle: N/A")
    
    # Check if entity is in document database
    if hasattr(entity, 'doc') and entity.doc:
        print(f"{indent}In document database: Yes")
        try:
            db_entity = entity.doc.entitydb.get(entity.dxf.handle)
            print(f"{indent}DB lookup successful: {db_entity is not None}")
        except:
            print(f"{indent}DB lookup: Failed")
    else:
        print(f"{indent}In document database: No doc reference")
    
    if hasattr(entity.dxf, 'insert'):
        print(f"{indent}Position: ({entity.dxf.insert.x}, {entity.dxf.insert.y})")
    
    if entity.dxftype() == 'MTEXT':
        print(f"{indent}Text: {repr(entity.text[:100])}")
        print(f"{indent}Full text length: {len(entity.text)} chars")
    
    # Check hyperlink
    try:
        hyperlink = entity.get_hyperlink()
        if hyperlink:
            print(f"{indent}Hyperlink: {hyperlink}")
        else:
            print(f"{indent}Hyperlink: None")
    except:
        print(f"{indent}Hyperlink: N/A (not supported)")
    
    # Print ALL XDATA apps for this entity
    all_xdata_apps = []
    try:
        if hasattr(entity, 'xdata'):
            all_xdata_apps = list(entity.xdata.keys()) if entity.xdata else []
    except:
        pass
    
    if all_xdata_apps:
        print(f"{indent}XDATA apps present: {all_xdata_apps}")
    else:
        print(f"{indent}XDATA apps present: None")
    
    # Print specific XDATA for our app
    if entity.has_xdata(XDATA_APP_ID):
        print(f"{indent}XDATA ({XDATA_APP_ID}):")
        xdata_list = entity.get_xdata(XDATA_APP_ID)
        for i, item in enumerate(xdata_list):
            print(f"{indent}  [{i}] {item}")
    else:
        print(f"{indent}XDATA ({XDATA_APP_ID}): None")

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_text_entities.py <dxf_file> [handle1,handle2,...] [layer_name]")
        print("\nExample:")
        print("  python debug_text_entities.py output.dxf 601057,601056 Plantext")
        sys.exit(1)
    
    dxf_path = sys.argv[1]
    
    handles_to_check = None
    if len(sys.argv) >= 3:
        handles_to_check = sys.argv[2].split(',')
    
    layer_filter = None
    if len(sys.argv) >= 4:
        layer_filter = sys.argv[3]
    
    analyze_text_entities(dxf_path, handles_to_check, layer_filter)

def check_handle_exists(doc, handle):
    """Check if a handle exists in any space."""
    spaces = [doc.modelspace(), doc.paperspace()]
    for space in spaces:
        try:
            entity = space.get_entity_by_handle(handle)
            if entity:
                return True
        except:
            continue
    
    # Also check all layouts
    for layout in doc.layouts:
        try:
            entity = layout.get_entity_by_handle(handle)
            if entity:
                return True
        except:
            continue
    
    return False

if __name__ == "__main__":
    main()

