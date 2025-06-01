#!/usr/bin/env python3

import sys
sys.path.append('src')
import ezdxf
from src.dxf_utils import remove_entities_by_layer, is_created_by_script, SCRIPT_IDENTIFIER

# Test the actual Waren DXF file
dxf_path = '/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/Zeichnung/25 05.31 Warenshof Zeichnung_edit4.dxf'

print("=== TESTING HATCH REMOVAL PROCESS ===")

try:
    # Load the DXF file
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # First, let's focus on one specific hatch layer for testing
    test_layer = 'Baufeld Schraffur'

    print(f"\n1. BEFORE REMOVAL - Checking '{test_layer}' layer:")

    # Count hatches on this layer before removal
    hatches_before = []
    for entity in doc.entitydb.values():
        if (hasattr(entity, 'dxf') and
            entity.dxftype() == 'HATCH' and
            entity.dxf.hasattr('layer') and
            entity.dxf.layer == test_layer):

            hatches_before.append(entity)
            is_script = is_created_by_script(entity, SCRIPT_IDENTIFIER)
            print(f"  Hatch {entity.dxf.handle}: Script-created={is_script}")

    print(f"  Total hatches found on '{test_layer}': {len(hatches_before)}")
    script_hatches_before = sum(1 for h in hatches_before if is_created_by_script(h, SCRIPT_IDENTIFIER))
    print(f"  Script-created hatches: {script_hatches_before}")

    # Test if any hatches should be removable
    if script_hatches_before == 0:
        print(f"  ❌ No script-created hatches found on '{test_layer}' - switching to different layer")

        # Try another layer
        test_layer = 'Baum_Laubbaum Stamm Schraffur'
        print(f"\n1b. CHECKING '{test_layer}' layer instead:")

        hatches_before = []
        for entity in doc.entitydb.values():
            if (hasattr(entity, 'dxf') and
                entity.dxftype() == 'HATCH' and
                entity.dxf.hasattr('layer') and
                entity.dxf.layer == test_layer):

                hatches_before.append(entity)
                is_script = is_created_by_script(entity, SCRIPT_IDENTIFIER)
                if len(hatches_before) <= 5:  # Only show first 5
                    print(f"  Hatch {entity.dxf.handle}: Script-created={is_script}")

        print(f"  Total hatches found on '{test_layer}': {len(hatches_before)}")
        script_hatches_before = sum(1 for h in hatches_before if is_created_by_script(h, SCRIPT_IDENTIFIER))
        print(f"  Script-created hatches: {script_hatches_before}")

    if script_hatches_before == 0:
        print("  ❌ Still no script-created hatches found! This is unexpected.")
        exit(1)

    print(f"\n2. TESTING REMOVAL FUNCTION:")
    print(f"  Calling remove_entities_by_layer(msp, '{test_layer}', '{SCRIPT_IDENTIFIER}')")

    # Call the removal function
    try:
        deleted_count = remove_entities_by_layer(msp, test_layer, SCRIPT_IDENTIFIER)
        print(f"  ✅ Function returned: {deleted_count} entities deleted")
    except Exception as e:
        print(f"  ❌ Function failed with error: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        exit(1)

    print(f"\n3. AFTER REMOVAL - Checking '{test_layer}' layer:")

    # Count hatches on this layer after removal
    hatches_after = []
    for entity in doc.entitydb.values():
        if (hasattr(entity, 'dxf') and
            entity.dxftype() == 'HATCH' and
            entity.dxf.hasattr('layer') and
            entity.dxf.layer == test_layer):

            hatches_after.append(entity)
            is_script = is_created_by_script(entity, SCRIPT_IDENTIFIER)
            if len(hatches_after) <= 5:  # Only show first 5
                print(f"  Hatch {entity.dxf.handle}: Script-created={is_script}")

    print(f"  Total hatches found on '{test_layer}': {len(hatches_after)}")
    script_hatches_after = sum(1 for h in hatches_after if is_created_by_script(h, SCRIPT_IDENTIFIER))
    print(f"  Script-created hatches: {script_hatches_after}")

    print(f"\n4. ANALYSIS:")
    print(f"  Hatches before removal: {len(hatches_before)} (script: {script_hatches_before})")
    print(f"  Hatches after removal:  {len(hatches_after)} (script: {script_hatches_after})")
    print(f"  Function reported deleted: {deleted_count}")
    print(f"  Actually removed: {len(hatches_before) - len(hatches_after)}")
    print(f"  Script hatches removed: {script_hatches_before - script_hatches_after}")

    if deleted_count > 0 and len(hatches_before) == len(hatches_after):
        print("  ❌ PROBLEM: Function reported deletions but hatch count unchanged!")
    elif deleted_count == 0 and script_hatches_before > 0:
        print("  ❌ PROBLEM: Function reported no deletions but script hatches exist!")
    elif script_hatches_after > 0:
        print("  ❌ PROBLEM: Script hatches still remain after removal!")
    else:
        print("  ✅ Removal appears to have worked correctly")

    # Test specific handle lookup
    if hatches_before:
        test_handle = hatches_before[0].dxf.handle
        print(f"\n5. TESTING SPECIFIC HANDLE LOOKUP:")
        print(f"  Looking for handle {test_handle} after removal...")
        try:
            entity = doc.entitydb.get(test_handle)
            if entity:
                print(f"  ❌ Entity still exists: {entity}")
            else:
                print(f"  ✅ Entity successfully removed from entitydb")
        except Exception as e:
            print(f"  ✅ Entity not found (removed): {e}")

except FileNotFoundError:
    print(f'DXF file not found: {dxf_path}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    print(f'Traceback: {traceback.format_exc()}')
