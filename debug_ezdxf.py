# Direct imports for ezdxf as a hard dependency
import ezdxf
from ezdxf import DXFValueError, DXFStructureError
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.entities.ltype import Linetype
from ezdxf.entities.textstyle import Textstyle as TextStyle
from ezdxf.entities.layer import Layer
from ezdxf.entities import Text, MText, Point as DXFPoint, Line as DXFLine, LWPolyline, Hatch
from ezdxf.enums import MTextEntityAlignment # For MTEXT
from ezdxf import const as ezdxf_const # For hatch flags and other constants

print("All ezdxf imports successful")

# Test the adapter import
try:
    from src.adapters.ezdxf_adapter import EzdxfAdapter
    from src.services.logging_service import LoggingService
    logger_service = LoggingService()
    adapter = EzdxfAdapter(logger_service)
except Exception as e:
    print(f"Adapter error: {e}")
