import unittest
from unittest.mock import patch, MagicMock, mock_open, call, ANY
import os

# Unconditional imports for ezdxf types
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.entities import Text, MText, Point as DXFPoint, Line as DXFLine, LWPolyline, Hatch
from ezdxf.entities.layer import Layer
from ezdxf.entities.ltype import Linetype
from ezdxf.entities.textstyle import Textstyle as TextStyle
from ezdxf.lldxf.const import DXFValueError, DXFStructureError
from ezdxf.enums import MTextEntityAlignment
from ezdxf import const as ezdxf_const

# Re-inserting table spec imports
from ezdxf.sections.tables import LayerTable as LayerTableSpec, \
                                  TextstyleTable as StyleTableSpec, \
                                  LinetypeTable as LinetypeTableSpec

# Assuming the module is in src/adapters/ezdxf_adapter.py
# and tests are in tests/adapters/test_ezdxf_adapter.py
# Adjust path as necessary for your test runner
from src.adapters.ezdxf_adapter import EzdxfAdapter
from src.interfaces.logging_service_interface import ILoggingService
from src.domain.exceptions import DXFProcessingError

# Mock a generic ezdxf entity for reuse
class MockDXFEntity:
    def __init__(self, handle="DEFAULT_HANDLE"):
        self.dxf = MagicMock()
        self.dxf.handle = handle
        self.dxf.name = "DEFAULT_NAME" # For layers, styles etc.
        # Add other common attributes as needed by tests
        self.dxf.font = "arial.ttf" # For TextStyle
        self.dxf.flags = 0 # For linetypes, layer state
        self.dxf.pattern = [] # For linetypes
        self.dxf.description = "Mock Description" # For linetypes

        # Initialize .dxf attributes that are commonly accessed/expected
        self.dxf.color = 256 # Default ByLayer, set on the .dxf object
        self.dxf.linetype = "CONTINUOUS" # Default, set on the .dxf object
        self.dxf.lineweight = -1 # Default, set on the .dxf object
        self.dxf.plot = 1 # Plotting enabled, set on the .dxf object
        self.dxf.true_color = None # Initialize on the .dxf object
        self.dxf.transparency = None # Initialize on the .dxf object

        # For entities that might have specific sub-attributes (e.g., MText)
        self.dxf.char_height = None
        self.dxf.insert = None
        self.dxf.text_direction = None
        self.dxf.attachment_point = None
        self.dxf.line_spacing_factor = None
        self.dxf.width = None # MText width

        # Mock methods for layer state changes
        self.lock = MagicMock(name=f"{handle}_lock_method")
        self.unlock = MagicMock(name=f"{handle}_unlock_method")
        self.freeze = MagicMock(name=f"{handle}_freeze_method")
        self.thaw = MagicMock(name=f"{handle}_thaw_method")

        # Mock methods for hatch paths
        self.paths = MagicMock()
        self.paths.add_polyline_path = MagicMock(name=f"{handle}_add_polyline_path_method")
        self.set_pattern_fill = MagicMock(name=f"{handle}_set_pattern_fill_method")
        self.set_solid_fill = MagicMock(name=f"{handle}_set_solid_fill_method")

    def dxftype(self):
        return "MOCK_ENTITY"

    def set_pattern_fill(self, name, color=None, angle=None, scale=None):
        pass # Mock implementation

    def set_solid_fill(self, color=None):
        pass # Mock implementation

    def get_handle(self): # Mimic method if some code calls it as a method
        return self.dxf.handle

    @property
    def color(self):
        return self.dxf.color

    @color.setter
    def color(self, value):
        self.dxf.color = value

    @property
    def linetype(self):
        return self.dxf.linetype

    @linetype.setter
    def linetype(self, value):
        self.dxf.linetype = value

    @property
    def lineweight(self):
        return self.dxf.lineweight

    @lineweight.setter
    def lineweight(self, value):
        self.dxf.lineweight = value

    @property
    def plot(self):
        return self.dxf.plot

    @plot.setter
    def plot(self, value):
        self.dxf.plot = value

    @property
    def true_color(self):
        return self.dxf.true_color

    @true_color.setter
    def true_color(self, value):
        self.dxf.true_color = value

    @property
    def is_on(self):
        return self.dxf.color >= 0

    @is_on.setter
    def is_on(self, value: bool):
        current_color = abs(self.dxf.color) # Get current absolute color value
        if value: # True means ON
            self.dxf.color = current_color if current_color != 0 else 256 # Ensure non-zero for ON
        else: # False means OFF
            self.dxf.color = -abs(current_color if current_color != 0 else 256) # Ensure non-zero for OFF

    @property
    def is_frozen(self):
        return bool(self.dxf.flags & 1)

    # No setter for is_frozen directly, use freeze/thaw methods

    @property
    def is_locked(self):
        return bool(self.dxf.flags & 2)

    # No setter for is_locked directly, use lock/unlock methods

    @property
    def is_off(self):
        return self.dxf.color < 0

    @is_off.setter
    def is_off(self, value: bool):
        current_color = abs(self.dxf.color) # Get current absolute color value
        if value: # True means OFF
            self.dxf.color = -abs(current_color if current_color != 0 else 256) # Ensure non-zero for OFF
        else: # False means ON
            self.dxf.color = current_color if current_color != 0 else 256 # Ensure non-zero for ON

class CustomLayerTableSpec:
    def add(self, name, dxfattribs=None): pass
    def get(self, name, default=None): pass
    def __contains__(self, name): return False # Must exist on the spec for MagicMock to mock it

class CustomStyleTableSpec:
    def new(self, name, dxfattribs=None): pass # Styles often use .new() rather than .add()
    def get(self, name, default=None): pass
    def __contains__(self, name): return False

class CustomLinetypeTableSpec:
    def add(self, name, dxfattribs=None): pass # Linetypes use .add()
    def get(self, name, default=None): pass
    def __contains__(self, name): return False

class TestEzdxfAdapter(unittest.TestCase):

    def setUp(self):
        self.mock_logger_service = MagicMock(spec=ILoggingService)
        self.mock_logger = MagicMock()
        self.mock_logger_service.get_logger.return_value = self.mock_logger

        # Store patches to stop them in tearDown
        self.patches_started_mocks = {} # Stores the mock object returned by patcher.start()
        self.active_patchers = [] # Stores the patcher objects themselves for stopping
        self.patch_ezdxf_available_patcher = None # For the EZDXF_IMPORTED_SUCCESSFULLY flag specifically

    def _start_patch(self, name, **kwargs):
        patcher = patch(name, **kwargs)
        self.active_patchers.append(patcher) # Store the patcher for stopping
        started_mock = patcher.start()
        self.patches_started_mocks[name] = started_mock # Store the started mock if needed by name
        return started_mock

    def _mock_ezdxf_globally(self):
        # Patch the ezdxf module itself
        self.mock_ezdxf_module = self._start_patch('src.adapters.ezdxf_adapter.ezdxf')

        # Configure the mock_ezdxf_module based on how ezdxf_adapter.py imports and uses ezdxf
        # Exceptions
        self.mock_ezdxf_module.DXFValueError = DXFValueError # Use real exception
        self.mock_ezdxf_module.DXFStructureError = DXFStructureError # Use real exception

        # Document and Layouts
        self.mock_drawing = MagicMock(spec=Drawing) # This will be the return_value of new/readfile
        self.mock_ezdxf_module.new.return_value = self.mock_drawing
        self.mock_ezdxf_module.readfile.return_value = self.mock_drawing
        self.mock_modelspace = MagicMock(spec=Modelspace)
        self.mock_drawing.modelspace = MagicMock(return_value=self.mock_modelspace) # modelspace() is a method
        self.mock_drawing.saveas = MagicMock() # Added for save tests

        # Configure mock_modelspace with common methods
        self.mock_modelspace.add_point = MagicMock()
        self.mock_modelspace.add_line = MagicMock()
        self.mock_modelspace.add_lwpolyline = MagicMock()
        self.mock_modelspace.add_text = MagicMock()
        self.mock_modelspace.add_mtext = MagicMock()
        self.mock_modelspace.add_hatch = MagicMock()
        self.mock_modelspace.query = MagicMock()

        self.mock_layers_table = MagicMock(spec=CustomLayerTableSpec)
        self.mock_drawing.layers = self.mock_layers_table
        self.mock_layers_table.add = MagicMock()
        self.mock_layers_table.get = MagicMock()
        self.mock_layers_table.__contains__.return_value = False

        self.mock_styles_table = MagicMock(spec=CustomStyleTableSpec)
        self.mock_drawing.styles = self.mock_styles_table
        self.mock_styles_table.new = MagicMock()
        self.mock_styles_table.get = MagicMock()
        self.mock_styles_table.__contains__.return_value = False

        self.mock_linetypes_table = MagicMock(spec=CustomLinetypeTableSpec)
        self.mock_drawing.linetypes = self.mock_linetypes_table
        self.mock_linetypes_table.add = MagicMock()
        self.mock_linetypes_table.get = MagicMock()
        self.mock_linetypes_table.__contains__.return_value = False

        # Entities (assuming accessed like ezdxf.entities.Text)
        # Create a mock for the .entities submodule if it doesn't exist
        if not hasattr(self.mock_ezdxf_module, 'entities') or not isinstance(self.mock_ezdxf_module.entities, MagicMock):
            self.mock_ezdxf_module.entities = MagicMock()
        self.mock_ezdxf_module.entities.Text = MagicMock(spec=Text)
        self.mock_ezdxf_module.entities.MText = MagicMock(spec=MText)
        self.mock_ezdxf_module.entities.Point = MagicMock(spec=DXFPoint) # Renamed to DXFPoint in adapter
        self.mock_ezdxf_module.entities.Line = MagicMock(spec=DXFLine)   # Renamed to DXFLine in adapter
        self.mock_ezdxf_module.entities.LWPolyline = MagicMock(spec=LWPolyline)
        self.mock_ezdxf_module.entities.Hatch = Hatch # Use the real Hatch type imported at the top of the test file

        # Table Entries (Linetype, Style, Layer)
        if not hasattr(self.mock_ezdxf_module, 'tableentries') or not isinstance(self.mock_ezdxf_module.tableentries, MagicMock):
            self.mock_ezdxf_module.tableentries = MagicMock()
        self.mock_ezdxf_module.tableentries.Layer = MagicMock(spec=Layer)
        self.mock_ezdxf_module.tableentries.Linetype = MagicMock(spec=Linetype)
        self.mock_ezdxf_module.tableentries.Style = MagicMock(spec=TextStyle) # TextStyle is Style in adapter

        # Enums and Constants
        if not hasattr(self.mock_ezdxf_module, 'enums') or not isinstance(self.mock_ezdxf_module.enums, MagicMock):
            self.mock_ezdxf_module.enums = MagicMock()
        self.mock_ezdxf_module.enums.MTextEntityAlignment = MagicMock(spec=MTextEntityAlignment)
        self.mock_ezdxf_module.const = MagicMock(spec=ezdxf_const) # ezdxf_const is ezdxf.const in adapter

        # Patch geopandas related imports (gpd is a hard dependency)
        self._start_patch('src.adapters.ezdxf_adapter.gpd', new_callable=MagicMock)

        # Patch os.makedirs for save_document tests
        self._start_patch('src.adapters.ezdxf_adapter.os.makedirs', return_value=None)


    def tearDown(self):
        for patcher in self.active_patchers:
            try:
                patcher.stop()
            except RuntimeError: # pragma: no cover
                 # can happen if patch was already stopped or not started
                 pass
        self.patches_started_mocks = {}
        self.active_patchers = []


    @patch('src.adapters.ezdxf_adapter.os.path.exists')
    def test_load_dxf_file_success(self, mock_os_path_exists):
        self._mock_ezdxf_globally()
        mock_os_path_exists.return_value = True
        adapter = EzdxfAdapter(self.mock_logger_service)
        doc = adapter.load_dxf_file("test.dxf")
        self.patches_started_mocks['src.adapters.ezdxf_adapter.ezdxf'].readfile.assert_called_with("test.dxf")
        self.assertEqual(doc, self.mock_drawing)
        self.mock_logger.info.assert_called_with("Loading DXF file: test.dxf")

    @patch('src.adapters.ezdxf_adapter.os.path.exists')
    def test_load_dxf_file_not_found(self, mock_os_path_exists):
        self._mock_ezdxf_globally()
        mock_os_path_exists.return_value = False
        adapter = EzdxfAdapter(self.mock_logger_service)
        self.mock_logger.reset_mock() # Reset after init
        with self.assertRaises(DXFProcessingError) as context:
            adapter.load_dxf_file("nonexistent.dxf")
        self.assertTrue("DXF file not found: nonexistent.dxf" in str(context.exception))
        self.mock_logger.error.assert_called_with("DXF file not found for loading: nonexistent.dxf")
        self.mock_logger.info.assert_not_called() # Ensure no attempt to load during the action itself

    @patch('src.adapters.ezdxf_adapter.os.path.exists')
    def test_load_dxf_file_structure_error(self, mock_os_path_exists):
        self._mock_ezdxf_globally()
        mock_os_path_exists.return_value = True
        error_msg_from_ezdxf = "Test Structure Error"
        file_path_for_test = "path/to/corrupt.dxf"
        self.patches_started_mocks['src.adapters.ezdxf_adapter.ezdxf'].readfile.side_effect = DXFStructureError(error_msg_from_ezdxf)
        adapter = EzdxfAdapter(self.mock_logger_service)
        self.mock_logger.reset_mock() # Reset after init

        with self.assertRaises(DXFProcessingError) as context:
            adapter.load_dxf_file(file_path_for_test)

        expected_exception_msg = f"DXF Structure Error while loading {file_path_for_test}: {error_msg_from_ezdxf}"
        self.assertTrue(expected_exception_msg in str(context.exception))
        self.mock_logger.error.assert_called_with(expected_exception_msg, exc_info=True)

    @patch('src.adapters.ezdxf_adapter.os.path.exists', return_value=True)
    def test_load_dxf_file_io_error(self, mock_exists):
        self._mock_ezdxf_globally()
        # Simulate ezdxf.readfile raising our DXFStructureError.
        error_message = "Test IO-like Error via DXFStructureError"
        self.mock_ezdxf_module.readfile.side_effect = DXFStructureError(error_message)

        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.load_dxf_file("io_error.dxf")

        expected_log_msg = f"DXF Structure Error while loading io_error.dxf: {error_message}"
        self.mock_logger.error.assert_called_with(expected_log_msg, exc_info=True)
        # Verify the DXFProcessingError attributes
        self.assertEqual(context.exception.args[0], expected_log_msg)
        self.assertIsInstance(context.exception.__cause__, DXFStructureError)
        self.assertEqual(str(context.exception.__cause__), error_message)

    def test_save_document_success(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.save_document(self.mock_drawing, "output/test_save.dxf")
        self.patches_started_mocks['src.adapters.ezdxf_adapter.os.makedirs'].assert_called_with("output", exist_ok=True)
        self.mock_drawing.saveas.assert_called_with("output/test_save.dxf")
        self.mock_logger.info.assert_called_with("Successfully saved DXF file: output/test_save.dxf")

    def test_save_document_no_doc(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.save_document(None, "output/test_save.dxf")
        self.assertEqual(str(context.exception), "DXF document is None, cannot save.")

    def test_save_document_exception(self):
        self._mock_ezdxf_globally()
        self.mock_drawing.saveas.side_effect = Exception("Save failed")
        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.save_document(self.mock_drawing, "output/fail_save.dxf")
        self.assertTrue("Failed to save DXF file output/fail_save.dxf: Save failed" in str(context.exception))

    def test_create_document_default_version(self):
        self._mock_ezdxf_globally()
        self.mock_drawing.layers = MagicMock()
        self.mock_drawing.layers.add = MagicMock()
        self.mock_drawing.layers.__contains__.return_value = False

        adapter = EzdxfAdapter(self.mock_logger_service)
        doc = adapter.create_document()

        self.patches_started_mocks['src.adapters.ezdxf_adapter.ezdxf'].new.assert_called_with(dxfversion="AC1027")
        self.assertEqual(doc, self.mock_drawing)
        self.mock_drawing.layers.add.assert_called_with("0")
        self.mock_logger.info.assert_called_with("Successfully created new DXF document (version AC1027).")

    def test_create_document_specific_version(self):
        self._mock_ezdxf_globally()
        self.mock_drawing.layers = MagicMock()
        self.mock_drawing.layers.add = MagicMock()
        self.mock_drawing.layers.__contains__.return_value = True

        adapter = EzdxfAdapter(self.mock_logger_service)
        doc = adapter.create_document(dxf_version="AC1032") # R2018

        self.patches_started_mocks['src.adapters.ezdxf_adapter.ezdxf'].new.assert_called_with(dxfversion="AC1032")
        self.assertEqual(doc, self.mock_drawing)
        self.mock_drawing.layers.add.assert_not_called()
        self.mock_logger.info.assert_called_with("Successfully created new DXF document (version AC1032).")

    def test_create_document_exception(self):
        self._mock_ezdxf_globally()
        self.patches_started_mocks['src.adapters.ezdxf_adapter.ezdxf'].new.side_effect = Exception("Creation failed")
        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.create_document()
        self.assertTrue("Failed to create new DXF document (version AC1027): Creation failed" in str(context.exception))

    def test_get_modelspace_success(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        msp = adapter.get_modelspace(self.mock_drawing)
        self.mock_drawing.modelspace.assert_called_once()
        self.assertEqual(msp, self.mock_modelspace)

    def test_get_modelspace_no_doc(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.get_modelspace(None)
        self.assertEqual(str(context.exception), "DXF document is None, cannot get modelspace.")

    # --- Layer Tests ---
    def test_create_dxf_layer_new(self):
        self._mock_ezdxf_globally()
        mock_new_layer_entity = MockDXFEntity("NEW_LAYER")
        self.mock_layers_table.add.return_value = mock_new_layer_entity
        self.mock_layers_table.__contains__.return_value = False

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.create_dxf_layer(self.mock_drawing, "NEW_LAYER_NAME", color=1, linetype="DASHED", lineweight=30, plot=False, true_color=0x00FF00)

        self.mock_layers_table.add.assert_called_with("NEW_LAYER_NAME")
        self.assertEqual(mock_new_layer_entity.dxf.color, 1)
        self.assertEqual(mock_new_layer_entity.dxf.linetype, "DASHED")
        self.assertEqual(mock_new_layer_entity.dxf.lineweight, 30)
        self.assertEqual(mock_new_layer_entity.dxf.plot, 0) # plot=False means 0
        self.assertEqual(mock_new_layer_entity.dxf.true_color, 0x00FF00)
        self.mock_logger.debug.assert_any_call("Created new DXF layer: NEW_LAYER_NAME")

    def test_create_dxf_layer_existing(self):
        self._mock_ezdxf_globally()
        mock_existing_layer_entity = MockDXFEntity("EXISTING_LAYER")
        self.mock_layers_table.get.return_value = mock_existing_layer_entity
        self.mock_layers_table.__contains__.return_value = True

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.create_dxf_layer(self.mock_drawing, "EXISTING_LAYER_NAME", color=2)

        self.mock_layers_table.get.assert_called_with("EXISTING_LAYER_NAME")
        self.mock_layers_table.add.assert_not_called()
        self.assertEqual(mock_existing_layer_entity.dxf.color, 2)
        self.mock_logger.debug.assert_any_call("Ensured DXF layer exists: EXISTING_LAYER_NAME")

    def test_create_dxf_layer_no_doc(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.create_dxf_layer(None, "ANY_LAYER")
        self.assertEqual(str(context.exception), "DXF Document is None, cannot create layer.")

    def test_create_dxf_layer_dxf_value_error(self):
        self._mock_ezdxf_globally()
        self.mock_drawing.layers = MagicMock()
        error_to_raise = DXFValueError("Invalid layer prop")
        self.mock_drawing.layers.add.side_effect = error_to_raise
        self.mock_drawing.layers.__contains__.return_value = False

        adapter = EzdxfAdapter(self.mock_logger_service)
        with self.assertRaises(DXFProcessingError) as context:
            adapter.create_dxf_layer(self.mock_drawing, "ERROR_LAYER", color=-1000) # Example invalid value
        self.assertEqual(str(context.exception), "DXFValueError for DXF layer ERROR_LAYER: Invalid layer prop")

    def test_get_layer_found(self):
        self._mock_ezdxf_globally()
        mock_layer_obj = MockDXFEntity("FOUND_LAYER")
        self.mock_drawing.layers = MagicMock()
        self.mock_drawing.layers.__contains__.return_value = True
        self.mock_drawing.layers.get.return_value = mock_layer_obj

        adapter = EzdxfAdapter(self.mock_logger_service)
        layer = adapter.get_layer(self.mock_drawing, "EXISTING_LAYER")

        self.mock_drawing.layers.get.assert_called_with("EXISTING_LAYER")
        self.assertEqual(layer, mock_layer_obj)
        self.mock_logger.debug.assert_called_with("Retrieved layer: 'EXISTING_LAYER'.")

    def test_get_layer_not_found(self):
        self._mock_ezdxf_globally()
        self.mock_drawing.layers = MagicMock()
        self.mock_drawing.layers.__contains__.return_value = False

        adapter = EzdxfAdapter(self.mock_logger_service)
        layer = adapter.get_layer(self.mock_drawing, "MISSING_LAYER")

        self.assertIsNone(layer)
        self.mock_logger.debug.assert_called_with("Layer 'MISSING_LAYER' not found.")

    def test_set_layer_properties_all(self):
        self._mock_ezdxf_globally()
        mock_layer_entity_for_test = MockDXFEntity("TARGET_LAYER_PROPS")
        self.mock_drawing.layers.get.return_value = mock_layer_entity_for_test # Setup mock drawing to return our mock layer

        # Configure linetypes to include "HIDDEN" for the test
        self.mock_drawing.linetypes.__contains__ = MagicMock(side_effect=lambda x: x in ["CONTINUOUS", "HIDDEN"])

        adapter = EzdxfAdapter(self.mock_logger_service)
        layer_name_to_test = "TARGET_LAYER_PROPS"

        adapter.set_layer_properties(
            doc=self.mock_drawing, # Pass the mock drawing
            layer_name=layer_name_to_test, # Pass the layer name
            color=5, linetype="HIDDEN", lineweight=50,
            plot=False, on=False, frozen=True, locked=True
        )
        self.assertTrue(mock_layer_entity_for_test.is_off) # Assert is_off state
        self.assertEqual(mock_layer_entity_for_test.dxf.color, -5) # is_off makes color negative
        self.assertEqual(mock_layer_entity_for_test.dxf.linetype, "HIDDEN")
        self.assertEqual(mock_layer_entity_for_test.dxf.lineweight, 50)
        self.assertEqual(mock_layer_entity_for_test.dxf.plot, 0) # plot=False
        # self.assertEqual(mock_layer_entity_for_test.dxf.flags, 1) # frozen - flags can be combined
        mock_layer_entity_for_test.lock.assert_called_once()
        mock_layer_entity_for_test.freeze.assert_called_once()
        self.mock_logger.debug.assert_called_with(f"Set properties for layer: '{layer_name_to_test}'. Color: 5, LType: HIDDEN, LW: 50, Plot: False, On: False, Frozen: True, Locked: True")


    def test_set_layer_properties_on_and_thaw_unlock(self):
        self._mock_ezdxf_globally()
        mock_layer_entity_for_state_test = MockDXFEntity("TARGET_LAYER_STATE")
        mock_layer_entity_for_state_test.dxf.color = -7 # Start as off
        mock_layer_entity_for_state_test.dxf.flags = 3 # Start as frozen and locked (1 | 2)
        self.mock_drawing.layers.get.return_value = mock_layer_entity_for_state_test # Setup mock drawing

        adapter = EzdxfAdapter(self.mock_logger_service)
        layer_name_for_state_test = "TARGET_LAYER_STATE"

        adapter.set_layer_properties(
            doc=self.mock_drawing, # Pass mock drawing
            layer_name=layer_name_for_state_test, # Pass layer name
            on=True, frozen=False, locked=False
        )
        self.assertEqual(mock_layer_entity_for_state_test.dxf.color, 7) # Turns on
        mock_layer_entity_for_state_test.thaw.assert_called_once()
        mock_layer_entity_for_state_test.unlock.assert_called_once()

    def test_set_layer_properties_no_entity(self):
        self._mock_ezdxf_globally()
        # Simulate layer not being found in the document
        self.mock_drawing.layers.get.return_value = None
        adapter = EzdxfAdapter(self.mock_logger_service)
        layer_name_not_found = "NON_EXISTENT_LAYER"

        with self.assertRaisesRegex(DXFProcessingError, f"Layer '{layer_name_not_found}' not found in document for property setting."):
            adapter.set_layer_properties(doc=self.mock_drawing, layer_name=layer_name_not_found, color=1)
        self.mock_logger.error.assert_called_with(f"Layer '{layer_name_not_found}' not found in document, cannot set properties.")


    # --- Entity Querying ---
    def test_query_entities_success(self):
        self._mock_ezdxf_globally()
        mock_entities = [MockDXFEntity("E1"), MockDXFEntity("E2")]
        self.mock_modelspace.query.return_value = mock_entities
        adapter = EzdxfAdapter(self.mock_logger_service)

        result = adapter.query_entities(self.mock_modelspace, 'LINE[layer=="0"]')
        self.mock_modelspace.query.assert_called_with('LINE[layer=="0"]')
        self.assertEqual(result, mock_entities)
        self.mock_logger.debug.assert_called_with("Querying entities in modelspace/block with query: LINE[layer==\"0\"]")

    def test_query_entities_dxf_value_error(self):
        self._mock_ezdxf_globally()
        self.mock_modelspace.query.side_effect = DXFValueError("Bad query")
        adapter = EzdxfAdapter(self.mock_logger_service)

        with self.assertRaisesRegex(DXFProcessingError, "Invalid query string or entity type for query: BAD_QUERY. Error: Bad query"):
            adapter.query_entities(self.mock_modelspace, "BAD_QUERY")

    # --- Hatch Fill Tests ---
    def test_set_hatch_pattern_fill_success(self):
        self._mock_ezdxf_globally()
        mock_hatch_entity = MagicMock(spec=Hatch)
        mock_hatch_entity.dxf = MagicMock()
        mock_hatch_entity.dxf.handle = "H123"
        mock_hatch_entity.dxf.solid_fill = 0 # Required for the adapter logic to proceed with pattern
        mock_hatch_entity.set_pattern_fill = MagicMock() # Ensure the method exists
        mock_hatch_entity.set_solid_fill = MagicMock() # Though not directly used here, good for consistency

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.set_hatch_pattern_fill(mock_hatch_entity, "ANSI31", color=3, scale=0.5, angle=45)

        mock_hatch_entity.set_pattern_fill.assert_called_with(name="ANSI31", color=3, scale=0.5, angle=45)
        self.assertEqual(mock_hatch_entity.dxf.solid_fill, 0)
        self.mock_logger.debug.assert_called_with("Setting pattern fill for HATCH (handle: H123): name='ANSI31', color=3, scale=0.5, angle=45")

    def test_set_hatch_pattern_fill_invalid_entity_type(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        # We need to patch the ezdxf.entities.Hatch that the adapter imports for this test to work correctly
        # with the isinstance check, if EZDXF_TEST_AVAILABLE is true.
        # For now, if EZDXF_TEST_AVAILABLE, this test might fail due to isinstance check using real Hatch.
        # Let's assume the adapter's isinstance check is robust or the test environment handles this.
        with self.assertRaisesRegex(DXFProcessingError, "Invalid entity type for set_hatch_pattern_fill"):
            adapter.set_hatch_pattern_fill(MockDXFEntity(), "SOLID") # Passing a generic mock entity

    def test_set_hatch_solid_fill_success(self):
        self._mock_ezdxf_globally()
        mock_hatch_entity = MagicMock(spec=Hatch)
        mock_hatch_entity.dxf = MagicMock()
        mock_hatch_entity.dxf.handle = "H456"
        mock_hatch_entity.set_pattern_fill = MagicMock() # Good for consistency
        mock_hatch_entity.set_solid_fill = MagicMock()   # Ensure the method exists

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.set_hatch_solid_fill(mock_hatch_entity, color=7)

        mock_hatch_entity.set_solid_fill.assert_called_with(color=7)
        self.mock_logger.debug.assert_called_with("Setting solid fill for HATCH (handle: H456): color=7")


    def test_set_hatch_solid_fill_invalid_entity_type(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        # Similar to above, handle isinstance for EZDXF_TEST_AVAILABLE
        with self.assertRaisesRegex(DXFProcessingError, "Invalid entity type for set_hatch_solid_fill"):
            adapter.set_hatch_solid_fill(MockDXFEntity(), color=1)


    # --- Test for add_geodataframe_to_dxf ---
    def test_add_geodataframe_to_dxf_empty_gdf(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        # Ensure self.mock_drawing is set up by _mock_ezdxf_globally
        # It should be self.mock_ezdxf_module.new.return_value or self.mock_ezdxf_module.readfile.return_value
        # For this test, let's assume we have a drawing object, which would be self.mock_drawing
        mock_drawing_instance = self.mock_drawing # Use the one prepared in _mock_ezdxf_globally
        mock_gdf = MagicMock()
        mock_gdf.empty = True
        adapter.add_geodataframe_to_dxf(mock_drawing_instance, mock_gdf, "GEO_LAYER")
        self.mock_logger.info.assert_called_with("GeoDataFrame is empty or None for layer GEO_LAYER. Nothing to add.")
        # If modelspace is obtained via drawing.modelspace(), ensure it's mocked on mock_drawing_instance
        if hasattr(mock_drawing_instance, 'modelspace'):
            mock_drawing_instance.modelspace.return_value.add_point.assert_not_called()

    def test_add_geodataframe_to_dxf_success(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)

        # Mock GeoDataFrame
        mock_row1_geom = MagicMock()
        mock_row1_geom.geom_type = 'Point'
        mock_row1_geom.x = 10
        mock_row1_geom.y = 20
        mock_row1 = MagicMock()
        mock_row1.geometry = mock_row1_geom

        mock_row2_geom = MagicMock()
        mock_row2_geom.geom_type = 'LineString'
        mock_row2_geom.coords = [(0,0), (1,1)]
        mock_row2 = MagicMock()
        mock_row2.geometry = mock_row2_geom

        mock_row3_geom_ext = MagicMock()
        mock_row3_geom_ext.coords = [(0,0), (1,0), (1,1), (0,1), (0,0)]
        mock_row3_geom = MagicMock()
        mock_row3_geom.geom_type = 'Polygon'
        mock_row3_geom.exterior = mock_row3_geom_ext

        mock_row3 = MagicMock()
        mock_row3.geometry = mock_row3_geom

        mock_gdf = MagicMock()
        # Configure len(mock_gdf) for the logger message
        # One way to do this is to mock __len__ if GeoDataFrame uses it,
        # or set a property if the adapter reads it directly.
        # For now, assume it's used to get the count for the log message.
        # The adapter code uses len(gdf), so mock_gdf.__len__ is needed.
        mock_gdf.__len__ = MagicMock(return_value=3)
        mock_gdf.empty = False
        mock_gdf.iterrows.return_value = iter([(0, mock_row1), (1, mock_row2), (2, mock_row3)])

        # Mock hatch returned by msp.add_hatch
        mock_hatch_for_gdf = MagicMock()
        mock_hatch_for_gdf.paths = MagicMock()
        self.mock_modelspace.add_hatch.return_value = mock_hatch_for_gdf


        adapter.add_geodataframe_to_dxf(self.mock_drawing, mock_gdf, "DATA_LAYER", color=5) # color for hatch

        self.mock_modelspace.add_point.assert_called_with((10, 20), dxfattribs={'layer': "DATA_LAYER"})
        self.mock_modelspace.add_lwpolyline.assert_called_with([(0,0), (1,1)], dxfattribs={'layer': "DATA_LAYER"})
        self.mock_modelspace.add_hatch.assert_called_with(color=5, dxfattribs={'layer': "DATA_LAYER"})
        mock_hatch_for_gdf.paths.add_polyline_path.assert_called_with([(0,0), (1,0), (1,1), (0,1), (0,0)], is_closed=True)
        self.mock_logger.info.assert_called_with("Added 3 geometries to DXF layer: DATA_LAYER")


    # --- Other Entity Creation Methods ---
    def test_create_text_style_new(self):
        self._mock_ezdxf_globally()
        mock_style_entity = MockDXFEntity("NewStyle")
        self.mock_drawing.styles = MagicMock()
        self.mock_drawing.styles.__contains__.return_value = False
        self.mock_drawing.styles.new.return_value = mock_style_entity

        adapter = EzdxfAdapter(self.mock_logger_service)
        style = adapter.create_text_style(self.mock_drawing, "MyStyle", "Arial.ttf")

        self.mock_drawing.styles.new.assert_called_with("MyStyle", dxfattribs={'font': "Arial.ttf"})
        self.assertEqual(style, mock_style_entity)
        self.mock_logger.info.assert_called_with("Successfully created text style 'MyStyle'.")

    def test_create_text_style_existing_same_font(self):
        self._mock_ezdxf_globally()
        mock_existing_style = MockDXFEntity("ExistingStyle")
        mock_existing_style.dxf.font = "arial.ttf" # Case difference
        self.mock_drawing.styles = MagicMock()
        self.mock_drawing.styles.__contains__.return_value = True
        self.mock_drawing.styles.get.return_value = mock_existing_style

        adapter = EzdxfAdapter(self.mock_logger_service)
        style = adapter.create_text_style(self.mock_drawing, "MyStyle", "Arial.TTF") # Test font case insensitivity

        self.mock_drawing.styles.get.assert_called_with("MyStyle")
        self.assertEqual(style, mock_existing_style)
        self.mock_logger.debug.assert_called_with("Text style 'MyStyle' already exists with font 'Arial.TTF'.")


    def test_add_text_entity(self):
        self._mock_ezdxf_globally()
        mock_text_entity = MagicMock()
        self.mock_modelspace.add_text.return_value = mock_text_entity

        adapter = EzdxfAdapter(self.mock_logger_service)
        text_ent = adapter.add_text(self.mock_modelspace, "Hello", dxfattribs={"color":1}, point=(1,2,3), height=5, rotation=15, style="TestStyle")

        self.mock_modelspace.add_text.assert_called_with(
            text="Hello",
            dxfattribs={'color': 1, 'insert': (1,2,3), 'height': 5, 'rotation': 15, 'style': "TestStyle", 'layer': '0'}
        )
        self.assertEqual(text_ent, mock_text_entity)

    def test_add_mtext_entity(self):
        self._mock_ezdxf_globally()
        mock_mtext_entity = MagicMock()
        self.mock_modelspace.add_mtext.return_value = mock_mtext_entity

        adapter = EzdxfAdapter(self.mock_logger_service)
        mtext_ent = adapter.add_mtext(self.mock_modelspace, "World", insert=(4,5,6), char_height=3, width=50, style="MStyle")

        self.mock_modelspace.add_mtext.assert_called_with(
            text="World",
            dxfattribs={'insert': (4,5,6), 'char_height': 3, 'width': 50, 'style': "MStyle", 'layer': '0'}
        )
        self.assertEqual(mtext_ent, mock_mtext_entity)


    # --- Test set_entity_properties ---
    def test_set_entity_properties_all_set(self):
        self._mock_ezdxf_globally()
        mock_entity = MockDXFEntity()
        mock_entity.dxf.set = MagicMock() # To check calls if needed

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.set_entity_properties(
            mock_entity, layer="TestLayer", color=1, linetype="DASHED",
            lineweight=25, transparency=0.5
        )

        expected_calls = [
            call('layer', "TestLayer"),
            call('color', 1),
            call('linetype', "DASHED"),
            call('lineweight', 25),
        ]
        # Transparency might require hasattr check, so test its call if supported
        if hasattr(mock_entity.dxf, "transparency"):
             expected_calls.append(call('transparency', 33554559))

        mock_entity.dxf.set.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_entity.dxf.set.call_count, len(expected_calls))

    def test_set_entity_properties_no_entity(self):
        self._mock_ezdxf_globally()
        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.set_entity_properties(None, color=1) # Should log warning and return
        self.mock_logger.warning.assert_called_with("Attempted to set properties on a None entity.")

    def test_set_entity_properties_unsupported_transparency(self):
        self._mock_ezdxf_globally()
        mock_entity_no_transparency = MockDXFEntity()
        # Remove transparency attribute for this test
        if hasattr(mock_entity_no_transparency.dxf, "transparency"): # Check before deleting
            delattr(mock_entity_no_transparency.dxf, "transparency")
        mock_entity_no_transparency.dxf.set = MagicMock()

        adapter = EzdxfAdapter(self.mock_logger_service)
        adapter.set_entity_properties(mock_entity_no_transparency, transparency=0.5)

        # Check that 'transparency' was not in the set calls
        for set_call in mock_entity_no_transparency.dxf.set.call_args_list:
            self.assertNotEqual(set_call[0][0], 'transparency')
        # Use the actual entity type from the mock entity for the log message
        self.mock_logger.debug.assert_any_call(f"Entity type {mock_entity_no_transparency.dxftype()} may not directly support 'transparency' attribute. Property not set.")


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
