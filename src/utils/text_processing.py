"""Text processing utility functions for string manipulation."""
import re


def sanitize_dxf_layer_name(name: str) -> str:
    """
    Sanitizes a string to be a valid DXF layer name.
    DXF layer names can contain letters, digits, and the special characters
    dollar sign ($), underscore (_), and hyphen (-).
    They cannot contain spaces if not enclosed in quotes in some contexts, but ezdxf handles this.
    This function will replace other problematic characters with underscores.
    It also ensures the name is not empty.
    """
    if not isinstance(name, str):
        name = str(name)

    # Replace characters not allowed or problematic in layer names with underscore
    # Allowed: A-Z, a-z, 0-9, $, _, -
    # For simplicity, we'll be a bit more restrictive initially, replacing most non-alphanumeric
    # characters except for underscore and hyphen. DXF handles many things, but this is safer.
    # Spaces are generally okay as ezdxf handles them, but can be problematic in other tools.
    # Let's replace spaces with underscores too for broader compatibility.
    name = name.replace(" ", "_")

    # Keep alphanumeric, underscore, hyphen. Replace others with underscore.
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    # Ensure the name is not empty after sanitization
    if not sanitized_name:
        return "default_layer"

    return sanitized_name
