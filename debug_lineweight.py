#!/usr/bin/env python3

import ezdxf
from src.adapters.ezdxf_adapter import EzdxfAdapter
from src.services.logging_service import LoggingService

def main():
    # Create adapter
    logger_service = LoggingService()
    adapter = EzdxfAdapter(logger_service=logger_service)

    # Create DXF document
    doc = ezdxf.new('R2010')

    print("=== Testing Layer Lineweight ===")

    # Test 1: Create layer with lineweight 25 directly using ezdxf
    print("\n1. Direct ezdxf layer creation:")
    layer_direct = doc.layers.add("test_direct")
    print(f"   Initial lineweight: {layer_direct.dxf.lineweight}")

    layer_direct.dxf.lineweight = 25
    print(f"   After setting to 25: {layer_direct.dxf.lineweight}")

    # Test 2: Create layer using adapter
    print("\n2. Adapter layer creation:")
    try:
        adapter.create_dxf_layer(doc, "test_adapter",
            color=1,
            lineweight=25,
            linetype='Continuous'
        )
        layer_adapter = doc.layers.get("test_adapter")
        print(f"   Adapter created layer lineweight: {layer_adapter.dxf.lineweight}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test 3: Check valid lineweight constants
    print("\n3. Checking ezdxf lineweight constants:")
    try:
        from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS, LINEWEIGHT_DEFAULT
        print(f"   Valid lineweights: {VALID_DXF_LINEWEIGHTS}")
        print(f"   DEFAULT constant: {LINEWEIGHT_DEFAULT}")
        print(f"   Is 25 valid? {25 in VALID_DXF_LINEWEIGHTS}")
    except ImportError as e:
        print(f"   Could not import constants: {e}")

    # Test 4: Save and reload to see what happens
    print("\n4. Save and reload test:")
    doc.saveas("debug_lineweight_test.dxf")

    # Reload and check
    doc_reloaded = ezdxf.readfile("debug_lineweight_test.dxf")
    layer_reloaded_direct = doc_reloaded.layers.get("test_direct")
    layer_reloaded_adapter = doc_reloaded.layers.get("test_adapter")

    print(f"   Reloaded direct layer lineweight: {layer_reloaded_direct.dxf.lineweight}")
    print(f"   Reloaded adapter layer lineweight: {layer_reloaded_adapter.dxf.lineweight}")

if __name__ == "__main__":
    main()
