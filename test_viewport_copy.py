#!/usr/bin/env python3
"""
Test script to simulate viewport copying with stale XDATA.
This replicates what happens when you duplicate a viewport in AutoCAD.
"""

import ezdxf
from src.dxf_utils import attach_custom_data, XDATA_APP_ID
from src.viewport_manager import ViewportManager
from src.project_loader import ProjectLoader
import tempfile
import os

def create_test_dxf_with_copied_viewport():
    """Create a test DXF file with a copied viewport (stale XDATA)."""

    # Create new DXF document
    doc = ezdxf.new('R2010')
    paper_space = doc.paperspace()

    # Register our XDATA app
    doc.appids.new(XDATA_APP_ID)

    # Create original viewport
    original_vp = paper_space.add_viewport(
        center=(100, 100),
        size=(200, 150),
        view_center_point=(1000, 1000, 0),
        view_height=300
    )
    original_vp.dxf.status = 1
    original_vp.dxf.layer = 'VIEWPORTS'

    # Attach XDATA to original (simulate app management)
    attach_custom_data(
        original_vp,
        'PYTHON_ACAD_TOOLS',
        entity_name='Viewport_005',
        entity_type='VIEWPORT',
        content_hash='original_hash_123',
        entity_handle=str(original_vp.dxf.handle)
    )

    # Add some frozen layers to test property extraction
    original_vp.frozen_layers = ['Gebäude', 'Test_Layer']

    print(f"Original viewport handle: {original_vp.dxf.handle}")

    # Create copied viewport (simulate AutoCAD copy operation)
    copied_vp = paper_space.add_viewport(
        center=(300, 100),  # Different position
        size=(200, 150),    # Same size
        view_center_point=(1200, 1000, 0),  # Different view center
        view_height=300
    )
    copied_vp.dxf.status = 1
    copied_vp.dxf.layer = 'VIEWPORTS'

    # CRITICAL: Copy the SAME XDATA from original (this is what AutoCAD does)
    # This creates the "stale XDATA" scenario
    original_xdata = original_vp.get_xdata(XDATA_APP_ID)
    if original_xdata:
        copied_vp.set_xdata(XDATA_APP_ID, original_xdata)

    # Give the copy different frozen layers to test independent extraction
    copied_vp.frozen_layers = ['Different_Layer', 'Another_Layer']

    print(f"Copied viewport handle: {copied_vp.dxf.handle}")
    print(f"Copied viewport has same XDATA name: Viewport_005")
    print(f"But different actual handle: {copied_vp.dxf.handle}")

    # Debug: Show what frozen layers are actually on each viewport
    print(f"Original viewport frozen_layers: {original_vp.frozen_layers}")
    print(f"Copied viewport frozen_layers: {copied_vp.frozen_layers}")

    return doc

def create_test_project_settings():
    """Create test project settings for viewport sync."""
    return {
        'viewports': [
            {
                'name': 'Viewport_005',
                'center': {'x': 100, 'y': 100},
                'width': 200,
                'height': 150,
                'viewCenter': {'x': 1000, 'y': 1000},
                'scale': 2.0,
                'sync': 'auto',  # CRITICAL: auto mode for copy detection
                'frozenLayers': ['Gebäude', 'Test_Layer'],
                'lockZoom': True,
                '_sync': {
                    'dxf_handle': '4302',  # This will mismatch the copied viewport
                    'content_hash': 'original_hash_123',
                    'last_sync_time': 1753453402,
                    'sync_source': 'yaml'
                }
            }
        ],
        'viewport_sync': 'auto',
        'viewport_discovery': False,  # This is NOT relevant for our case
        'viewport_deletion_policy': 'auto',
        'viewport_default_layer': 'VIEWPORTS'
    }

def create_test_dxf_with_copied_text():
    """Create a test DXF file with a copied text entity (stale XDATA)."""

    # Create new DXF document
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    # Register our XDATA app
    doc.appids.new(XDATA_APP_ID)

    # Create original text
    original_text = msp.add_text(
        'Original Text',
        dxfattribs={'insert': (100, 100), 'height': 10}
    )
    original_text.dxf.layer = 'TEXT_LAYER'

    # Attach XDATA to original
    attach_custom_data(
        original_text,
        'PYTHON_ACAD_TOOLS',
        entity_name='Text_001',
        entity_type='TEXT',
        content_hash='original_text_hash_123',
        entity_handle=str(original_text.dxf.handle)
    )

    print(f"Original text handle: {original_text.dxf.handle}")

    # Create copied text (simulate AutoCAD copy operation)
    copied_text = msp.add_text(
        'Copied Text',  # Different content
        dxfattribs={'insert': (200, 200), 'height': 10}  # Different position
    )
    copied_text.dxf.layer = 'TEXT_LAYER'

    # CRITICAL: Copy the SAME XDATA from original (this is what AutoCAD does)
    original_xdata = original_text.get_xdata(XDATA_APP_ID)
    if original_xdata:
        copied_text.set_xdata(XDATA_APP_ID, original_xdata)

    print(f"Copied text handle: {copied_text.dxf.handle}")
    print(f"Original text content: '{original_text.dxf.text}'")
    print(f"Copied text content: '{copied_text.dxf.text}'")

    return doc

def create_test_dxf_with_copied_block():
    """Create a test DXF file with a copied block insert (stale XDATA)."""

    # Create new DXF document
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    # Register our XDATA app
    doc.appids.new(XDATA_APP_ID)

    # Create a simple block definition
    block_def = doc.blocks.new('TEST_BLOCK')
    block_def.add_line((0, 0), (10, 10))

    # Create original block insert
    original_insert = msp.add_blockref(
        'TEST_BLOCK',
        insert=(100, 100),
        dxfattribs={'xscale': 1.0, 'yscale': 1.0, 'rotation': 0}
    )
    original_insert.dxf.layer = 'BLOCK_LAYER'

    # Attach XDATA to original
    attach_custom_data(
        original_insert,
        'PYTHON_ACAD_TOOLS',
        entity_name='Block_001',
        entity_type='INSERT',
        content_hash='original_block_hash_123',
        entity_handle=str(original_insert.dxf.handle)
    )

    print(f"Original block insert handle: {original_insert.dxf.handle}")

    # Create copied block insert (simulate AutoCAD copy operation)
    copied_insert = msp.add_blockref(
        'TEST_BLOCK',
        insert=(200, 200),  # Different position
        dxfattribs={'xscale': 1.5, 'yscale': 1.5, 'rotation': 45}  # Different properties
    )
    copied_insert.dxf.layer = 'BLOCK_LAYER'

    # CRITICAL: Copy the SAME XDATA from original
    original_xdata = original_insert.get_xdata(XDATA_APP_ID)
    if original_xdata:
        copied_insert.set_xdata(XDATA_APP_ID, original_xdata)

    print(f"Copied block insert handle: {copied_insert.dxf.handle}")
    print(f"Original insert position: {original_insert.dxf.insert}")
    print(f"Copied insert position: {copied_insert.dxf.insert}")

    return doc

def test_viewport_copy_detection():
    """Test the viewport copy detection logic."""

    print("=== Testing Viewport Copy Detection ===")

    # Create test DXF with copied viewport
    doc = create_test_dxf_with_copied_viewport()

    # Add a main viewport (ID=1) to test skip logic
    main_viewport = doc.paperspace().add_viewport(
        center=(50, 50),
        size=(100, 100),
        view_center_point=(0, 0, 0),
        view_height=100
    )
    main_viewport.dxf.id = 1  # Main viewport (should be skipped)

    # Create test project settings
    project_settings = create_test_project_settings()

    # Create viewport manager (need to provide required dependencies)
    name_to_aci = {}  # Mock ACI mapping
    style_manager = None  # Mock style manager

    viewport_manager = ViewportManager(
        project_settings=project_settings,
        script_identifier='PYTHON_ACAD_TOOLS',
        name_to_aci=name_to_aci,
        style_manager=style_manager
    )

    print("\n--- Before Sync ---")
    print(f"Project has {len(project_settings['viewports'])} viewport configs")

    # Run viewport sync (this should detect the copy)
    try:
        result = viewport_manager.sync_viewports(doc, doc.modelspace())

        print("\n--- After Sync ---")
        print(f"Processed {len(result)} viewports")
        print(f"Project now has {len(project_settings['viewports'])} viewport configs")

        # Check if a copy was auto-discovered
        viewport_names = [vp.get('name') for vp in project_settings['viewports']]
        print(f"Viewport names: {viewport_names}")

        if 'Viewport_005_copy' in viewport_names:
            print("✅ SUCCESS: Copy was auto-discovered!")

            # Check if properties are independent (not YAML anchors/aliases)
            original_vp_config = None
            copy_vp_config = None

            for vp in project_settings['viewports']:
                if vp.get('name') == 'Viewport_005':
                    original_vp_config = vp
                elif vp.get('name') == 'Viewport_005_copy':
                    copy_vp_config = vp

            if original_vp_config and copy_vp_config:
                original_frozen = original_vp_config.get('frozenLayers', [])
                copy_frozen = copy_vp_config.get('frozenLayers', [])

                print(f"Original frozenLayers: {original_frozen}")
                print(f"Copy frozenLayers: {copy_frozen}")

                if original_frozen != copy_frozen:
                    print("✅ SUCCESS: Properties are independent (no YAML anchors)")
                else:
                    print("⚠️  WARNING: Properties might be shared (YAML anchors)")
        else:
            print("❌ FAILED: Copy was not auto-discovered")

    except Exception as e:
        print(f"❌ ERROR during sync: {e}")
        import traceback
        traceback.print_exc()

def test_text_copy_detection():
    """Test text entity copy detection logic."""
    print("\n=== Testing Text Copy Detection ===")

    from src.text_insert_manager import TextInsertManager

    # Create test DXF with copied text
    doc = create_test_dxf_with_copied_text()

    # Create test project settings for text
    project_settings = {
        'texts': [
            {
                'name': 'Text_001',
                'text': 'Original Text',
                'position': {'type': 'absolute', 'x': 100, 'y': 100},
                'sync': 'auto',
                '_sync': {
                    'dxf_handle': '30',  # This will mismatch the copied text
                    'content_hash': 'original_text_hash_123',
                    'last_sync_time': 1753453402,
                    'sync_source': 'yaml'
                }
            }
        ],
        'text_sync': 'auto',
        'text_discovery': False,
        'text_deletion_policy': 'auto',
        'text_default_layer': 'TEXT_LAYER'
    }

    # Create text manager
    style_manager = None  # Mock
    name_to_aci = {}  # Mock

    text_manager = TextInsertManager(
        project_settings=project_settings,
        script_identifier='PYTHON_ACAD_TOOLS',
        style_manager=style_manager,
        name_to_aci=name_to_aci
    )

    print(f"Project has {len(project_settings['texts'])} text configs")

    # Run text sync
    try:
        result = text_manager.process_entities(doc, doc.modelspace())

        print(f"Processed {len(result)} text entities")
        print(f"Project now has {len(project_settings['texts'])} text configs")

        text_names = [txt.get('name') for txt in project_settings['texts']]
        print(f"Text names: {text_names}")

        if 'Text_001_copy' in text_names:
            print("✅ SUCCESS: Text copy was auto-discovered!")
        else:
            print("❌ FAILED: Text copy was not auto-discovered")

    except Exception as e:
        print(f"❌ ERROR during text sync: {e}")
        import traceback
        traceback.print_exc()

def test_block_copy_detection():
    """Test block insert copy detection logic."""
    print("\n=== Testing Block Copy Detection ===")

    from src.block_insert_manager import BlockInsertManager
    from src.project_loader import ProjectLoader

    # Create test DXF with copied block
    doc = create_test_dxf_with_copied_block()

    # Find the actual handle of the original block (first block insert created)
    original_handle = None
    for insert in doc.modelspace().query('INSERT'):
        if str(insert.dxf.insert) == "(100.0, 100.0, 0.0)":  # Original position
            original_handle = str(insert.dxf.handle)
            break

    print(f"Using original handle: {original_handle}")

    # Create test project settings for blocks
    project_settings = {
        'blocks': [
            {
                'name': 'Block_001',
                'blockName': 'TEST_BLOCK',
                'position': {'type': 'absolute', 'x': 100, 'y': 100},
                'scale': 1.0,
                'rotation': 0.0,
                'sync': 'auto',
                '_sync': {
                    'dxf_handle': original_handle,  # Use actual handle from original
                    'content_hash': 'original_block_hash_123',
                    'last_sync_time': 1753453402,
                    'sync_source': 'yaml'
                }
            }
        ],
        'block_sync': 'auto',
        'block_discovery': False,
        'block_deletion_policy': 'auto',
        'block_default_layer': 'BLOCK_LAYER'
    }

    # Create mock project loader
    class MockProjectLoader:
        def __init__(self, project_settings):
            self.project_settings = project_settings

        def write_yaml_file(self, filename, data):
            print(f"Mock: Would write to {filename}")
            return True

    project_loader = MockProjectLoader(project_settings)
    all_layers = []  # Mock

    block_manager = BlockInsertManager(
        project_loader=project_loader,
        all_layers=all_layers,
        script_identifier='PYTHON_ACAD_TOOLS'
    )

    print(f"Project has {len(project_settings['blocks'])} block configs")

    # Run block sync
    try:
        result = block_manager.process_entities(doc, doc.modelspace())

        print(f"Processed {len(result)} block entities")
        print(f"Project now has {len(project_settings['blocks'])} block configs")

        block_names = [blk.get('name') for blk in project_settings['blocks']]
        print(f"Block names: {block_names}")

        if 'Block_001_copy' in block_names:
            print("✅ SUCCESS: Block copy was auto-discovered!")
        else:
            print("❌ FAILED: Block copy was not auto-discovered")

    except Exception as e:
        print(f"❌ ERROR during block sync: {e}")
        import traceback
        traceback.print_exc()

def test_rename_copy_in_yaml():
    """Test if we can rename a discovered copy in YAML and still have it work."""
    print("\n=== Testing Rename Copy in YAML ===")

    from src.viewport_manager import ViewportManager

    # First, create test DXF with copied viewport and run initial discovery
    doc = create_test_dxf_with_copied_viewport()
    project_settings = create_test_project_settings()

    # Create viewport manager
    style_manager = None
    name_to_aci = {"red": 1, "blue": 5, "green": 3}

    viewport_manager = ViewportManager(
        project_settings=project_settings,
        script_identifier='PYTHON_ACAD_TOOLS',
        style_manager=style_manager,
        name_to_aci=name_to_aci
    )

    print("🔄 Step 1: Running initial sync to discover copy...")
    result = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

    print(f"After initial sync: {len(project_settings['viewports'])} viewports")
    viewport_names = [vp.get('name') for vp in project_settings['viewports']]
    print(f"Viewport names: {viewport_names}")

    # Find the copy that was auto-discovered
    copy_config = None
    for vp in project_settings['viewports']:
        if vp.get('name', '').endswith('_copy'):
            copy_config = vp
            break

    if not copy_config:
        print("❌ FAILED: No copy was discovered in step 1")
        return

    original_copy_name = copy_config['name']
    print(f"✅ Found auto-discovered copy: '{original_copy_name}'")

    # Step 2: Rename the copy in YAML
    new_name = "Viewport_005_renamed"
    print(f"🏷️ Step 2: Renaming '{original_copy_name}' to '{new_name}' in YAML...")
    copy_config['name'] = new_name

    # Step 3: Run sync again to see if it still works
    print("🔄 Step 3: Running sync again after rename...")

    try:
        result2 = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

        print(f"After rename sync: {len(project_settings['viewports'])} viewports")
        viewport_names_after = [vp.get('name') for vp in project_settings['viewports']]
        print(f"Viewport names after rename: {viewport_names_after}")

        # Check if the renamed entity still exists and works
        if new_name in viewport_names_after:
            print(f"✅ SUCCESS: Renamed copy '{new_name}' still works!")

            # Check if the XDATA was updated to match the new name
            for viewport in doc.layouts.get('Layout1').query('VIEWPORT'):
                if viewport.dxf.id == 1:  # Skip main viewport
                    continue

                xdata = viewport.get_xdata(XDATA_APP_ID)
                if xdata:
                    # Find entity_name in XDATA
                    for i, (code, value) in enumerate(xdata):
                        if code == 1000 and value == "entity_name" and i+1 < len(xdata):
                            entity_name_in_xdata = xdata[i+1][1]
                            print(f"XDATA entity_name: '{entity_name_in_xdata}'")

                            if entity_name_in_xdata == new_name:
                                print("✅ SUCCESS: XDATA was updated to match new name!")
                            else:
                                print(f"⚠️ WARNING: XDATA still has old name '{entity_name_in_xdata}' instead of '{new_name}'")
                            break
        else:
            print(f"❌ FAILED: Renamed copy '{new_name}' not found after sync")

        # Check if old name is gone
        if original_copy_name in viewport_names_after:
            print(f"⚠️ WARNING: Old name '{original_copy_name}' still exists")
        else:
            print(f"✅ SUCCESS: Old name '{original_copy_name}' was properly removed")

    except Exception as e:
        print(f"❌ ERROR during rename sync: {e}")
        import traceback
        traceback.print_exc()

def test_rename_via_rediscovery():
    """Test renaming by deleting the copy config and letting the system re-discover it."""
    print("\n=== Testing Rename via Re-discovery ===")

    from src.viewport_manager import ViewportManager

    # Create test DXF with copied viewport and run initial discovery
    doc = create_test_dxf_with_copied_viewport()
    project_settings = create_test_project_settings()

    # Create viewport manager
    style_manager = None
    name_to_aci = {"red": 1, "blue": 5, "green": 3}

    viewport_manager = ViewportManager(
        project_settings=project_settings,
        script_identifier='PYTHON_ACAD_TOOLS',
        style_manager=style_manager,
        name_to_aci=name_to_aci
    )

    print("🔄 Step 1: Running initial sync to discover copy...")
    result = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

    print(f"After initial sync: {len(project_settings['viewports'])} viewports")
    viewport_names = [vp.get('name') for vp in project_settings['viewports']]
    print(f"Viewport names: {viewport_names}")

    # Find and remove the copy from YAML
    copy_config = None
    for i, vp in enumerate(project_settings['viewports']):
        if vp.get('name', '').endswith('_copy'):
            copy_config = project_settings['viewports'].pop(i)
            break

    if not copy_config:
        print("❌ FAILED: No copy found to remove")
        return

    original_copy_name = copy_config['name']
    print(f"🗑️ Step 2: Removed copy '{original_copy_name}' from YAML")
    print(f"After removal: {len(project_settings['viewports'])} viewports")

    # Enable discovery to allow re-discovery
    project_settings['viewport_discovery'] = True
    print("✅ Step 3: Enabled discovery mode")

    # Run sync again - should re-discover the orphaned DXF entity
    print("🔄 Step 4: Running sync to re-discover orphaned entity...")
    result2 = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

    print(f"After re-discovery: {len(project_settings['viewports'])} viewports")
    viewport_names_after = [vp.get('name') for vp in project_settings['viewports']]
    print(f"Viewport names: {viewport_names_after}")

    # Check if a new copy was discovered
    new_copy_names = [name for name in viewport_names_after if name.endswith('_copy')]
    if new_copy_names:
        new_copy_name = new_copy_names[0]
        print(f"✅ SUCCESS: Re-discovered as '{new_copy_name}'")

        # Now we can rename it manually in YAML
        for vp in project_settings['viewports']:
            if vp.get('name') == new_copy_name:
                vp['name'] = 'Viewport_005_custom_name'
                print(f"🏷️ Step 5: Renamed to 'Viewport_005_custom_name' in YAML")
                break

        # Disable discovery and run sync again
        project_settings['viewport_discovery'] = False
        print("🔄 Step 6: Running final sync with custom name...")

        try:
            result3 = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))
            final_names = [vp.get('name') for vp in project_settings['viewports']]
            print(f"Final viewport names: {final_names}")

            if 'Viewport_005_custom_name' in final_names:
                print("❌ FAILED: Custom name still triggers deletion")
            else:
                print("⚠️ Expected: Custom name caused deletion (as before)")

        except Exception as e:
            print(f"Error in final sync: {e}")

    else:
        print("❌ FAILED: No copy was re-discovered")

def test_simple_rename():
    """Simple test just for rename functionality."""
    print("\n=== Testing Simple Rename ===")

    from src.viewport_manager import ViewportManager

    # Create test DXF with copied viewport and run initial discovery
    doc = create_test_dxf_with_copied_viewport()
    project_settings = create_test_project_settings()

    # Create viewport manager
    style_manager = None
    name_to_aci = {"red": 1, "blue": 5, "green": 3}

    viewport_manager = ViewportManager(
        project_settings=project_settings,
        script_identifier='PYTHON_ACAD_TOOLS',
        style_manager=style_manager,
        name_to_aci=name_to_aci
    )

    print("Step 1: Running initial sync to discover copy...")
    result = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

    print(f"After initial sync: {len(project_settings['viewports'])} viewports")
    viewport_names = [vp.get('name') for vp in project_settings['viewports']]
    print(f"Viewport names: {viewport_names}")

    # Find the copy that was auto-discovered
    copy_config = None
    copied_entity = None
    for vp in project_settings['viewports']:
        if vp.get('name', '').endswith('_copy'):
            copy_config = vp
            # Find the actual DXF entity
            for viewport in doc.layouts.get('Layout1').query('VIEWPORT'):
                if viewport.dxf.id == 1:  # Skip main viewport
                    continue
                if str(viewport.dxf.handle) == vp.get('_sync', {}).get('dxf_handle'):
                    copied_entity = viewport
                    break
            break

    if not copy_config or not copied_entity:
        print("❌ FAILED: No copy was discovered in step 1")
        return

    original_copy_name = copy_config['name']
    print(f"Found auto-discovered copy: '{original_copy_name}'")

    # Check XDATA before rename
    xdata = copied_entity.get_xdata(XDATA_APP_ID)
    print(f"XDATA before rename: {xdata}")

    # Step 2: Rename the copy in YAML
    new_name = "Viewport_005_renamed"
    print(f"Step 2: Renaming '{original_copy_name}' to '{new_name}' in YAML...")
    copy_config['name'] = new_name

    # Step 3: Run sync again to see if it still works
    print("Step 3: Running sync again after rename...")

    result2 = viewport_manager.process_entities(doc, doc.layouts.get('Layout1'))

    print(f"After rename sync: {len(project_settings['viewports'])} viewports")
    viewport_names_after = [vp.get('name') for vp in project_settings['viewports']]
    print(f"Viewport names after rename: {viewport_names_after}")

    # Check XDATA after rename
    xdata_after = copied_entity.get_xdata(XDATA_APP_ID)
    print(f"XDATA after rename: {xdata_after}")

    # Check results
    if new_name in viewport_names_after:
        print(f"✅ SUCCESS: Renamed copy '{new_name}' still works!")

        # Verify XDATA was updated
        name_in_xdata = None
        if xdata_after:
            in_entity_section = False
            for code, value in xdata_after:
                if code == 1000 and value == "ENTITY_NAME":  # Fixed: was "entity_name", should be "ENTITY_NAME"
                    in_entity_section = True
                elif in_entity_section and code == 1000:
                    name_in_xdata = value
                    break

        if name_in_xdata == new_name:
            print(f"✅ SUCCESS: XDATA was updated to '{name_in_xdata}'")
        else:
            print(f"⚠️ WARNING: XDATA still shows '{name_in_xdata}', expected '{new_name}'")
    else:
        print(f"❌ FAILED: Renamed copy '{new_name}' not found after sync")

if __name__ == "__main__":
    test_viewport_copy_detection()
    test_text_copy_detection()
    test_block_copy_detection()
    test_simple_rename()  # Test the new rename functionality!
