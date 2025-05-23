"""Utilities for DXF document maintenance like cleanup."""
from typing import Optional

# It's crucial that the logger is passed in or globally available if these utils are to log.
# For now, assuming no direct logging from these low-level utils to keep them simple.
# Consider adding logger: Optional[ILoggingService] = None to functions if logging is needed.

try:
    from ezdxf.document import Drawing
    from ezdxf.recover import audit
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None) # type: ignore
    def audit(doc: Drawing, stream = None):
        pass # Stub if ezdxf not available
    EZDXF_AVAILABLE = False

def cleanup_dxf_document(doc: Drawing, do_audit: bool = True, do_purge: bool = True) -> bool:
    """
    Performs cleanup operations on an ezdxf Drawing object.
    This can include auditing the document for errors and purging unused resources.

    Args:
        doc: The ezdxf Drawing object to clean.
        do_audit: If True, performs an audit of the DXF document.
        do_purge: If True, purges unused blocks, layers, linetypes, text styles etc.
                  Note: Purging can be aggressive. Ensure it doesn't remove entities
                  or definitions that might be needed later if they are currently unreferenced
                  but intended for future use in the same document session.

    Returns:
        True if cleanup operations were attempted (even if some failed internally in ezdxf),
        False if ezdxf is not available or doc is None.
    """
    if not EZDXF_AVAILABLE or doc is None:
        return False

    if do_audit:
        try:
            # The audit function in ezdxf.recover might write to a stream.
            # If detailed audit logs are needed, a stream (like io.StringIO) can be passed.
            # For now, just run it to fix errors internally if possible.
            auditor = audit(doc) # ezdxf.recover.audit
            if auditor.has_errors:
                # print(f"DXF audit found {len(auditor.errors)} errors.") # Log this with a logger
                pass # Errors are fixed internally by auditor if possible
            if auditor.has_fixed_errors:
                # print(f"DXF audit fixed {len(auditor.fixes)} errors.") # Log this
                pass
        except Exception as e:
            # print(f"Error during DXF document audit: {e}") # Log this
            pass # Don't let audit failure stop other cleanup

    if do_purge:
        try:
            # Purge unused blocks
            # doc.blocks.purge() # This might be too aggressive for some workflows

            # Purge all known table entries (layers, linetypes, text styles, etc.)
            # ezdxf's purge() method on the document is quite comprehensive.
            doc.purge()
            # print("DXF document purged of unused resources.") # Log this
        except Exception as e:
            # print(f"Error during DXF document purge: {e}") # Log this
            pass # Don't let purge failure stop process

    return True
