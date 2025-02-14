"""Utility functions for layer processing."""

from src.core.utils import log_debug, log_warning, log_error

def is_wmts_or_wms_layer(layer_name, project_settings):
    """Check if a layer is a WMTS or WMS layer."""
    try:
        log_debug(f"Checking if {layer_name} is a WMTS/WMS layer")
        
        # Check in WMTS layers
        if any(layer.get('name') == layer_name for layer in project_settings.get('wmtsLayers', [])):
            log_debug(f"Layer {layer_name} found in WMTS layers")
            return True
            
        # Check in WMS layers
        if any(layer.get('name') == layer_name for layer in project_settings.get('wmsLayers', [])):
            log_debug(f"Layer {layer_name} found in WMS layers")
            return True
            
        log_debug(f"Layer {layer_name} is not a WMTS/WMS layer")
        return False
        
    except Exception as e:
        log_error(f"Error checking WMTS/WMS layer status for {layer_name}: {str(e)}")
        return False

def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
    try:
        if not isinstance(s1, str) or not isinstance(s2, str):
            log_warning(f"Invalid input types for Levenshtein distance: {type(s1)}, {type(s2)}")
            return float('inf')
            
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        distance = previous_row[-1]
        log_debug(f"Levenshtein distance between '{s1}' and '{s2}': {distance}")
        return distance
        
    except Exception as e:
        log_error(f"Error calculating Levenshtein distance: {str(e)}")
        return float('inf')  # Return infinity as a safe fallback 