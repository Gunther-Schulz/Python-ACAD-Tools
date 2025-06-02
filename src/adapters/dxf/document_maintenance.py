"""DXF document maintenance adapter for ezdxf library integration.

This module provides adapter functions for DXF document cleanup and maintenance operations.
"""
from typing import Optional

# Direct imports for ezdxf as a hard dependency
from ezdxf.document import Drawing
from ezdxf.recover import audit

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
    if doc is None:
        return False

    if do_audit:
        try:
            # The audit function in ezdxf.recover might write to a stream.
            # If detailed audit logs are needed, a stream (like io.StringIO) can be passed.
            # For now, just run it to fix errors internally if possible.
            auditor = audit(doc) # ezdxf.recover.audit
            if auditor.has_errors:
                # Errors are fixed internally by auditor if possible
                pass
            if auditor.has_fixed_errors:
                pass
        except Exception:
            # Don't let audit failure stop other cleanup
            pass

    if do_purge:
        try:
            # Purge all known table entries (layers, linetypes, text styles, etc.)
            # ezdxf's purge() method on the document is quite comprehensive.
            doc.purge()
        except Exception:
            # Don't let purge failure stop process
            pass

    return True
