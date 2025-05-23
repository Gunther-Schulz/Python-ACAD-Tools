"""Utilities for working with DXF entities, particularly XDATA."""
from typing import List, Tuple, Any, Optional

APP_ID_PREFIX = "ACAD_APP_PYACADTOOLS"

try:
    from ezdxf.entities import DXFGraphic
    from ezdxf.lldxf.extendedtags import ExtendedTags
    from ezdxf.lldxf.types import DXFTag
    from ezdxf.lldxf.const import DXFValueError
    EZDXF_AVAILABLE = True
except ImportError:
    DXFGraphic = type(None) # type: ignore
    ExtendedTags = type(None) # type: ignore
    DXFTag = type(None) # type: ignore
    DXFValueError = Exception # type: ignore
    EZDXF_AVAILABLE = False

def attach_xdata(entity: DXFGraphic, app_id: str, xdata_pairs: List[Tuple[int, Any]]) -> bool:
    """
    Attaches extended data (XDATA) to a DXF entity under a specific application ID.
    It will replace any existing XDATA for the same app_id.

    Args:
        entity: The ezdxf entity to attach XDATA to.
        app_id: The application ID (registered app name) for the XDATA.
                This function will prepend a standard prefix if not already present.
        xdata_pairs: A list of (group_code, value) tuples for the XDATA.

    Returns:
        True if XDATA was attached, False otherwise (e.g., ezdxf not available).
    """
    if not EZDXF_AVAILABLE or entity is None:
        return False

    # Ensure app_id is registered if not already (ezdxf handles this transparently)
    # Prefix the app_id to make it more unique to this toolset if it doesn't have the prefix
    # final_app_id = app_id if app_id.startswith(APP_ID_PREFIX) else f"{APP_ID_PREFIX}_{app_id.upper().replace(' ', '_')}"
    final_app_id = app_id # Keep app_id as provided by caller for now; caller manages namespacing.

    try:
        entity.set_xdata(final_app_id, xdata_pairs) # set_xdata replaces existing XDATA for app_id
        return True
    except DXFValueError as e:
        # This can happen if group codes are not in allowed range (1000-1071, except 1001)
        # Or if entity does not support XDATA (rare for DXFGraphic derivatives)
        # Consider logging this error with a logger if available
        # print(f"Error setting XDATA for app_id '{final_app_id}' on entity {entity.dxf.handle if hasattr(entity, 'dxf') else 'N/A'}: {e}")
        return False
    except Exception:
        # Catch any other unexpected ezdxf errors
        # print(f"Unexpected error setting XDATA for app_id '{final_app_id}': {e}")
        return False

def get_xdata(entity: DXFGraphic, app_id: str) -> Optional[List[Tuple[int, Any]]]:
    """
    Retrieves extended data (XDATA) for a specific application ID from a DXF entity.

    Args:
        entity: The ezdxf entity.
        app_id: The application ID for the XDATA.

    Returns:
        A list of (group_code, value) tuples if XDATA is found, otherwise None.
    """
    if not EZDXF_AVAILABLE or entity is None:
        return None

    # final_app_id = app_id if app_id.startswith(APP_ID_PREFIX) else f"{APP_ID_PREFIX}_{app_id.upper().replace(' ', '_')}"
    final_app_id = app_id

    try:
        xdata = entity.get_xdata(final_app_id)
        # Convert from ezdxf's ExtendedTags to a simple list of tuples
        return [(tag.code, tag.value) for tag in xdata]
    except DXFValueError: # Raised if app_id not found
        return None
    except Exception:
        return None

def has_xdata_value(entity: DXFGraphic, app_id: str, expected_value: Any, group_code: int = 1000) -> bool:
    """
    Checks if an entity has a specific XDATA string value for a given app_id and group_code.
    Primarily useful for checking identifier tags.

    Args:
        entity: The ezdxf entity.
        app_id: The application ID for the XDATA.
        expected_value: The value to check for.
        group_code: The group code of the XDATA tag to check (default is 1000 for strings).

    Returns:
        True if the entity has XDATA from app_id with the specified tag and value, False otherwise.
    """
    xdata_list = get_xdata(entity, app_id)
    if xdata_list:
        for code, value in xdata_list:
            if code == group_code and value == expected_value:
                return True
    return False

def attach_script_identifier(entity: DXFGraphic, script_identifier: str) -> bool:
    """
    Simple helper to attach script identifier XDATA to an entity.

    Args:
        entity: The ezdxf entity to mark
        script_identifier: The script identifier string

    Returns:
        True if XDATA was attached, False otherwise
    """
    if not EZDXF_AVAILABLE or entity is None:
        return False

    try:
        # Clear any existing XDATA first (matches OLDAPP pattern)
        try:
            entity.discard_xdata('DXFEXPORTER')
        except:
            pass

        # Set new XDATA
        entity.set_xdata('DXFEXPORTER', [(1000, script_identifier)])
        return True
    except Exception as e:
        return False

def remove_entities_by_layer(dxf_drawing, layer_names, script_identifier="python-acad-tools"):
    """
    Safely remove entities from specified layers that were created by this script.

    Args:
        dxf_drawing: The ezdxf Drawing object
        layer_names: Single layer name (str) or list of layer names to clear
        script_identifier: Identifier used to mark entities created by this script

    Returns:
        int: Number of entities deleted
    """
    if not EZDXF_AVAILABLE:
        raise RuntimeError("ezdxf library not available for DXF operations")

    doc = dxf_drawing
    key_func = doc.layers.key
    delete_count = 0

    # Convert single layer name to list
    if isinstance(layer_names, str):
        layer_names = [layer_names]

    # Convert layer names to keys
    layer_keys = [key_func(layer_name) for layer_name in layer_names]

    # Safe deletion using trashcan
    try:
        with doc.entitydb.trashcan() as trash:
            # Iterate through all entities in both modelspace and paperspace
            for entity in doc.entitydb.values():
                try:
                    # Check if entity has layer attribute
                    if not hasattr(entity, 'dxf') or not entity.dxf.hasattr("layer"):
                        continue

                    # Check if entity is on one of the target layers
                    if key_func(entity.dxf.layer) in layer_keys:
                        # Check if entity was created by our script
                        if is_created_by_script(entity, script_identifier):
                            try:
                                # Clear any XDATA before deletion
                                try:
                                    entity.discard_xdata('DXFEXPORTER')
                                except:
                                    pass

                                # Add to trashcan for safe deletion
                                trash.add(entity.dxf.handle)
                                delete_count += 1

                            except Exception as e:
                                # Log but continue with other entities
                                continue
                except AttributeError:
                    continue

        # Cleanup operations
        try:
            doc.entitydb.purge()
        except Exception as e:
            pass  # Not critical if purge fails

        try:
            doc.audit()
        except Exception as e:
            pass  # Audit failure is not critical

    except Exception as e:
        raise RuntimeError(f"Failed to remove entities from layers {layer_names}: {e}")

    return delete_count


def is_created_by_script(entity, script_identifier):
    """Check if an entity was created by this script by examining XDATA."""
    if not EZDXF_AVAILABLE:
        return False

    try:
        xdata = entity.get_xdata('DXFEXPORTER')
        if xdata:
            for tag in xdata:
                if tag.code == 1000 and tag.value == script_identifier:
                    return True
    except DXFValueError:
        # This exception is raised when the entity has no XDATA for 'DXFEXPORTER'
        # It's not an error, just means the entity wasn't created by this script
        return False
    except Exception:
        # Any other unexpected error
        return False
    return False
