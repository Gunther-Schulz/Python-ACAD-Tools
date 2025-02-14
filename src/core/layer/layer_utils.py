"""Layer utility functions."""

from src.utils import log_debug

def is_wmts_or_wms_layer(layer_name, project_settings):
    """Check if a layer is a WMTS or WMS layer."""
    # Check in WMTS layers
    if any(layer.get('name') == layer_name for layer in project_settings.get('wmtsLayers', [])):
        return True
        
    # Check in WMS layers
    if any(layer.get('name') == layer_name for layer in project_settings.get('wmsLayers', [])):
        return True
        
    return False

def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
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

    return previous_row[-1] 