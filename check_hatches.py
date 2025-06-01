#!/usr/bin/env python3

import sys
sys.path.append('src')
import ezdxf
from src.dxf_utils import is_created_by_script, SCRIPT_IDENTIFIER

# Check the actual Waren DXF file for hatches (from project.yaml)
dxf_path = '/home/g/hidrive/Öffentlich Planungsbüro Schulz/Projekte/22-20 Maxsolar - Waren, Grabowhöfe/Zeichnung/25 05.31 Warenshof Zeichnung_edit4.dxf'

try:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    print('=== CHECKING EXISTING HATCHES IN WAREN DXF ===')
    hatches_found = 0
    script_hatches = 0
    hatch_layers = {}

    for entity in doc.entitydb.values():
        if hasattr(entity, 'dxf') and entity.dxftype() == 'HATCH':
            hatches_found += 1
            layer = getattr(entity.dxf, 'layer', 'NO_LAYER')
            handle = getattr(entity.dxf, 'handle', 'NO_HANDLE')

            # Count hatches per layer
            if layer not in hatch_layers:
                hatch_layers[layer] = 0
            hatch_layers[layer] += 1

            print(f'Hatch {hatches_found}: Layer={layer}, Handle={handle}')

            # Check if it has our script XDATA
            try:
                xdata = entity.get_xdata('DXFEXPORTER')
                if xdata:
                    print(f'  XDATA found: {xdata}')
                    if is_created_by_script(entity, SCRIPT_IDENTIFIER):
                        script_hatches += 1
                        print(f'  ✅ Created by script')
                    else:
                        print(f'  ❌ NOT created by script')
                else:
                    print(f'  ❌ No XDATA found')
            except Exception as e:
                print(f'  Error checking XDATA: {e}')

    print(f'\nSUMMARY:')
    print(f'Total hatches found: {hatches_found}')
    print(f'Script-created hatches: {script_hatches}')
    print(f'Non-script hatches: {hatches_found - script_hatches}')
    print(f'\nHATCHES BY LAYER:')
    for layer, count in hatch_layers.items():
        print(f'  {layer}: {count} hatches')

except FileNotFoundError:
    print(f'DXF file not found: {dxf_path}')
except Exception as e:
    print(f'Error: {e}')
