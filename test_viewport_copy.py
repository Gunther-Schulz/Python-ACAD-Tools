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

if __name__ == "__main__":
    test_viewport_copy_detection()
