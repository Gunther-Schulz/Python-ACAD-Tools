"""Utilities for handling DXF document operations."""

import ezdxf
import traceback
from src.utils import log_debug, log_warning, log_error
from .style_defaults import DEFAULT_TEXT_STYLE, STANDARD_TEXT_STYLES

def set_drawing_properties(doc):
    # Set the properties
    doc.header['$MEASUREMENT'] = 1  # 1 for metric, 0 for imperial
    doc.header['$INSUNITS'] = 6  # 6 for meters
    doc.header['$LUNITS'] = 2  # 2 for decimal units
    doc.header['$LUPREC'] = 4  # Precision for linear units
    doc.header['$AUPREC'] = 4  # Precision for angular units
    
    # Define meaning of values
    measurement_meaning = {
        0: "Imperial (inches, feet)",
        1: "Metric (millimeters, meters)"
    }
    
    insunits_meaning = {
        0: "Unitless",
        1: "Inches",
        2: "Feet",
        3: "Miles",
        4: "Millimeters",
        5: "Centimeters",
        6: "Meters",
        7: "Kilometers",
        8: "Microinches",
        9: "Mils",
        10: "Yards",
        11: "Angstroms",
        12: "Nanometers",
        13: "Microns",
        14: "Decimeters",
        15: "Decameters",
        16: "Hectometers",
        17: "Gigameters",
        18: "Astronomical units",
        19: "Light years",
        20: "Parsecs"
    }
    
    lunits_meaning = {
        1: "Scientific",
        2: "Decimal",
        3: "Engineering",
        4: "Architectural",
        5: "Fractional"
    }
    
    # Log and print the settings with their meanings
    log_debug("\n=== Drawing Properties Set ===")
    
    # MEASUREMENT
    measurement_msg = f"$MEASUREMENT: {doc.header['$MEASUREMENT']} - {measurement_meaning.get(doc.header['$MEASUREMENT'], 'Unknown')}"
    log_debug(measurement_msg)
    
    # INSUNITS
    insunits_msg = f"$INSUNITS: {doc.header['$INSUNITS']} - {insunits_meaning.get(doc.header['$INSUNITS'], 'Unknown')}"
    log_debug(insunits_msg)
    
    # LUNITS
    lunits_msg = f"$LUNITS: {doc.header['$LUNITS']} - {lunits_meaning.get(doc.header['$LUNITS'], 'Unknown')}"
    log_debug(lunits_msg)
    
    # LUPREC
    luprec_msg = f"$LUPREC: {doc.header['$LUPREC']} - Linear units precision (number of decimal places)"
    log_debug(luprec_msg)
    
    # AUPREC
    auprec_msg = f"$AUPREC: {doc.header['$AUPREC']} - Angular units precision (number of decimal places)"
    log_debug(auprec_msg)
    
    log_debug("\n=== End of Drawing Properties ===")

def verify_dxf_settings(filename):
    loaded_doc = ezdxf.readfile(filename)
    
    # Define meaning of values
    measurement_meaning = {
        0: "Imperial (inches, feet)",
        1: "Metric (millimeters, meters)"
    }
    
    insunits_meaning = {
        0: "Unitless", 1: "Inches", 2: "Feet", 3: "Miles",
        4: "Millimeters", 5: "Centimeters", 6: "Meters", 7: "Kilometers",
        8: "Microinches", 9: "Mils", 10: "Yards", 11: "Angstroms",
        12: "Nanometers", 13: "Microns", 14: "Decimeters", 15: "Decameters",
        16: "Hectometers", 17: "Gigameters", 18: "Astronomical units",
        19: "Light years", 20: "Parsecs"
    }
    
    lunits_meaning = {
        1: "Scientific", 2: "Decimal", 3: "Engineering",
        4: "Architectural", 5: "Fractional"
    }

    log_debug("\n=== Verifying DXF Settings ===")

    measurement = loaded_doc.header.get('$MEASUREMENT', None)
    measurement_msg = f"$MEASUREMENT: {measurement} - {measurement_meaning.get(measurement, 'Unknown')}"
    log_debug(measurement_msg)

    insunits = loaded_doc.header.get('$INSUNITS', None)
    insunits_msg = f"$INSUNITS: {insunits} - {insunits_meaning.get(insunits, 'Unknown')}"
    log_debug(insunits_msg)

    lunits = loaded_doc.header.get('$LUNITS', None)
    lunits_msg = f"$LUNITS: {lunits} - {lunits_meaning.get(lunits, 'Unknown')}"
    log_debug(lunits_msg)

    luprec = loaded_doc.header.get('$LUPREC', None)
    luprec_msg = f"$LUPREC: {luprec} - Linear units precision (decimal places)"
    log_debug(luprec_msg)

    auprec = loaded_doc.header.get('$AUPREC', None)
    auprec_msg = f"$AUPREC: {auprec} - Angular units precision (decimal places)"
    log_debug(auprec_msg)

    log_debug("=== End of DXF Settings Verification ===\n")

def cleanup_document(doc):
    """Perform thorough document cleanup."""
    try:
        # Run audit to fix potential structural issues
        auditor = doc.audit()
        if len(auditor.errors) > 0:
            log_warning(f"Audit found {len(auditor.errors)} issues")
        
        # Clean up empty groups
        for group in doc.groups:
            if len(group) == 0:
                doc.groups.remove(group.dxf.name)
        
        # Purge unused blocks
        modelspace = doc.modelspace()
        paperspace = doc.paperspace()
        used_blocks = set()
        
        # Check modelspace for block references
        for insert in modelspace.query('INSERT'):
            used_blocks.add(insert.dxf.name)
            
        # Check paperspace for block references
        for insert in paperspace.query('INSERT'):
            used_blocks.add(insert.dxf.name)
            
        # Remove unused blocks
        for block in list(doc.blocks):
            block_name = block.name
            
            # Skip special blocks, used blocks, and AutoCAD special blocks
            if (block_name.startswith('_') or 
                block_name.startswith('*') or 
                block_name.startswith('A$C') or 
                block_name in used_blocks):
                continue
                
            try:
                doc.blocks.delete_block(block_name)
                log_debug(f"Removed unused block: {block_name}")
            except Exception as e:
                # Only log errors that aren't related to block being in use
                if "still in use" not in str(e):
                    log_warning(f"Could not remove block {block_name}: {str(e)}")
        
        # Purge unused layers
        for layer in list(doc.layers):
            layer_name = layer.dxf.name
            
            # Skip system layers (0, Defpoints)
            if layer_name in ['0', 'Defpoints']:
                continue
                
            # Check if the layer has any entities
            has_entities = False
            
            # Check modelspace
            for entity in modelspace:
                if entity.dxf.layer == layer_name:
                    has_entities = True
                    break
                    
            # If not found in modelspace, check paperspace
            if not has_entities:
                for entity in paperspace:
                    if entity.dxf.layer == layer_name:
                        has_entities = True
                        break
            
            # Remove empty layer
            if not has_entities:
                try:
                    doc.layers.remove(layer_name)
                    log_debug(f"Removed empty layer: {layer_name}")
                except Exception as e:
                    log_warning(f"Could not remove layer {layer_name}: {str(e)}")
        
        # Purge unused linetypes
        for linetype in list(doc.linetypes):
            try:
                doc.linetypes.remove(linetype.dxf.name)
            except Exception as e:
                # Skip if linetype is in use or is a default linetype
                continue
        
        # Purge unused text styles
        for style in list(doc.styles):
            try:
                doc.styles.remove(style.dxf.name)
            except Exception as e:
                # Skip if style is in use or is a default style
                continue
        
        # Purge unused dimension styles
        for dimstyle in list(doc.dimstyles):
            try:
                doc.dimstyles.remove(dimstyle.dxf.name)
            except Exception as e:
                # Skip if dimstyle is in use or is a default style
                continue
        
        # Force database update
        doc.entitydb.purge()
        
        log_debug("Document cleanup completed successfully")
        
    except Exception as e:
        log_error(f"Error during document cleanup: {str(e)}")
        log_error(f"Traceback:\n{traceback.format_exc()}")

def initialize_document(doc):
    loaded_styles = load_standard_text_styles(doc)
    return loaded_styles

def load_standard_text_styles(doc):
    """Load standard text styles into the document."""
    for style_name, font_name, oblique_angle in STANDARD_TEXT_STYLES:
        if style_name not in doc.styles:
            doc.styles.new(style_name, dxfattribs={
                'font': font_name,
                'width': 1.0,
                'oblique': oblique_angle
            }) 