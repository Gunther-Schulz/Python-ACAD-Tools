import sys
print(f"diag_ezdxf_import.py: sys.executable: {sys.executable}")
print(f"diag_ezdxf_import.py: sys.path: {sys.path}")

error_in_imports = False

try:
    import ezdxf
    print("diag_ezdxf_import.py: ezdxf imported successfully!")
    print(f"diag_ezdxf_import.py: ezdxf version: {ezdxf.__version__}")
    print(f"diag_ezdxf_import.py: ezdxf path: {ezdxf.__file__}")
except ImportError as e:
    print(f"diag_ezdxf_import.py: FAILED to import top-level ezdxf. Error: {e}")
    error_in_imports = True
except Exception as e:
    print(f"diag_ezdxf_import.py: An unexpected error occurred during ezdxf import: {e}")
    error_in_imports = True

try:
    from ezdxf.errors import DXFError, DXFValueError, DXFStructureError
    print("diag_ezdxf_import.py: ezdxf.errors imported successfully!")
except ImportError as e:
    print(f"diag_ezdxf_import.py: FAILED to import from ezdxf.errors. Error: {e}")
    error_in_imports = True
except Exception as e:
    print(f"diag_ezdxf_import.py: An unexpected error occurred during ezdxf.errors import: {e}")
    error_in_imports = True

try:
    from ezdxf.document import Drawing
    print("diag_ezdxf_import.py: ezdxf.document.Drawing imported successfully!")
except ImportError as e:
    print(f"diag_ezdxf_import.py: FAILED to import from ezdxf.document.Drawing. Error: {e}")
    error_in_imports = True
except Exception as e:
    print(f"diag_ezdxf_import.py: An unexpected error occurred during ezdxf.document.Drawing import: {e}")
    error_in_imports = True

if not error_in_imports:
    print("diag_ezdxf_import.py: All attempted ezdxf imports were successful.")
else:
    print("diag_ezdxf_import.py: One or more ezdxf imports FAILED.")
